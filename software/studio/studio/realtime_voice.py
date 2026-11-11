"""豆包实时语音对话：云端 WebSocket 会话 + duck-echo 音频桥 + 受限动作执行。

链路（F26）：
    麦克风(duck-echo) --audio.sock 16k PCM--> 本服务 --WSS--> 豆包实时语音
    云端回答文字 --> 网页字幕；云端 TTS PCM --> duck-echo 扬声器（人声模式）
    云端按回复文字配叫声（鸭叫模式，本地分类器选 tag，经 duck-echo 的 robot.sound）
    云端工具调用 --> 白名单动作（坐/站/点头/摇头/歪头/张嘴/叫声），带回读与护栏

协议来源：docs.volcengine.com 豆包语音《端到端实时语音》接入必读（Seeduplex 3.0）。
本文件不把 API Key 写进任何日志或广播；事件文本只保留最近少量轮次给网页看。
"""
import asyncio
import base64
import json
import logging
import os
import ssl
import struct
import time
import urllib.parse

from .rpc import Conn, RpcError, Timeout, Unreachable, encode_notify, open_conn

LOG = logging.getLogger('studio.realtime')

WSS_URL = 'wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue'
MODEL_ID = '1.2.6.1'
DEFAULT_VOICE = 'zh_female_vv_jupiter_bigtts'
VOICE_LIMIT = 200
INPUT_RATE = 16000
OUTPUT_RATE = 24000
CONNECT_TIMEOUT_S = 8.0
IDLE_CLOSE_S = 300.0
MAX_FRAME = 1 << 20
MAX_TEXT = 2000
TRANSCRIPT_TURNS = 24

QUACK_TAGS = ('chirp', 'greet', 'inquire', 'coo', 'alarm', 'peck')

TOOLS = [
    {"type": "function", "name": "duck_action",
     "description": "让小鸭子做一个动作。sit=坐下，stand=站起来，nod=点头，shake=摇头，tilt=歪头，mouth=张嘴。",
     "parameters": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["sit", "stand", "nod", "shake", "tilt", "mouth"]}},
         "required": ["action"]}},
    {"type": "function", "name": "duck_sound",
     "description": "让小鸭子叫一声。tag：chirp=嘎，greet=打招呼，inquire=疑问，coo=咕咕撒娇，alarm=大叫，peck=告别。",
     "parameters": {"type": "object", "properties": {
         "tag": {"type": "string", "enum": list(QUACK_TAGS)}}, "required": ["tag"]}},
    {"type": "function", "name": "set_reply_mode",
     "description": "切换回答方式。用户说“说人话”等明确要求时调 human（人声说出回答）；用户要求用鸭子叫声回答时调 quack。",
     "parameters": {"type": "object", "properties": {
         "mode": {"type": "string", "enum": ["human", "quack"]}}, "required": ["mode"]}},
]

INSTRUCTIONS = (
    "你是一台名叫小鸭子的桌面机器人，通过语音和主人聊天。用简短口语化的中文回答，"
    "一般一到两句话，语气可爱活泼。主人让你做动作或叫一声时，调用对应工具，"
    "并用一句话回应。默认情况下你的回答只作为字幕显示、由鸭子叫声配音；"
    "只有主人明确要求“说人话”或已切换到人声模式时，才直接说出完整回答。"
    "不确定或做不到的要求不要调用动作工具，用文字说明。"
)


def instructions_with_mode(reply_mode):
    if reply_mode == 'human':
        return INSTRUCTIONS + "当前是人声模式：回答会被直接说出来，保持句子简短。"
    return INSTRUCTIONS + "当前是鸭叫模式：回答保持简短，系统会按你的文字配一声合适的鸭叫。"


def quack_tag(text):
    """回复文字 -> 叫声 tag。规则保守：识别不出就嘎一声。"""
    if not isinstance(text, str):
        return 'chirp'
    compact = text.strip()
    if any(mark in compact for mark in ('？', '?', '吗', '什么', '为什么', '怎么', '几', '哪')) \
            or compact.endswith(('吧', '呢')):
        return 'inquire'
    if any(word in compact for word in ('你好', '嗨', '哈喽', '欢迎', '认识你很高兴')):
        return 'greet'
    if any(word in compact for word in ('拜拜', '再见', '明天见', '晚安')):
        return 'peck'
    if any(word in compact for word in ('对不起', '抱歉', '难过', '不可以', '不行', '不能', '危险', '小心')):
        return 'coo'
    if any(word in compact for word in ('开心', '高兴', '喜欢', '太好了', '哈哈', '真棒', '好耶')):
        return 'chirp'
    if any(word in compact for word in ('快', '注意', '警告', '站起来', '坐好')):
        return 'alarm'
    return 'chirp'


