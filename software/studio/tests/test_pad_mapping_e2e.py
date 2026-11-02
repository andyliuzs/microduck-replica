import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from tests import test_vpad_e2e as harness

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(harness._node_ok() and harness.EDGE and os.environ.get('STUDIO_E2E','1')!='0','requires Edge/Node')
class MappingBrowser(unittest.TestCase):
    def test_button_axis_learning_save_reload_and_reset(self):
        output=Path(os.environ.get('PAD_MAPPING_E2E_DIR') or tempfile.mkdtemp(prefix='pad-mapping-e2e-'))
        output.mkdir(parents=True,exist_ok=True)
        source=output/'input.json'
        source.write_text(json.dumps({'seq':0,'buttons':{},'axes':{'0':0,'1':0,'3':0,'4':0,'2':0},'events':[]}),encoding='utf-8')
        robot,config,web,cdp=[harness._port(0) for _ in range(4)]
        processes,streams=[],[]; record=output/'robot.jsonl'
        # Keep the actual capture unchanged: policies.enabled=True describes
        # installed models, while busStatus.policy_enabled=False means stopped.
        fixture=ROOT/'tests/fixtures/now-20261018.jsonl'
        def launch(name,args):
            stream=(output/name).open('w',encoding='utf-8');streams.append(stream)
            processes.append(subprocess.Popen(args,cwd=ROOT,env={**os.environ,'PAD_MAPPING_INPUT':str(source),
                'PYTHONIOENCODING':'utf-8'},stdout=stream,stderr=subprocess.STDOUT))
        try:
            launch('fake.log',[sys.executable,'-I',str(ROOT/'dev/fake_robotd.py'),'--fixture',str(fixture),
                '--robotd-port',str(robot),'--configd-port',str(config),'--posture','holding','--record',str(record)])
            launch('studio.log',[sys.executable,'-I',str(ROOT/'tests/pad_mapping_fixture.py'),'--listen',f'127.0.0.1:{web}',
                '--robotd',f'tcp:127.0.0.1:{robot}','--configd',f'tcp:127.0.0.1:{config}','--servo-sim',
                '--state-dir',str(output/'state'),'--log-dir',str(output/'logs')])
            harness._wait_http(f'http://127.0.0.1:{web}/healthz','mapping Studio')
            launch('edge.log',[harness.EDGE,'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
                f'--remote-debugging-port={cdp}',f'--user-data-dir={output/"edge"}','about:blank'])
            harness._wait_http(f'http://127.0.0.1:{cdp}/json/version','mapping Edge')
            result=subprocess.run([harness.NODE,str(ROOT/'tests/pad_mapping_e2e.mjs'),'--url',f'http://127.0.0.1:{web}/#/pad',
                '--cdp',str(cdp),'--input',str(source),'--shots',str(output/'shots')],cwd=ROOT,
                capture_output=True,text=True,encoding='utf-8',timeout=160)
            (output/'browser.json').write_text(result.stdout,encoding='utf-8')
            (output/'browser.stderr').write_text(result.stderr,encoding='utf-8')
            self.assertEqual(result.returncode,0,f'{result.stderr[-4000:]}\n{output}')
            report=json.loads(result.stdout);self.assertEqual(report['errors'],[])
            self.assertTrue(all(report[k] for k in ('button_swap','axis_calibration','save_reload','reset','no_auto_resume','guarded',
                'duplicate','hats','triggers','deadzone','ownership','cancel_preserves','navigation_cancel','reconnect','background_cancel','edit_swap_save')))
            self.assertEqual(report['widths'],[1440,390,320])
            rows=[json.loads(line) for line in record.read_text(encoding='utf-8').splitlines() if line]
            self.assertFalse(any(r['method'] in {'robot.init','robot.enable','robot.do','robot.head','robot.mouth','robot.move'} for r in rows))
        finally:
            for p in reversed(processes):harness._kill(p)
            for s in streams:s.close()
