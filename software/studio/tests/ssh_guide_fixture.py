"""Loopback browser fixture: never changes the computer's users, SSH or keys."""
import json
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'deps'), str(ROOT)]
from studio import app, helper

control = Path(os.environ['SSH_GUIDE_CONTROL'])
original_build = app.build_app


def build(**kwargs):
    kwargs['ssh_home'] = str(control.parent / 'isolated-home')
    return original_build(**kwargs)


def read():
    return json.loads(control.read_text(encoding='utf-8'))


def status(timeout=10):
    state = read()
    if state.get('unknown'):
        return False, 'status_failed', {}
    return True, 'ssh_status', {'password_login': state.get('enabled', False),
        'ssh_active': state.get('active', True), 'user': 'radxa'}


def password(by, on, password=None, timeout=40):
    state = read()
    if state.get('fail'):
        return False, 'reload_failed', {'msg': '模拟：SSH 服务重载失败，请重试'}
    state.update(enabled=on, changes=state.get('changes', 0) + 1)
    control.write_text(json.dumps(state), encoding='utf-8')
    return True, 'ssh_password_on' if on else 'ssh_password_off', {}


app.build_app = build
helper.available = lambda: True
helper.ssh_status = status
helper.ssh_password = password
sys.argv[0] = str(ROOT / 'run.py')
runpy.run_path(str(ROOT / 'tests' / 'audio_fixture_launcher.py'), run_name='__main__')
