"""Private one-request JSON control socket; no PCM, text or robot RPC surface."""
import json
import os
from pathlib import Path
import socket
import stat
import threading

MAX_REQUEST = 8192
DEFAULT_SOCKET = '/run/duck-echo/control.sock'
RUNTIME_ROOT = str(Path(__file__).resolve().parent.parent)


def decode_request(raw):
    if len(raw) > MAX_REQUEST or not raw.endswith(b'\n') or raw.count(b'\n') != 1:
        raise ValueError('expected one JSON line of at most 8192 bytes')
    try:
        return json.loads(raw.decode('utf-8'))
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ValueError('invalid JSON request') from error


class AudioControl:
    def __init__(self, audio, feel, bridge=None):
        self.audio, self.feel, self.bridge = audio, feel, bridge
        self.lock = threading.RLock()

    def status(self):
        voice = getattr(self.audio,'voice',None)
        voice_ready = bool(voice is not None and voice.ready.is_set() and voice.recognizer is not None)
        interaction = getattr(self.audio, 'music', None)
        error = getattr(interaction, 'error', None)
        if self.audio.failed:
            error = 'microphone capture unavailable; enable listening to retry'
        dialogue = bool(getattr(self.audio, 'dialogue_mode', False))
        if self.bridge is not None and dialogue and not self.bridge.status().get('bridge_client'):
            error = 'dialogue bridge has no studio connection'
        last = None
        if voice is not None and hasattr(voice, 'last_view'):
            try:
                last = voice.last_view()
                # 太久以前的指令不再往外说：手机页看到的是「刚刚听到了什么」，不是历史
                if isinstance(last, dict) and last.get('age', 0) > 30:
                    last = None
            except Exception:
                last = None
        return {'listening': bool(self.audio.active), 'music': bool(self.audio.music_mode),
                'dialogue': dialogue,
                'runtime_root':RUNTIME_ROOT,'voice_ready':voice_ready,
                'rhythm': self.feel.snapshot(), 'error': str(error)[:240] if error else None,
                'last': last}

    def request(self, request):
        with self.lock:
            if not isinstance(request, dict):
                return {'ok': False, 'error': 'request must be an object'}
            method = request.get('method')
            if method == 'status' and set(request) == {'method'}:
                return {'ok': True, 'status': self.status()}
            switches = {key: value for key, value in request.items() if key != 'method'}
            if (method != 'set' or not {'listening', 'music', 'dialogue'} & set(switches)
                    or not set(request) <= {'method', 'listening', 'music', 'dialogue'}
                    or any(type(value) is not bool for value in switches.values())):
                return {'ok': False, 'error': 'allowed methods are status and set with boolean listening/music/dialogue'}
            if switches.get('dialogue') is True and self.bridge is None:
                return {'ok': False, 'error': 'dialogue bridge is not configured'}
            if switches.get('listening') is False and (switches.get('music') is True
                                                       or switches.get('dialogue') is True):
                return {'ok': False, 'error': 'music and dialogue require listening'}
            if switches.get('dialogue') is True and switches.get('music') is True:
                return {'ok': False, 'error': 'dialogue and music cannot run together'}
            if request.get('listening') is False:
                if self.bridge is not None and getattr(self.audio, 'dialogue_mode', False):
                    self.bridge.set_enabled(False)
                self.audio.stop(play=False, announce=True)
            else:
                if (request.get('listening') is True or request.get('music') is True
                        or request.get('dialogue') is True) and not self.audio.active:
                    self.audio.start()
                if 'dialogue' in request:
                    if request['dialogue'] and not self.audio.active:
                        return {'ok': False, 'error': 'listening did not start; check the microphone'}
                    self.audio.set_dialogue(request['dialogue'])
                    if self.bridge is not None:
                        self.bridge.set_enabled(request['dialogue'])
                if 'music' in request:
                    if request['music'] and getattr(self.audio, 'dialogue_mode', False):
                        # 显式要听音乐：先把对话关掉（互斥，两个都开只拒绝同一条消息里的组合）
                        self.audio.set_dialogue(False)
                        if self.bridge is not None:
                            self.bridge.set_enabled(False)
                    self.audio.set_music(request['music'])
            return {'ok': True, 'status': self.status()}


class AudioControlServer:
    def __init__(self, control, path=DEFAULT_SOCKET):
        self.control, self.path = control, Path(path)
        self.stopped = threading.Event()
        self.socket = None
        self.thread = None

    def start(self):
        # systemd creates the private runtime directory; never create arbitrary
        # parents or unlink a regular file at a mistaken configured path.
        if self.path.exists():
            if not stat.S_ISSOCK(self.path.lstat().st_mode):
                raise RuntimeError('control socket path is not a socket')
            self.path.unlink()
        server = socket.socket(socket.AF_UNIX)
        try:
            server.bind(str(self.path))
            os.chmod(self.path, 0o600)
            server.listen(4)
            server.settimeout(.2)
        except BaseException:
            server.close()
            raise
        self.socket = server
        self.thread = threading.Thread(target=self._run, name='audio-control', daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stopped.is_set():
            try:
                client, _ = self.socket.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with client:
                client.settimeout(.5)
                try:
                    raw = bytearray()
                    while b'\n' not in raw and len(raw) <= MAX_REQUEST:
                        block = client.recv(min(1024, MAX_REQUEST+1-len(raw)))
                        if not block:
                            break
                        raw.extend(block)
                    response = self.control.request(decode_request(bytes(raw)))
                except (OSError, ValueError) as error:
                    response = {'ok': False, 'error': str(error)[:240]}
                try:
                    client.sendall((json.dumps(response, ensure_ascii=False, allow_nan=False)+'\n').encode())
                except OSError:
                    pass

    def close(self):
        self.stopped.set()
        if self.socket is not None:
            self.socket.close()
        if self.thread is not None:
            self.thread.join(timeout=1)
            self.path.unlink(missing_ok=True)
