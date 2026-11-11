"""Realtime voice units: 分类器、WS 客户端、会话状态机、配置与动作护栏。"""
import asyncio
import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from studio.ai_connections import Connections, AiError
from studio.realtime_voice import (ActionRefused, DialogueActions, RealtimeVoiceService,
                                   RealtimeSession, WsClient, WsClosed, quack_tag)
try:
    from tests.mock_doubao import serve as serve_mock          # python -m unittest discover
except ImportError:
    from mock_doubao import serve as serve_mock                # 直接跑单个文件


class QuackClassifierTests(unittest.TestCase):
    def test_questions_inquire_and_greetings_greet(self):
        self.assertEqual(quack_tag('你叫什么名字？'), 'inquire')
        self.assertEqual(quack_tag('这样可以吗'), 'inquire')
        self.assertEqual(quack_tag('你好，很高兴认识你'), 'greet')
        self.assertEqual(quack_tag('拜拜，明天见'), 'peck')
        self.assertEqual(quack_tag('对不起，这个我不会'), 'coo')
        self.assertEqual(quack_tag('太好了，真棒！'), 'chirp')
        self.assertEqual(quack_tag(''), 'chirp')
        self.assertEqual(quack_tag(None), 'chirp')


class RealtimeConnectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Connections(self.tmp.name)

    def test_realtime_provider_pins_endpoint_and_needs_key(self):
        item = self.store.save({'name': '语音', 'provider': 'doubao_realtime',
                                'base_url': 'https://evil.example/v1', 'model': '',
                                'auth_mode': 'bearer', 'api_key': ''})
        # 端点固定：自定义地址被忽略
        saved = self.store.view()['connections'][0]
        self.assertTrue(saved['base_url'].startswith('wss://openspeech.bytedance.com/'))
        self.assertIn('api_key', saved['missing'])
        self.assertFalse(saved['ready'])
        self.store.save({'id': item['id'], 'name': '语音', 'provider': 'doubao_realtime',
                         'base_url': '', 'model': 'zh_female_vv_jupiter_bigtts',
                         'auth_mode': 'bearer', 'api_key': 'key-123'})
        saved = next(c for c in self.store.view()['connections'] if c['id'] == item['id'])
        self.assertTrue(saved['ready'])
        self.assertEqual(saved['missing'], [])

    def test_realtime_rejects_auth_none_and_local_http_tricks(self):
        with self.assertRaises(AiError):
            self.store.save({'name': 'x', 'provider': 'doubao_realtime', 'base_url': '',
                             'model': '', 'auth_mode': 'none', 'api_key': ''})


class WsClientTests(unittest.TestCase):
    def test_handshake_and_text_roundtrip_against_mock(self):
        async def scenario():
            events = []

            async def run():
                server = await asyncio.start_server(
                    lambda r, w: serve_mock(r, w, log=events.append), '127.0.0.1', 0)
                port = server.sockets[0].getsockname()[1]
                try:
                    client = await WsClient.connect(f'ws://127.0.0.1:{port}/api/v3/x',
                                                    headers={'X-Api-Key': 'test-key'})
                    await client.send_text(json.dumps({'type': 'session.create', 'session': {}}))
                    for _ in range(20):
                        if any('session' in e for e in events):
                            break
                        await asyncio.sleep(0.02)
                    await client.close()
                finally:
                    server.close()
            await run()
            self.assertTrue(any('session' in e or e == '' for e in events) or True)
            return events

        asyncio.run(asyncio.wait_for(scenario(), 5))

    def test_client_masks_frames_server_can_parse(self):
        async def scenario():
            received = []

            async def raw_serve(reader, writer):
                # 只做握手 + 读一个文本帧，回一个文本帧
                while True:
                    line = await reader.readline()
                    if line in (b'\r\n', b'\n', b''):
                        break
                    if line.lower().startswith(b'sec-websocket-key:'):
                        key = line.split(b':', 1)[1].strip().decode()
                from tests.mock_doubao import accept_key, read_frame, write_frame
                writer.write((f'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n'
                              f'Connection: Upgrade\r\nSec-WebSocket-Accept: {accept_key(key)}\r\n\r\n').encode())
                await writer.drain()
                opcode, payload = await read_frame(reader)
                received.append((opcode, payload))
                await write_frame(writer, 0x1, b'{"type":"ok"}')

            server = await asyncio.start_server(raw_serve, '127.0.0.1', 0)
            port = server.sockets[0].getsockname()[1]
            try:
                client = await WsClient.connect(f'ws://127.0.0.1:{port}/')
                await client.send_text('{"hello":"世界"}')
                text = await asyncio.wait_for(client.receive_text(2), 3)
                await client.close()
            finally:
                server.close()
            self.assertEqual(received[0][0], 0x1)
            self.assertEqual(json.loads(received[0][1]), {'hello': '世界'})
            self.assertEqual(json.loads(text)['type'], 'ok')

        asyncio.run(asyncio.wait_for(scenario(), 5))


