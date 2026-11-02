"""Real local browser/auth/APIs; only the OS SSH boundary is simulated."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests import test_vpad_e2e as harness

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(harness._node_ok() and harness.EDGE and os.environ.get('STUDIO_E2E', '1') != '0',
                     'requires Node >=22 and Edge')
class SshGuideBrowser(unittest.TestCase):
    def test_headless_setup_existing_access_and_responsive_help(self):
        output = Path(os.environ.get('SSH_GUIDE_E2E_DIR') or tempfile.mkdtemp(prefix='ssh-guide-e2e-'))
        output.mkdir(parents=True, exist_ok=True)
        control = output / 'ssh-fixture.json'
        control.write_text(json.dumps({'enabled': False, 'changes': 0}), encoding='utf-8')
        ports = [harness._port(0) for _ in range(4)]
        robot, config, web, cdp = ports
        processes, streams = [], []
        record = output / 'robotd.jsonl'
        record.write_text('', encoding='utf-8')

        def launch(name, arguments):
            stream = (output / name).open('w', encoding='utf-8')
            streams.append(stream)
            processes.append(subprocess.Popen(arguments, cwd=ROOT,
                env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'SSH_GUIDE_CONTROL': str(control)},
                stdout=stream, stderr=subprocess.STDOUT))

        try:
            launch('fake.log', [sys.executable, '-I', str(ROOT / 'dev/fake_robotd.py'), '--fixture',
                str(ROOT / 'tests/fixtures/now-20261018.jsonl'), '--robotd-port', str(robot),
                '--configd-port', str(config), '--posture', 'holding', '--record', str(record)])
            launch('studio.log', [sys.executable, '-I', str(ROOT / 'tests/ssh_guide_fixture.py'),
                '--listen', f'127.0.0.1:{web}', '--robotd', f'tcp:127.0.0.1:{robot}',
                '--configd', f'tcp:127.0.0.1:{config}', '--servo-sim',
                '--state-dir', str(output / 'state'), '--log-dir', str(output / 'logs')])
            harness._wait_http(f'http://127.0.0.1:{web}/healthz', 'SSH guide Studio')
            launch('edge.log', [harness.EDGE, '--headless=new', '--disable-gpu', '--no-first-run',
                '--no-default-browser-check', f'--remote-debugging-port={cdp}',
                f'--user-data-dir={output / "edge"}', 'about:blank'])
            harness._wait_http(f'http://127.0.0.1:{cdp}/json/version', 'SSH guide Edge')
            result = subprocess.run([harness.NODE, str(ROOT / 'tests/ssh_guide_e2e.mjs'),
                '--url', f'http://127.0.0.1:{web}/', '--cdp', str(cdp), '--control', str(control),
                '--shots', str(output / 'shots')], cwd=ROOT, capture_output=True,
                text=True, encoding='utf-8', timeout=160)
            (output / 'browser.json').write_text(result.stdout, encoding='utf-8')
            (output / 'browser.stderr').write_text(result.stderr, encoding='utf-8')
            self.assertEqual(result.returncode, 0, f'{result.stderr[-4000:]}\nArtifacts: {output}')
            report = json.loads(result.stdout)
            self.assertEqual(report['errors'], [])
            self.assertEqual(report['layouts'], [1440, 390, 320])
            for key in ('entry_and_route', 'password_confirmation', 'session_refreshed', 'ssh_enabled',
                        'existing_access', 'copy_without_secrets', 'copy_fallback', 'retry', 'keys_preserved'):
                self.assertTrue(report[key], key)
            rows = [json.loads(line) for line in record.read_text(encoding='utf-8').splitlines() if line]
            forbidden = {'robot.init', 'robot.enable', 'robot.do', 'robot.head', 'robot.mouth', 'robot.move'}
            self.assertFalse(any(row['method'] in forbidden for row in rows), 'guide must never actuate')
            for path in (output / 'logs').glob('*'):
                if path.is_file():
                    text = path.read_text(encoding='utf-8', errors='replace')
                    self.assertNotIn('fixture-web-pass-A', text)
                    self.assertNotIn('fixture-ssh-pass-B', text)
        finally:
            for process in reversed(processes):
                harness._kill(process)
            for stream in streams:
                stream.close()
