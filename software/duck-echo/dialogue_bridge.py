"""Single-client audio bridge: mic PCM out to Studio, streamed TTS and quacks in.

Studio owns the cloud WebSocket; duck-echo keeps the microphone, the speaker
and the self-audio suppression that already guards cue playback. The bridge is
one JSON line per message both ways, exactly like control.sock:

  client -> service   {"method":"tts","data":<base64 pcm s16le mono 24 kHz>}
                      {"method":"tts_end"} {"method":"quack","tag":"greet"}
                      {"method":"stop_output"} {"method":"ping"}
  service -> client   {"type":"state","dialogue":bool,"listening":bool}
                      {"type":"pcm","data":<base64 pcm s16le mono 16 kHz, 20 ms>}
                      {"type":"mute"} {"type":"unmute"} {"type":"pong"}

PCM only flows while dialogue is enabled, listening is active and the
microphone is not suppressed (duck speaking). Suppression transitions become
explicit mute/unmute lines so the cloud side can send the matching
input_audio_mute.commit events instead of silently withholding audio.
"""
import base64
import json
import logging
import queue
import socket
import stat
import struct
import threading
import time
from pathlib import Path

LOG = logging.getLogger('duck-echo')
DEFAULT_BRIDGE_SOCKET = '/run/duck-echo/audio.sock'
CLOUD_RATE = 16000          # session.audio.input.format: pcm/16000
TTS_RATE = 24000            # session.audio.output.format: pcm_s16le/24000
TTS_TAIL = 0.4              # keep the mic muted through the speaker decay
MAX_QUEUE_BYTES = 2 * 1024 * 1024    # TTS 突发下发可达数十秒（24k mono ≈ 48 KB/s）;丢最旧仅当 Studio 停止读取