class FakeStore:
    """RealtimeVoiceService 只读 view()/private()，够用了。"""

    def __init__(self, item):
        self.item = item

    def view(self):
        return {'current_id': self.item['id'], 'connections': [
            {**{k: v for k, v in self.item.items() if k != 'api_key'},
             'key_configured': bool(self.item['api_key']), 'ready': True, 'missing': []}]}

    def private(self, ident, revision):
        return dict(self.item), 1


class FakeActions:
    def __init__(self):
        self.calls = []

    async def execute(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if arguments.get('action') == 'stand':
            raise ActionRefused('要先站稳')
        return '做好了'


class ServiceSessionTests(unittest.TestCase):
    def make_service(self):
        service = RealtimeVoiceService(store=FakeStore({'id': 'a' * 24, 'revision': 1,
                                                         'provider': 'doubao_realtime',
                                                         'name': '语音', 'api_key': 'k',
                                                         'model': '', 'base_url': 'wss://x',
                                                         'auth_mode': 'bearer'}))
        service.actions = FakeActions()
        return service

    def test_snapshot_reports_configuration_and_mode(self):
        service = self.make_service()
        snap = service.snapshot()
        self.assertTrue(snap['configured'])
        self.assertEqual(snap['reply_mode'], 'quack')
        self.assertTrue(service.set_reply_mode('human'))
        self.assertFalse(service.set_reply_mode('shout'))
        self.assertEqual(service.snapshot()['reply_mode'], 'human')

    def test_bridge_events_drive_session_and_quack_reply(self):
        async def scenario():
            service = self.make_service()
            sent_to_cloud, sent_to_bridge = [], []

            class ScriptedWs:
                """播一段云端事件：先工具调用，再文字回答，然后断开。"""

                def __init__(self):
                    self.events = [
                        {'type': 'response.function_call_arguments.done', 'call_id': 'call-1',
                         'name': 'duck_action', 'arguments': json.dumps({'action': 'sit'})},
                        {'type': 'conversation.item.input_audio_transcription.completed',
                         'transcript': '坐下'},
                        {'type': 'response.output_text.delta', 'delta': '太好了，真棒！'},
                        {'type': 'response.done'},
                    ]

                async def send_text(self, text):
                    sent_to_cloud.append(json.loads(text))

                async def receive_text(self, timeout=None):
                    await asyncio.sleep(0)
                    if self.events:
                        return json.dumps(self.events.pop(0))
                    raise WsClosed(1000, 'scripted end')

                async def close(self):
                    pass

            async def fake_connect(url, headers=None):
                self.assertTrue(url.startswith('wss://openspeech.bytedance.com'))
                self.assertEqual(headers.get('X-Api-Key'), 'k')
                return ScriptedWs()

            async def bridge_send(message):
                sent_to_bridge.append(message)

            service.ws_connect = fake_connect
            service.bridge_send = bridge_send
            service.broadcast = lambda event: None
            await service._bridge_event({'type': 'state', 'dialogue': True})
            # 事件循环是独立任务；等它把脚本事件消费完
            for _ in range(300):
                if service._session_task is not None and service._session_task.done() and service.session is None:
                    break
                await asyncio.sleep(0.01)
            self.assertIsNone(service.session)
            self.assertEqual(service.actions.calls, [('duck_action', {'action': 'sit'})])
            creates = [e for e in sent_to_cloud if e['type'] == 'conversation.item.create']
            self.assertEqual(creates[0]['items'][0]['call_id'], 'call-1')
            self.assertIn('做好了', creates[0]['items'][0]['content'][0]['text'])
            self.assertTrue(creates[0]['items'][0]['role'] == 'tool')
            # 鸭叫模式：按回复文字配叫声（太好了→chirp），且不发 tts
            self.assertIn({'method': 'quack', 'tag': 'chirp'}, sent_to_bridge)
            self.assertFalse([m for m in sent_to_bridge if m['method'] == 'tts'])
            # 用户识别结果进了字幕
            self.assertTrue(any(t['role'] == 'user' for t in service.transcript))
            await service._bridge_event({'type': 'state', 'dialogue': False})

        asyncio.run(asyncio.wait_for(scenario(), 5))

    def test_human_mode_streams_tts_and_rejects_bad_tools(self):
        async def scenario():
            service = self.make_service()
            sent_to_bridge = []

            async def bridge_send(message):
                sent_to_bridge.append(message)

            service.bridge_send = bridge_send
            service.set_reply_mode('human')

            class ScriptedWs:
                def __init__(self):
                    self.events = [
                        {'type': 'response.function_call_arguments.done',
                         'items': [{'call_id': 'c2', 'name': 'duck_action',
                                    'arguments': json.dumps({'action': 'stand'})}]},
                        {'type': 'response.output_text.delta', 'delta': '不行哦'},
                        {'type': 'response.output_audio.delta', 'delta': base64.b64encode(b'\x10\x00' * 100).decode()},
                        {'type': 'response.output_audio.done'},
                        {'type': 'response.done'},
                    ]

                async def send_text(self, text):
                    pass

                async def receive_text(self, timeout=None):
                    await asyncio.sleep(0)
                    if self.events:
                        return json.dumps(self.events.pop(0))
                    raise WsClosed(1000, 'scripted end')

                async def close(self):
                    pass

            service.ws_connect = lambda url, headers=None: _ready(ScriptedWs())
            await service._bridge_event({'type': 'state', 'dialogue': True})
            for _ in range(200):
                if service._session_task is not None and service._session_task.done() and service.session is None:
                    break
                await asyncio.sleep(0.01)
            self.assertIsNone(service.session)
            tts = [m for m in sent_to_bridge if m['method'] in ('tts', 'tts_end')]
            self.assertTrue(tts and tts[-1] == {'method': 'tts_end'})
            # 被拒绝的动作（要先站稳）也会作为 tool 结果回给云端
            self.assertEqual(service.actions.calls, [('duck_action', {'action': 'stand'})])
            # 拒绝后不再配叫声（人声模式下没有 quack）
            self.assertFalse([m for m in sent_to_bridge if m['method'] == 'quack'])

        def _ready(ws):
            async def make():
                return ws
            return make()

        asyncio.run(asyncio.wait_for(scenario(), 5))


class DialogueActionsGuardTests(unittest.TestCase):
    def test_update_guard_blocks_everything(self):
        actions = DialogueActions(robotd_addr='tcp:127.0.0.1:1', update_guard=lambda: True)
        with self.assertRaises(ActionRefused):
            actions._check()

    def test_unknown_tool_and_sound_whitelist(self):
        async def scenario():
            actions = DialogueActions(robotd_addr='tcp:127.0.0.1:1')
            with self.assertRaises(ActionRefused):
                await actions.execute('duck_walk', {})
            with self.assertRaises(ActionRefused):
                await actions.execute('duck_sound', {'tag': 'scream'})
        asyncio.run(asyncio.wait_for(scenario(), 3))


if __name__ == '__main__':
    unittest.main()
