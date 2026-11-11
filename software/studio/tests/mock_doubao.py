"""本地 mock 豆包实时语音服务：同一套事件子集，给开发与测试闭环用。

不是官方服务的完整实现，只覆盖 Studio 会用到的事件：
  session.create -> session.created
  input_audio_buffer.append（只计数）
  input_audio_mute/unmute.commit -> 只记录
  conversation.item.create(role=tool) -> 只记录
  每收到约 1 秒音频 -> 识别一句话 -> 回文字 + 工具调用(可选) + response.done
  session.close -> 关连接

用法（开发联调）：
  cd software/studio && python -m tests.mock_doubao [--port 18086] [--tool]
"""
import argparse
import asyncio
import base64
import hashlib
import json
import os
import struct

GUIDANCE = "你收到的是 mock 服务，不是真豆包。"


def accept_key(key):
    return base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()


async def read_frame(reader):
    """服务器视角：读一个客户端帧（带掩码），返回 (opcode, payload)。"""
    header = await reader.readexactly(2)
    first, second = header[0], header[1]
    opcode, length = first & 0x0F, second & 0x7F
    if length == 126:
        length = struct.unpack('>H', await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack('>Q', await reader.readexactly(8))[0]
    mask = await reader.readexactly(4) if second & 0x80 else None
    payload = bytearray(await reader.readexactly(length))
    if mask:
        payload = bytearray(b ^ mask[i % 4] for i, b in enumerate(payload))
    return opcode, bytes(payload)


async def write_frame(writer, opcode, payload):
    header = bytearray([0x80 | opcode])
    if len(payload) < 126:
        header.append(len(payload))
    elif len(payload) < (1 << 16):
        header.append(126)
        header.extend(struct.pack('>H', len(payload)))
    else:
        header.append(127)
        header.extend(struct.pack('>Q', len(payload)))
    writer.write(bytes(header) + payload)
    await writer.drain()


class DoubaoSession:
    """按脚本能走完一轮对话的服务端状态机。"""

    def __init__(self, send_text, log):
        self.send_text, self.log = send_text, log
        self.turns = 0
        self.tools_seen = []
        self.tool_results = []
        self.created = asyncio.Event()

    async def event(self, message):
        kind = message.get('type')
        if kind == 'session.create':
            await self.send_text({'type': 'session.created', 'session': {'id': 'mock-session-1'}})
            self.created.set()
        elif kind == 'input_audio_mute.commit':
            self.log('mute')
        elif kind == 'input_audio_unmute.commit':
            self.log('unmute')
        elif kind == 'conversation.item.create':
            items = message.get('items') or []
            for item in items:
                if item.get('role') == 'tool':
                    self.tool_results.append(item.get('call_id'))
                    self.log(f'tool_result {item.get("call_id")}')
        elif kind == 'input_audio_buffer.append':
            self.turns += 1
            if self.turns == 1:
                await self.reply('你好呀，我是 mock 小鸭子。')
            elif self.turns == 2 and self.tools_seen:
                call_id = 'mock-call-1'
                name, arguments = self.tools_seen[0]
                await self.send_text({'type': 'response.function_call_arguments.done',
                                      'call_id': call_id, 'name': name, 'arguments': arguments})
                await self.reply('我让你动一下。')
            elif self.turns % 3 == 0:
                await self.reply(f'第 {self.turns // 3 + 1} 句话。')
        elif kind == 'session.close':
            raise ConnectionError('session closed by client')

    async def reply(self, text):
        await self.send_text({'type': 'conversation.item.input_audio_transcription.completed',
                              'text': '（mock 识别的话）'})
        await self.send_text({'type': 'response.output_text.delta', 'delta': text})
        await self.send_text({'type': 'response.output_audio.delta',
                              'delta': base64.b64encode(b'\x00\x00' * 240).decode()})
        await self.send_text({'type': 'response.output_audio.done'})
        await self.send_text({'type': 'response.done'})


async def serve(reader, writer, log=print, tool=False):
    """一次连接 = 一个会话；握手后循环分发文本帧。"""
    # --- HTTP upgrade 握手 ---
    key = None
    while True:
        line = await reader.readline()
        if line in (b'\r\n', b'\n', b''):
            break
        if line.lower().startswith(b'sec-websocket-key:'):
            key = line.split(b':', 1)[1].strip().decode()
    if key is None:
        writer.close()
        return
    writer.write((f'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                  f'Sec-WebSocket-Accept: {accept_key(key)}\r\n\r\n').encode())
    await writer.drain()

    async def send_text(obj):
        await write_frame(writer, 0x1, json.dumps(obj, ensure_ascii=False).encode())

    session = DoubaoSession(send_text, log)
    if tool:
        session.tools_seen.append(('duck_action', json.dumps({'action': 'sit'})))
    try:
        while True:
            opcode, payload = await read_frame(reader)
            if opcode == 0x8:
                await write_frame(writer, 0x8, payload[:2] or b'\x03\xe8')
                break
            if opcode == 0x9:
                await write_frame(writer, 0xA, payload)
                continue
            if opcode == 0xA:
                continue
            try:
                message = json.loads(payload.decode())
            except ValueError:
                continue
            await session.event(message)
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        writer.close()


async def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=18086)
    parser.add_argument('--tool', action='store_true', help='第二轮触发 duck_action 坐下工具调用')
    args = parser.parse_args(argv)
    server = await asyncio.start_server(
        lambda r, w: serve(r, w, tool=args.tool), args.host, args.port)
    print(f'mock doubao listening on ws://{args.host}:{args.port} ({GUIDANCE})')
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    asyncio.run(main())