# 48 kHz stereo -> 16 kHz mono: right channel only (same mic channel as the
# local recognizer), then average each group of three samples. Box-average
# first keeps the decimation from folding hiss back into the speech band.
def downsample_16k(raw, channel=1):
    samples = struct.unpack('<%dh' % (len(raw) // 2), raw[:len(raw) // 2 * 2])
    mono = samples[channel::2]
    groups = len(mono) // 3
    out = bytearray(groups * 2)
    for i in range(groups):
        value = mono[i * 3] + mono[i * 3 + 1] + mono[i * 3 + 2]
        struct.pack_into('<h', out, i * 2, max(-32768, min(32767, (value + 1) // 3)))
    return bytes(out)


class StreamPlayer:
    """One aplay process fed chunk by chunk; visible to playback_active()."""

    def __init__(self, backend, rate=TTS_RATE):
        self.backend, self.rate = backend, rate
        self.queue = queue.Queue()
        self.process = None
        self.thread = None

    def start(self):
        self.stop()
        import subprocess, tempfile
        errors = tempfile.TemporaryFile()
        process = subprocess.Popen([
            'aplay', '-q', '-D', self.backend.playback_device, '-t', 'raw',
            '-f', 'S16_LE', '-c', '1', '-r', str(self.rate),
        ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)

        def write():
            try:
                while True:
                    chunk = self.queue.get()
                    if chunk is None:
                        break
                    process.stdin.write(chunk)
                    process.stdin.flush()
            except (OSError, ValueError):
                pass
            finally:
                try:
                    process.stdin.close()
                    process.wait(timeout=2)
                except (OSError, ValueError):
                    pass
                if process.poll() is None:
                    process.kill()
                errors.seek(0)
                message = errors.read().decode(errors='replace').strip()
                errors.close()
                if message:
                    LOG.error('dialogue tts playback: %s', message)

        self.process = process
        LOG.info('dialogue tts: aplay started (24k mono)')
        self.thread = threading.Thread(target=write, name='dialogue-tts', daemon=True)
        self.thread.start()

    def write(self, data):
        if self.process is not None:
            self.queue.put(data)

    def finish(self):
        """优雅收尾：放行哨兵，让写线程把队列里剩余的音频全部灌给 aplay,
        aplay 播完缓冲后随 stdin 关闭自然退出。不杀进程、不清引用——
        active() 在排空期间仍为 True，麦克风持续被本地抑制（防自声回灌），
        aplay 退出后自然恢复。"""
        if self.process is not None:
            self.queue.put(None)

    def stop(self):
        if self.process is not None:
            LOG.info('dialogue tts: aplay stop requested')
            try:
                if self.process.poll() is None:
                    self.queue.put(None)
                    if self.thread is not None:
                        self.thread.join(timeout=2)
                if self.process.poll() is None:
                    self.process.kill()
            finally:
                self.process = None
                self.thread = None

    def active(self):
        return self.process is not None and self.process.poll() is None


class DialogueBridge:
    """Server side of audio.sock; one Studio connection at a time."""

    def __init__(self, audio, quack, clock=time.monotonic, path=DEFAULT_BRIDGE_SOCKET):
        self.audio, self.quack, self.clock, self.path = audio, quack, clock, Path(path)
        self.enabled = False                 # dialogue switch (control socket)
        self.lock = threading.RLock()
        self.send_lock = threading.Lock()
        self.pcm = queue.Queue()
        self.pcm_bytes = 0
        self.client = None
        self.player = StreamPlayer(audio.backend if hasattr(audio, 'backend') else audio)
        self.stopped = threading.Event()
        self.socket = None
        self.thread = None
        self.pump = None

    # -- lifecycle ---------------------------------------------------------
    def start(self):
        if not hasattr(socket, 'AF_UNIX'):
            # 单元测试在 Windows 上也跑（duck_echo.py 的约定）；桥只在鸭子上生效。
            LOG.warning('AF_UNIX unavailable; dialogue bridge stays idle')
            return
        if self.path.exists():
            if not stat.S_ISSOCK(self.path.lstat().st_mode):
                raise RuntimeError('dialogue bridge path is not a socket')
            self.path.unlink()
        server = socket.socket(socket.AF_UNIX)
        try:
            server.bind(str(self.path))
            import os
            os.chmod(self.path, 0o600)
            server.listen(1)
            server.settimeout(.2)
        except BaseException:
            server.close()
            raise
        self.socket = server
        self.thread = threading.Thread(target=self._run, name='dialogue-bridge', daemon=True)
        self.thread.start()
        self.pump = threading.Thread(target=self._pump_loop, name='dialogue-pump', daemon=True)
        self.pump.start()

    def close(self):
        self.stopped.set()
        self._drop_client()
        self.player.stop()
        if self.socket is not None:
            self.socket.close()
        for thread in (self.thread, self.pump):
            if thread is not None:
                thread.join(timeout=1)
        self.path.unlink(missing_ok=True)

    # -- control socket side ----------------------------------------------
    def set_enabled(self, enabled):
        with self.lock:
            self.enabled = bool(enabled)
        self.player.stop()
        self._drain_pcm()

    def _drain_pcm(self):
        # 用自己的 RLock 记账；queue 内部锁归 get/put，两不相干（feed 早期版本在这死锁过）
        with self.lock:
            while True:
                try:
                    dropped = self.pcm.get_nowait()
                except queue.Empty:
                    break
                self.pcm_bytes -= len(dropped)
        self._send_state()

    def status(self):
        with self.lock:
            return {'dialogue': self.enabled, 'bridge_client': self.client is not None}

    # -- observer side (capture thread; must stay quick) -------------------
    def feed(self, raw, timestamp=None):
        with self.lock:
            wanted = self.enabled and self.client is not None
        if not wanted:
            return
        data = downsample_16k(raw)
        with self.lock:
            while self.pcm_bytes + len(data) > MAX_QUEUE_BYTES:
                try:
                    dropped = self.pcm.get_nowait()
                except queue.Empty:
                    break
                self.pcm_bytes -= len(dropped)
            self.pcm.put(data)
            self.pcm_bytes += len(data)

    # -- outbound pump ------------------------------------------------------
    def _pump_loop(self):
        # 无静音状态机：有话发话，没话发零值补空。云端输入看门狗
        # （NoAudioInputTooLong）要求字节持续到达；鸭子说话（TTS/叫声）期间
        # 麦克风被本地抑制、队列自然为空 → 补零，云端听到的就是"安静"。
        zero = base64.b64encode(bytes(CLOUD_RATE // 50 * 2)).decode('ascii')
        while not self.stopped.is_set():
            time.sleep(.02)
            with self.lock:
                client = self.client
                active = self.enabled and getattr(self.audio, 'active', False)
            if client is None:
                continue
            if not active:
                # Listening stopped (R3 click, capture failure): dialogue ends
                # with it, exactly like music mode.
                if self.enabled:
                    self.set_enabled(False)
                continue
            sent_any = False
            while True:
                try:
                    data = self.pcm.get_nowait()
                except queue.Empty:
                    break
                with self.lock:
                    self.pcm_bytes -= len(data)
                self._send({'type': 'pcm', 'data': base64.b64encode(data).decode('ascii')})
                sent_any = True
            if not sent_any:
                self._send({'type': 'pcm', 'data': zero})

    # -- inbound lines from Studio ------------------------------------------
    def _handle(self, request):
        if not isinstance(request, dict):
            return {'ok': False, 'error': 'request must be an object'}
        method = request.get('method')
        if method in ('tts', 'quack'):
            LOG.warning('bridge rx %s (enabled=%s active=%s client=%s)',
                        method, self.enabled, getattr(self.audio, 'active', None), self.client is not None)
        if method == 'ping':
            return {'ok': True}
        if method in ('tts', 'tts_end', 'quack', 'stop_output'):
            if not (self.enabled and getattr(self.audio, 'active', False)):
                return {'ok': False, 'error': 'dialogue is not active'}
        if method == 'tts':
            try:
                data = base64.b64decode(request.get('data') or '', validate=False)
            except (ValueError, TypeError):
                return {'ok': False, 'error': 'tts chunk is not base64'}
            if not data or len(data) > 65536:
                return {'ok': False, 'error': 'tts chunk size invalid'}
            if not self.player.active():
                self.player.start()
            self.player.write(data)
            return {'ok': True}
        if method == 'tts_end':
            # 优雅排空：云端整段音频是突发下发的，喇叭实时消耗；立刻杀 aplay
            # 会把缓冲里没播完的语音切掉。放行哨兵让 aplay 播完自然退出，
            # 排空期间 active() 仍为 True，麦克风继续被本地抑制。
            self.player.finish()
            return {'ok': True}
        if method == 'quack':
            tag = request.get('tag')
            if not isinstance(tag, str) or not 1 <= len(tag) <= 32:
                return {'ok': False, 'error': 'quack tag invalid'}
            try:
                self.quack(tag)
                return {'ok': True}
            except Exception:
                LOG.exception('dialogue quack failed')
                return {'ok': False, 'error': 'quack failed'}
        if method == 'stop_output':
            self.player.stop()
            return {'ok': True}
        return {'ok': False, 'error': 'allowed methods are tts, tts_end, quack, stop_output, ping'}

    # -- socket plumbing -----------------------------------------------------
    def _run(self):
        while not self.stopped.is_set():
            try:
                client, _ = self.socket.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with self.lock:
                if self.client is not None:
                    # Only Studio belongs here; a second connection replaces nothing.
                    try:
                        client.close()
                    except OSError:
                        pass
                    continue
                self.client = client
            LOG.info('dialogue bridge client connected')
            self._send_state()
            with client:
                client.settimeout(.5)
                raw = bytearray()
                while not self.stopped.is_set():
                    try:
                        block = client.recv(4096)
                        if not block:
                            break
                        raw.extend(block)
                        while b'\n' in raw:
                            line, _, rest = bytes(raw).partition(b'\n')
                            raw = bytearray(rest)
                            try:
                                message = json.loads(line.decode('utf-8'))
                            except (UnicodeError, ValueError, RecursionError):
                                with self.send_lock:
                                    try:
                                        client.sendall(b'{"ok": false, "error": "invalid JSON request"}\n')
                                    except OSError:
                                        break
                                continue
                            reply = self._handle(message)
                            if reply is not None:
                                try:
                                    with self.send_lock:
                                        client.sendall((json.dumps(reply, ensure_ascii=False,
                                                                   allow_nan=False) + '\n').encode())
                                except OSError:
                                    break
                            if len(raw) > 262144:
                                break
                    except socket.timeout:
                        continue
                    except (OSError, ValueError):
                        break
            self._drop_client()

    @staticmethod
    def _decode(line):
        if not line or len(line) > 262144:
            return {'ok': False, 'error': 'invalid bridge line'}
        try:
            return json.loads(line.decode('utf-8'))
        except (UnicodeError, ValueError, RecursionError):
            return {'ok': False, 'error': 'invalid JSON request'}

    def _drop_client(self):
        with self.lock:
            client, self.client = self.client, None
        if client is not None:
            try:
                client.close()
            except OSError:
                pass
            LOG.info('dialogue bridge client disconnected')
        self.player.stop()

    def _send_state(self):
        self._send({'type': 'state', 'dialogue': self.enabled,
                    'listening': bool(getattr(self.audio, 'active', False))})

    def _send(self, message):
        with self.lock:
            client = self.client
        if client is None:
            return
        try:
            with self.send_lock:
                client.sendall((json.dumps(message, ensure_ascii=False,
                                           allow_nan=False) + '\n').encode())
        except OSError:
            self._drop_client()
