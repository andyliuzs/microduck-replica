import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import duck_echo as echo
import voice_commands as voice


class MappingRuntimeTests(unittest.TestCase):
    def setUp(self):
        from pad_mapping import MappingRuntime
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'mapping-state.json'; self.reader=MappingRuntime(self.path)
    def test_voice_explicitly_declares_the_mapping_startup_contract(self):
        self.assertIs(type(getattr(echo,'PADD_MAPPING_CONTRACT',None)),int)
        self.assertEqual(echo.PADD_MAPPING_CONTRACT,1)
    def write(self, **values):
        state={'version':1,'pid':os.getpid(),'output_blocked':False,
               'device':{'id':'controller','node':'/dev/input/event8'},'profile':None,**values}
        self.path.write_text(json.dumps(state),encoding='utf-8');return state
    def test_legacy_missing_file_defaults_and_custom_omission_has_no_r3(self):
        self.assertEqual(self.reader.read()['bindings']['r3'],{'kind':'key','code':318})
        self.write(profile={'bindings':{'select':{'kind':'key','code':305}}})
        view=self.reader.read();self.assertIsNone(view['bindings'].get('r3'))
        self.assertEqual(view['node'],'/dev/input/event8')
    def test_blocked_malformed_and_oversize_fail_closed(self):
        self.write(output_blocked=True);self.assertTrue(self.reader.blocked())
        self.path.write_text('{',encoding='utf-8');self.assertTrue(self.reader.blocked())
        self.path.write_text(' '*65537,encoding='utf-8');self.assertTrue(self.reader.blocked())
    def test_every_profile_change_invalidates_input_baseline_even_same_voice_bindings(self):
        self.write(profile={'bindings':{'r3':{'kind':'key','code':305}}});first=self.reader.read()
        self.write(profile={'bindings':{'r3':{'kind':'key','code':305},'south':{'kind':'key','code':306}}})
        self.assertNotEqual(self.reader.read(),first)
    def test_disappearing_modern_state_never_reenables_legacy_r3(self):
        self.write(profile={'bindings':{}});self.assertNotIn('r3',self.reader.read()['bindings'])
        self.path.unlink();view=self.reader.read()
        self.assertTrue(view['blocked']);self.assertFalse(view.get('legacy'))
        self.assertNotIn('r3',view['bindings'])
    def test_live_padd_with_different_uid_does_not_require_signal_permission(self):
        import pad_mapping
        self.write()
        with patch.object(pad_mapping.os,'name','posix'),patch.object(pad_mapping.os,'kill',side_effect=PermissionError()):
            self.assertFalse(self.reader.read()['blocked'])
    @unittest.skipUnless(os.name=='posix' and os.geteuid()==0,'requires isolated Linux root test process')
    def test_real_linux_reader_with_different_uid_can_read_live_padd_state(self):
        self.write();self.path.parent.chmod(0o755);self.path.chmod(0o644)
        def drop_privileges():
            os.setgroups([]);os.setgid(65534);os.setuid(65534)
        script='''import os,sys
sys.path.insert(0,sys.argv[1])
from pad_mapping import MappingRuntime
try:os.kill(int(sys.argv[3]),0)
except PermissionError:pass
else:raise AssertionError('fixture must deny signal permission')
view=MappingRuntime(sys.argv[2]).read()
assert not view['blocked'] and view['bindings']['r3']['code']==318,view
'''
        result=subprocess.run([sys.executable,'-I','-c',script,str(Path(__file__).resolve().parent),str(self.path),str(os.getpid())],
            preexec_fn=drop_privileges,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_motion_guard_and_lease_recheck_mapping_pause(self):
        self.write(output_blocked=True)
        with patch.object(voice,'PAD_MAPPING',self.reader),patch.object(voice.NATIVE_GUARD,'active',return_value=False):
            self.assertFalse(voice.updates_allowed())
            with self.assertRaises(voice.UpdateLocked):
                with voice.motion_lease(Path(self.tmp.name)/'no-marker'):pass
    def test_installer_and_software_package_include_shared_reader(self):
        import install
        self.assertIn('pad_mapping.py',install.RUNTIME_FILES)
        import importlib.util
        source=Path(__file__).resolve().parents[1]/'updater/package.py'
        spec=importlib.util.spec_from_file_location('updater_package',source)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertIsNotNone(module.runtime_path('software/duck-echo/pad_mapping.py'))
        unit=(Path(__file__).resolve().parent/'duck-echo.service').read_text(encoding='utf-8')
        groups=next(line.split('=',1)[1].split() for line in unit.splitlines() if line.startswith('SupplementaryGroups='))
        self.assertIn('robot',groups)

    def test_native_selected_node_does_not_require_linux_default_r3_capability(self):
        from unittest.mock import mock_open
        with patch.object(echo.glob,'glob',return_value=['/dev/input/event8','/dev/input/event9']), \
                patch.object(echo.os,'O_NONBLOCK',0,create=True),patch.object(echo.os,'open',return_value=4), \
                patch.object(echo.os,'close'),patch.object(echo,'key_bitmap',return_value=bytearray(96)), \
                patch('builtins.open',mock_open(read_data='custom controller')):
            self.assertEqual(echo.devices(),[])
            self.assertEqual(echo.devices('/dev/input/event8'),[{'path':'/dev/input/event8','name':'custom controller'}])


class MappedVoiceInputTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        class Audio:
            voice=None
            def start(inner):self.calls.append('start')
            def stop(inner,play):self.calls.append('stop')
            def expired(inner):return False
            def cancel_processing(inner):self.calls.append('cancel')
            def stop_playback(inner):self.calls.append('playback-stop')
        self.audio=Audio();self.values={};self.state={'node':'/dev/input/event8','blocked':False,
            'bindings':{'r3':{'kind':'key','code':305},'select':{'kind':'axis_button','code':16,'value':-1}}}
        self.control=echo.MappedVoiceInput(self.audio,lambda binding:self.values.get(binding['code'],False))
        self.control.update(self.state)
        self.calls.clear()
    def test_custom_r3_and_hat_select_match_raw_binding_only(self):
        self.control.event(1,318,1);self.assertNotIn('start',self.calls)
        self.control.event(1,305,1);self.assertIn('start',self.calls)
        self.control.event(3,16,-1);self.assertIn('cancel',self.calls)
    def test_pause_cancels_and_requires_release_after_resume(self):
        self.control.event(1,305,1)
        self.values[305]=True;self.control.update({**self.state,'blocked':True})
        self.calls.clear();self.control.event(1,305,1);self.assertEqual(self.calls,[])
        self.control.update(self.state);self.calls.clear()
        self.control.event(1,305,1);self.assertNotIn('start',self.calls)
        self.control.event(1,305,0);self.control.event(1,305,1);self.assertIn('start',self.calls)
    def test_profile_change_rebaselines_held_and_omission_disables(self):
        self.values[306]=True
        changed={**self.state,'bindings':{'r3':{'kind':'key','code':306}}}
        self.control.update(changed);self.calls.clear()
        self.control.event(1,306,1);self.assertNotIn('start',self.calls)
        self.control.event(1,306,0);self.control.event(1,306,1);self.assertIn('start',self.calls)
        self.control.update({**self.state,'bindings':{}});self.calls.clear()
        self.control.event(1,318,1);self.control.event(1,305,1);self.assertNotIn('start',self.calls)