# ---------------- 最小 RFC6455 客户端 ----------------

class WsClosed(Exception):
    def __init__(self, code=None, reason=''):
        super().__init__(f'websocket closed ({code}) {reason}'[:200])
        self.code, self.reason = code, reason


class WsClient:
    """只实现了对话要用的子集：文本帧 + ping/pong + close；客户端帧一律加掩码。"""

    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self._buf = bytearray()
        self._closed = False

    @classmethod
    async def connect(cls, url, headers=None, timeout=CONNECT_TIMEOUT_S, ssl_ctx=None):
        parsed = urllib.parse.urlsplit(url)
        secure = parsed.scheme == 'wss'
        if parsed.scheme not in ('ws', 'wss'):
            raise ValueError(f'websocket 地址要用 ws:// 或 wss://：{url}')
        host, port = parsed.hostname, parsed.port or (443 if secure else 80)
        path = parsed.path or '/'
        if parsed.query:
            path += '?' + parsed.query
        if secure and ssl_ctx is None:
            ssl_ctx = ssl.create_default_context()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ssl_ctx, limit=MAX_FRAME), timeout)
        key = base64.b64encode(os.urandom(16)).decode('ascii')
        lines = [f'GET {path} HTTP/1.1', f'Host: {host}' + (f':{port}' if port not in (80, 443) else ''),
                 'Upgrade: websocket', 'Connection: Upgrade', f'Sec-WebSocket-Key: {key}',
                 'Sec-WebSocket-Version: 13']
        for name, value in (headers or {}).items():
            lines.append(f'{name}: {value}')
        writer.write(('\r\n'.join(lines) + '\r\n\r\n').encode('utf-8'))
        await writer.drain()
        status = await asyncio.wait_for(reader.readline(), timeout)
        parts = status.split(None, 2)
        if len(parts) < 2 or parts[0] != b'HTTP/1.1' or parts[1] != b'101':
            raise WsClosed(reason=f'握手被拒：{status[:120]!r}')
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout)
            if line in (b'\r\n', b'\n', b''):
                break
        return cls(reader, writer)

    async def send_text(self, text):
        await self._send(0x1, text.encode('utf-8'))

    async def _send(self, opcode, payload):
        if self._closed:
            raise WsClosed(reason='local close')
        mask = os.urandom(4)
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < (1 << 16):
            header.append(0x80 | 126)
            header.extend(struct.pack('>H', length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack('>Q', length))
        header.extend(mask)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.writer.write(bytes(header) + masked)
        await self.writer.drain()

    async def receive_text(self, timeout=None):
        """返回一条完整文本消息；ping 自动回 pong，close 抛 WsClosed。"""
        chunks, last_opcode = [], None
        while True:
            opcode, payload, final = await self._read_frame(timeout)
            if opcode == 0x8:
                code = struct.unpack('>H', payload[:2])[0] if len(payload) >= 2 else None
                try:
                    await self._send(0x8, payload)
                except Exception:  # noqa: BLE001 —— 关闭路上什么错都不重要
                    pass
                raise WsClosed(code, payload[2:].decode('utf-8', 'replace'))
            if opcode == 0x9:            # ping -> pong
                await self._send(0xA, payload)
                continue
            if opcode == 0xA:            # pong
                continue
            if opcode in (0x1, 0x2):
                chunks.append(payload)
                last_opcode = opcode
                if final:
                    return bytes(b''.join(chunks)).decode('utf-8', 'replace')
            elif opcode == 0x0 and chunks:
                chunks.append(payload)
                if final:
                    return bytes(b''.join(chunks)).decode('utf-8', 'replace')

    async def _read_frame(self, timeout):
        while len(self._buf) < 2:
            await self._fill(timeout)
        first, second = self._buf[0], self._buf[1]
        final, opcode = bool(first & 0x80), first & 0x0F
        masked, length = bool(second & 0x80), second & 0x7F
        offset = 2
        if length == 126:
            while len(self._buf) < offset + 2:
                await self._fill(timeout)
            length = struct.unpack('>H', self._buf[offset:offset + 2])[0]
            offset += 2
        elif length == 127:
            while len(self._buf) < offset + 8:
                await self._fill(timeout)
            length = struct.unpack('>Q', self._buf[offset:offset + 8])[0]
            offset += 8
        if length > MAX_FRAME:
            raise WsClosed(reason=f'帧过大：{length}')
        if masked:
            while len(self._buf) < offset + 4:
                await self._fill(timeout)
            offset += 4
        while len(self._buf) < offset + length:
            await self._fill(timeout)
        payload = bytes(self._buf[offset:offset + length])
        del self._buf[:offset + length]
        return opcode, payload, final

    async def _fill(self, timeout):
        block = await asyncio.wait_for(self.reader.read(65536), timeout)
        if not block:
            raise WsClosed(reason='eof')
        self._buf.extend(block)

    async def close(self):
        if not self._closed:
            self._closed = True
            try:
                await self._send(0x8, struct.pack('>H', 1000))
            except Exception:  # noqa: BLE001
                pass
        try:
            self.writer.close()
        except Exception:  # noqa: BLE001
            pass


# ---------------- 受限动作执行 ----------------

class ActionRefused(Exception):
    pass


class DialogueActions:
    """白名单动作：坐/站带姿态回读；头/嘴按 pad_combo 的轨迹发通知；叫声走 robot.sound。"""

    SIT_TIMEOUT_S = 6.0

    def __init__(self, robotd_addr='unix:/run/robotd.sock', update_guard=lambda: False,
                 clock=time.monotonic):
        self.conn = Conn(robotd_addr, 'dialogue')
        self.update_guard = update_guard
        self.clock = clock
        self.lock = asyncio.Lock()

    def _check(self):
        if self.update_guard():
            raise ActionRefused('软件更新中，动作暂停')

    async def _call(self, method, params=None, timeout=2.0):
        result = await self.conn.call(method, params, timeout)
        if isinstance(result, dict) and result.get('accepted') is False:
            raise ActionRefused(str(result.get('reason') or method))
        return result

    async def _state(self):
        policies = await self.conn.call('robot.policies')
        bus = await self.conn.call('robot.busStatus')
        if not isinstance(policies, dict) or not isinstance(policies.get('sitting'), bool):
            raise ActionRefused('读不到当前姿态')
        if bus.get('phase') != 'control' or bus.get('mode') != 'motion':
            raise ActionRefused('主程序不在运动模式')
        return policies, bus

    async def posture(self, target):
        """坐/站，语义对齐 duck-echo voice_commands.PostureCommands（含回读）。"""
        self._check()
        desired = target == 'sit'
        policies, bus = await self._state()
        torque = bus.get('native', {}).get('torque_state_confirmed') is True
        homed = policies.get('homed') is True or bus.get('homed') is True
        if policies['sitting'] == desired and (desired or (torque and homed)):
            return '已经是这个姿势了'
        if not torque or not homed:
            if target == 'stand' and not policies['sitting']:
                await self._call('robot.init')
            else:
                raise ActionRefused('要先站稳并完成上电初始化')
        if not any(isinstance(slot, dict) and slot.get('slot') == 'sitstand' and slot.get('path')
                   and not slot.get('error') for slot in policies.get('slots', [])):
            raise ActionRefused('坐站策略没有安装')
        if bus.get('policy_enabled') is not True:
            if policies['sitting']:
                raise ActionRefused('当前坐姿未开策略，请按原恢复流程处理')
            await self._call('robot.stop')
            await self._call('robot.enable', {'on': True, 'toggle': False})
            deadline = self.clock() + 2.0
            while True:
                policies, bus = await self._state()
                if bus.get('policy_enabled') is True:
                    break
                if self.clock() >= deadline:
                    raise ActionRefused('策略使能没有确认')
                await asyncio.sleep(0.05)
        policies, _ = await self._state()
        if policies['sitting'] != desired:
            await self._call('robot.do', {'skill': 'sit_toggle'})
        deadline = self.clock() + self.SIT_TIMEOUT_S
        while True:
            self._check()
            policies, _ = await self._state()
            if policies['sitting'] == desired:
                return '做好了'
            if self.clock() >= deadline:
                raise ActionRefused('动作发了但姿态没到目标')
            await asyncio.sleep(0.08)

    async def sound(self, tag):
        if tag not in QUACK_TAGS:
            raise ActionRefused(f'不认识的叫声：{tag}')
        self._check()
        await self._call('robot.sound', {'tag': tag})
        return '叫过了'

    async def head(self, action):
        """nod/shake/tilt/mouth：25 Hz 通知轨迹，结束回正 / 合嘴（同 pad 组合动作）。"""
        from . import pad_combo as combo
        steps = {"nod": [{"do": "nod", "times": 2}], "shake": [{"do": "shake", "times": 2}],
                 "tilt": [{"do": "tilt", "side": "right", "ms": 1200}],
                 "mouth": [{"do": "mouth", "open": 0.9, "ms": 900}]}.get(action)
        if steps is None:
            raise ActionRefused(f'不认识的动作：{action}')
        self._check()
        policies, _ = await self._state()
        if policies.get('policy_enabled') is not True and action in ('nod', 'shake', 'tilt'):
            raise ActionRefused('头部的动作要先开始走（策略在跑）')
        step = steps[0]
        duration = combo.step_seconds(step)
        moves_head, moves_mouth = combo.head_at(step, 0.0) is not None, combo.mouth_at(step, 0.0) is not None
        start = self.clock()
        try:
            while True:
                elapsed = self.clock() - start
                if elapsed >= duration:
                    break
                self._check()
                head, mouth = combo.head_at(step, elapsed), combo.mouth_at(step, elapsed)
                if head is not None:
                    await self.conn.notify('robot.head', dict(
                        zip(('neck_pitch', 'head_pitch', 'head_yaw', 'head_roll'), head)))
                if mouth is not None:
                    await self.conn.notify('robot.mouth', {'open': mouth})
                await asyncio.sleep(combo.TICK_S)
        finally:
            head_zero = {"neck_pitch": 0., "head_pitch": 0., "head_yaw": 0., "head_roll": 0.}
            for used, method, params in ((moves_head, 'robot.head', head_zero),
                                         (moves_mouth, 'robot.mouth', {'open': 0.0})):
                if used:
                    try:
                        await self.conn.notify(method, params)
                    except (Unreachable, Timeout, OSError):
                        pass
        return '做好了'

    async def execute(self, name, arguments):
        """执行一个白名单工具调用，返回给云端的人类可读结果。"""
        if name == 'duck_action':
            action = arguments.get('action')
            async with self.lock:
                if action in ('sit', 'stand'):
                    return await self.posture(action)
                return await self.head(action)
        if name == 'duck_sound':
            async with self.lock:
                return await self.sound(arguments.get('tag'))
        if name == 'set_reply_mode':
            return 'reserved'          # 服务层处理（要改自身状态），到不了这里
        raise ActionRefused(f'不认识的工具：{name}')


# ---------------- 会话与服务 ----------------

class RealtimeSession:
    """一次云端对话会话：双向转发 + 事件分发 + 工具回填。"""

    def __init__(self, ws, service):
        self.ws, self.service = ws, service
        self.closing = False
        self.last_activity = time.monotonic()
        self.assistant_text = ''
        self.assistant_spoke = False

    async def send(self, event):
        self.last_activity = time.monotonic()
        await self.ws.send_text(json.dumps(event, ensure_ascii=False, separators=(',', ':')))

    async def append_audio(self, pcm_bytes):
        await self.send({'type': 'input_audio_buffer.append',
                         'audio': base64.b64encode(pcm_bytes).decode('ascii')})

    # 静音状态机已整体移除：桥永远发流（鸭子说话期间由本地抑制自然产生静音段），
    # 云端自己做 VAD；不再发 input_audio_mute/unmute.commit（那套快速切换正是
    # "第一轮回答后云端不再识别"的根因）。

    async def tool_result(self, call_id, text):
        await self.send({'type': 'conversation.item.create', 'items': [{
            'call_id': call_id, 'role': 'tool',
            'content': [{'type': 'input_text', 'text': str(text)[:400]}]}]})

    async def close(self):
        if not self.closing:
            self.closing = True
            try:
                await self.send({'type': 'session.close'})
            except Exception:  # noqa: BLE001 —— 关闭失败不影响流程
                pass
        await self.ws.close()

    async def run(self):
        """读云端事件直到会话结束；异常交给 service 处理。"""
        while True:
            text = await self.ws.receive_text(timeout=IDLE_CLOSE_S)
            self.last_activity = time.monotonic()
            event = json.loads(text)
            kind = event.get('type', '')
            if kind == 'conversation.item.input_audio_transcription.completed':
                # 真云端字段是 text（2026-11-11 实连核对）；transcript 作兼容兜底
                value = event.get('text') or event.get('transcript') or ''
                if value:
                    self.service._record('user', value, final=True)
            elif kind == 'response.output_text.delta':
                self.assistant_text += event.get('delta') or ''
                self.service._record('assistant', self.assistant_text)
            elif kind == 'response.output_audio.delta' and self.service.reply_mode == 'human':
                data = base64.b64decode(event.get('delta') or '')
                if data:
                    if not self.assistant_spoke:
                        LOG.warning('dialogue: TTS stream started (%s mode)', self.service.reply_mode)
                    self.assistant_spoke = True
                    await self.service.bridge_send({'method': 'tts',
                                                   'data': base64.b64encode(data).decode('ascii')})
            elif kind == 'response.output_audio.done':
                if self.assistant_spoke:
                    LOG.warning('dialogue: TTS stream done, handed to bridge')
                    await self.service.bridge_send({'method': 'tts_end'})
                    self.assistant_spoke = False
            elif kind == 'response.done':
                if self.service.reply_mode == 'quack' and self.assistant_text.strip():
                    tag = quack_tag(self.assistant_text)
                    LOG.warning('dialogue: quack reply (%s) for %r', tag, self.assistant_text[:40])
                    await self.service.bridge_send({'method': 'quack', 'tag': tag})
                elif not self.assistant_spoke:
                    pass                    # 人声模式但云端没给音频：文字已在网页显示
                self.assistant_text = ''
            elif kind == 'response.function_call_arguments.done':
                # 真云端把一次（或多个）调用放在 items 数组里（2026-11-11 实连核对）
                for item in (event.get('items') or [event]):
                    if isinstance(item, dict) and item.get('name'):
                        await self.service._dispatch_tool(
                            item.get('call_id'), item.get('name'), item.get('arguments'), self)
            elif kind == 'error':
                message = str(event.get('error') or event)[:240]
                raise WsClosed(reason=f'云端错误：{message}')


class RealtimeVoiceService:
    """常驻：连着 duck-echo 的 audio.sock；对话开时建云端会话，事件广播给网页。"""

    def __init__(self, store=None, bridge_addr='unix:/run/duck-echo/audio.sock',
                 robotd_addr='unix:/run/robotd.sock', update_guard=lambda: False,
                 ws_connect=None, log=None):
        self.store = store
        self.bridge_addr = bridge_addr
        self.actions = DialogueActions(robotd_addr, update_guard)
        self.ws_connect = ws_connect or WsClient.connect
        self.log = log
        self.broadcast = None            # app 注入的 async callable(dict)
        self.reply_mode = 'quack'
        self.session = None
        self.session_generation = 0
        self._session_task = None
        self._starting = False
        self.bridge_writer = None
        self.bridge_connected = False
        self.transcript = []             # [{'role','text'}] 环形，最近 TRANSCRIPT_TURNS 条
        self.error = None
        self.state_lock = asyncio.Lock()
        self.stopped = asyncio.Event()

    # ---- 生命周期 ----
    async def start(self):
        asyncio.create_task(self._bridge_loop())

    async def stop(self):
        self.stopped.set()
        await self._end_session('服务停止')
        if self.bridge_writer is not None:
            try:
                self.bridge_writer.close()
            except Exception:  # noqa: BLE001
                pass

    def snapshot(self):
        config = self._config_view()
        return {'available': self.bridge_connected, 'configured': config['ready'],
                'config_name': config['name'], 'session': bool(self.session),
                'reply_mode': self.reply_mode, 'error': self.error,
                'transcript': list(self.transcript)}

    def _config_view(self):
        try:
            view = self.store.view() if self.store is not None else {}
        except Exception:  # noqa: BLE001 —— 配置读不出来按未配置处理
            view = {}
        current = next((item for item in view.get('connections', [])
                        if item.get('id') == view.get('current_id')), None)
        ready = bool(current and current.get('provider') == 'doubao_realtime' and current.get('ready'))
        return {'ready': ready, 'name': (current or {}).get('name') or ''}

    def _config_private(self):
        view = self.store.view()
        current = next((item for item in view.get('connections', [])
                        if item.get('id') == view.get('current_id')), None)
        if not current or current.get('provider') != 'doubao_realtime' or not current.get('ready'):
            raise ActionRefused('先在设置里把豆包实时语音连接配好并设为当前')
        item, _generation = self.store.private(current['id'], current['revision'])
        voice = (item.get('model') or '').strip() or DEFAULT_VOICE
        return item['api_key'], voice

    # ---- duck-echo 桥 ----
    async def _bridge_loop(self):
        while not self.stopped.is_set():
            try:
                reader, writer = await open_conn(self.bridge_addr)
            except (Unreachable, OSError, ValueError) as error:
                self.bridge_connected = False
                self._emit()
                await asyncio.sleep(2.0)
                continue
            self.bridge_connected = True
            self.bridge_writer = writer
            self.error = None
            self._emit()
            try:
                while not self.stopped.is_set():
                    line = await reader.readline()
                    if not line:
                        break
                    try:
                        message = json.loads(line)
                    except ValueError:
                        continue
                    try:
                        await self._bridge_event(message)
                    except asyncio.CancelledError:
                        raise
                    except Exception:  # noqa: BLE001 —— 单个事件绝不拖垮桥的读循环
                        LOG.exception('bridge event failed')
            except (Unreachable, OSError, ValueError, ConnectionError):
                pass
            finally:
                self.bridge_connected = False
                self.bridge_writer = None
                try:
                    writer.close()
                except Exception:  # noqa: BLE001
                    pass
                await self._end_session('语音服务断开了')
                self._emit()

    async def _bridge_event(self, message):
        kind = message.get('type')
        if kind == 'state':
            if message.get('dialogue') is True:
                if self.session is None and not self._starting:
                    asyncio.create_task(self._start_session())
            else:
                asyncio.create_task(self._end_session('对话已关闭'))
        elif kind == 'pcm':
            session = self.session
            if session is not None:
                try:
                    await session.append_audio(base64.b64decode(message.get('data') or ''))
                except (WsClosed, OSError, ValueError):
                    pass
        # 旧版桥的 mute/unmute 行不再出现；即便收到也直接忽略（无状态机可切）

    async def bridge_send(self, message):
        writer = self.bridge_writer
        if writer is None or writer.is_closing():
            LOG.warning('bridge_send dropped %s: writer %s', message.get('method'),
                        'none' if writer is None else 'closing')
            return
        try:
            writer.write((json.dumps(message, ensure_ascii=False, separators=(',', ':')) + '\n').encode())
            await writer.drain()
            if message.get('method') in ('tts', 'tts_end', 'quack'):
                LOG.warning('bridge_send %s ok', message.get('method'))
        except (OSError, ValueError) as error:
            LOG.warning('bridge_send %s FAILED: %s', message.get('method'), str(error)[:120])

    # ---- 云端会话 ----
    async def _start_session(self):
        async with self.state_lock:
            if (self.session is not None or self.stopped.is_set() or self._starting):
                return
            self._starting = True
            self.session_generation += 1
            generation = self.session_generation
        try:
            try:
                api_key, voice = self._config_private()
            except Exception as error:  # noqa: BLE001 —— 配置问题按不可用处理
                self.error = str(error)[:240]
                LOG.warning('dialogue: session start aborted (config): %s', self.error)
                self._emit()
                await self._duck_dialogue_off()
                return
            ws = None
            for attempt in (1, 2, 3):
                try:
                    ws = await self.ws_connect(WSS_URL, headers={'X-Api-Key': api_key})
                    break
                except (WsClosed, OSError, ValueError, asyncio.TimeoutError) as error:
                    LOG.warning('dialogue: cloud connect attempt %d failed: %s', attempt, str(error)[:160])
                    if attempt < 3 and not self.stopped.is_set():
                        await asyncio.sleep(3)
            if ws is None:
                self.error = '连不上豆包实时语音（已重试 3 次），检查鸭子网络后重新开对话'
                LOG.warning('dialogue: session start aborted (connect)')
                self._emit()
                await self._duck_dialogue_off()
                return
            session = RealtimeSession(ws, self)
            self.session = session
            self.error = None
            self.transcript = []
            LOG.warning('dialogue: cloud session started (%s mode)', self.reply_mode)
            self._emit()
            try:
                await session.send({'type': 'session.create', 'session': {
                    'model': MODEL_ID,
                    'instructions': instructions_with_mode(self.reply_mode),
                    'audio': {'input': {'format': {'type': 'pcm', 'rate': INPUT_RATE}},
                              'output': {'format': {'type': 'pcm_s16le', 'rate': OUTPUT_RATE},
                                         'voice': voice}},
                    'tools': TOOLS}})
            except Exception as error:  # noqa: BLE001 —— 建会话失败按断开处理
                self.session = None
                self.error = f'会话建立失败：{error}'[:240]
                LOG.warning('dialogue: session.create failed: %s', self.error)
                await session.close()
                self._emit()
                return
            # 事件循环必须是独立任务：桥的读循环还要继续收 PCM / 开关
            self._session_task = asyncio.create_task(self._run_session(session, generation))
        finally:
            self._starting = False

    async def _run_session(self, session, generation):
        try:
            while generation == self.session_generation and self.session is session:
                try:
                    await session.run()
                    break                      # 云端正常收尾
                except asyncio.TimeoutError:
                    await session.close()
                    self.error = '对话空闲太久，已自动结束（省话费）'
                    break
                except (WsClosed, OSError, ValueError) as error:
                    await session.close()
                    if generation != self.session_generation or self.session is not session:
                        break
                    self.error = f'语音会话断开：{error}'[:240]
                    break
        finally:
            self._starting = False
            if self.session is session:
                self.session = None
            await self.bridge_send({'method': 'stop_output'})
            self._emit()

    async def _end_session(self, reason):
        async with self.state_lock:
            session, self.session = self.session, None
            self.session_generation += 1
            task, self._session_task = self._session_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, 2)
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001 —— 收尾任务里什么错都不再往外抛
                pass
        if session is not None:
            await session.close()
            LOG.warning('dialogue: session ended (%s)', reason or 'normal')
            if reason:
                self.error = reason
            self._emit()

    async def _duck_dialogue_off(self):
        """云端起不来时关掉 duck-echo 的对话开关，麦克风不再白白流动。"""
        import socket as _socket
        if not hasattr(_socket, 'AF_UNIX'):
            return                      # Windows 开发机上没有；只在鸭子上生效
        try:
            with _socket.socket(_socket.AF_UNIX) as client:
                client.settimeout(0.4)
                client.connect('/run/duck-echo/control.sock')
                client.sendall(json.dumps({'method': 'set', 'dialogue': False}).encode() + b'\n')
                client.recv(64)
        except (OSError, ValueError):
            pass

    # ---- 网页 / 工具 ----
    def set_reply_mode(self, mode):
        if mode not in ('human', 'quack'):
            return False
        self.reply_mode = mode
        LOG.warning('dialogue: reply mode -> %s (set from web)', mode)
        self._emit()
        return True

    def _record(self, role, text, final=False):
        text = str(text)[:MAX_TEXT]
        if self.transcript and self.transcript[-1]['role'] == role and not final:
            self.transcript[-1]['text'] = text
        else:
            self.transcript.append({'role': role, 'text': text})
            self.transcript = self.transcript[-TRANSCRIPT_TURNS:]
        self._emit()

    def _emit(self):
        if self.broadcast is not None:
            try:
                self.broadcast({'t': 'dialogue', 'dialogue': self.snapshot()})
            except Exception:  # noqa: BLE001 —— 广播失败不影响语音链路
                pass

    async def _dispatch_tool(self, call_id, name, arguments, session):
        try:
            parsed = json.loads(arguments) if isinstance(arguments, str) and arguments else {}
            if not isinstance(parsed, dict):
                raise ValueError('参数不是对象')
        except ValueError:
            await session.tool_result(call_id, '参数格式不对')
            return
        if name == 'set_reply_mode':
            mode = parsed.get('mode')
            if mode in ('human', 'quack') and mode != self.reply_mode:
                self.reply_mode = mode
                LOG.warning('dialogue: reply mode -> %s (set by cloud tool)', mode)
                self._emit()
                await session.tool_result(call_id, '已切换')
            else:
                await session.tool_result(call_id, '本来就是这个模式')
            return
        try:
            result = await self.actions.execute(name, parsed)
            await session.tool_result(call_id, result)
        except ActionRefused as error:
            await session.tool_result(call_id, f'没做成：{error}')
        except (Unreachable, Timeout, RpcError) as error:
            await session.tool_result(call_id, f'主程序没配合：{error}')
        except Exception:  # noqa: BLE001 —— 工具崩了也要回话，云端才不会挂着等
            LOG.exception('dialogue tool failed')
            await session.tool_result(call_id, '内部错误')
