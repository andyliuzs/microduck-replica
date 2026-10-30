"""Fixed companion bundle: synthetic bytes and isolated root/service fixtures."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests import test_native_update as legacy

SOURCE=Path(__file__).resolve().parents[1]/'deploy/controller_bundle.py'
C=None
if SOURCE.exists():
    spec=importlib.util.spec_from_file_location('controller_bundle_tests',SOURCE)
    C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)

OLD_PAD,NEW_PAD=legacy.elf(b'pad-old'),legacy.elf(b'pad-new')
SHA=lambda data:hashlib.sha256(data).hexdigest()


class BundleManifest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(C,'controller companion module must exist')
        patch=mock.patch.multiple(C,ROBOTD_SHA256=SHA(legacy.NEW),ROBOTD_SIZE=len(legacy.NEW),
            PADD_SHA256=SHA(NEW_PAD),PADD_SIZE=len(NEW_PAD),PADD_SOURCE='a'*40,
            SUPPORTED_PADD_SHA256=(SHA(OLD_PAD),))
        patch.start();self.addCleanup(patch.stop)

    def test_distinct_manifest_binds_both_binaries_and_all_fixed_unit_bytes(self):
        manifest=C.bundle_manifest('2026.10.31',legacy.NEW,NEW_PAD)
        self.assertEqual(manifest['schema'],'microduck-controller-payload/1')
        self.assertEqual(set(manifest['components']),{'robotd','padd'})
        self.assertEqual(manifest['components']['padd']['sha256'],SHA(NEW_PAD))
        self.assertEqual(set(manifest['units']),set(C.UNITS))
        C.validate_bundle(legacy.NEW,NEW_PAD,manifest,'2026.10.31')

    def test_unknown_pins_wrong_bytes_partial_or_altered_manifest_refuse(self):
        manifest=C.bundle_manifest('2026.10.31',legacy.NEW,NEW_PAD)
        for robot,pad,body,version in ((legacy.OLD,NEW_PAD,manifest,'2026.10.31'),
            (legacy.NEW,OLD_PAD,manifest,'2026.10.31'),(legacy.NEW,NEW_PAD,{**manifest,'extra':True},'2026.10.31'),
            (legacy.NEW,NEW_PAD,manifest,'2026.11.1')):
            with self.assertRaises(ValueError):C.validate_bundle(robot,pad,body,version)
        with mock.patch.object(C,'PADD_SHA256',None),self.assertRaises(ValueError):
            C.validate_bundle(legacy.NEW,NEW_PAD,manifest,'2026.10.31')

    def test_units_add_state_group_network_and_external_legacy_voice_guard(self):
        all_units=b'\n'.join(C.UNITS.values()).decode()
        self.assertIn('StateDirectory=padd',all_units)
        self.assertIn('SupplementaryGroups=robot',all_units)
        self.assertIn('AF_NETLINK',all_units)
        self.assertIn('ExecStartPre=/usr/bin/python3 -I '+C.VOICE_GUARD,all_units)
        self.assertNotIn('ExecStart=',all_units)


class VoiceCompatibility(unittest.TestCase):
    def test_legacy_suite_is_denied_until_explicit_component_restore(self):
        self.assertIsNotNone(C,'controller companion module must exist')
        old={'files':{'duck-echo/duck_echo.py':'a'*64}}
        modern={'contracts':{'padd_mapping':1},'files':{
            'duck-echo/duck_echo.py':'a'*64,'duck-echo/pad_mapping.py':'b'*64}}
        files={'duck-echo/duck_echo.py':b'echo','duck-echo/pad_mapping.py':b'reader'}
        modern['files']={name:SHA(data) for name,data in files.items()}
        self.assertFalse(C.compatible_suite(old,files))
        self.assertTrue(C.compatible_suite(modern,files))
        self.assertFalse(C.compatible_suite({**modern,'contracts':{'padd_mapping':True}},files))
        self.assertFalse(C.compatible_suite(modern,{**files,'duck-echo/duck_echo.py':b'changed'}))

    @unittest.skipUnless(os.name=='posix','requires real POSIX current symlink')
    def test_actual_external_gate_blocks_downgrade_and_survives_release_switch(self):
        self.assertIsNotNone(C)
        namespace={'__name__':'fixture_voice_guard'}
        exec(compile(C.VOICE_GUARD_PROGRAM,'external-voice-guard.py','exec'),namespace)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            marker=root/C.COMPAT.lstrip('/');marker.parent.mkdir(parents=True)
            old=root/'opt/microduck/software/releases/2026.10.27'
            new=old.with_name('2026.10.31')
            for release in (old,new):release.mkdir(parents=True)
            current=old.parent.parent/'current';current.symlink_to('releases/2026.10.27')
            (old/'suite-version.json').write_text(json.dumps({'version':'2026.10.27','files':{}}))
            self.assertEqual(namespace['guard'](temporary),0)
            marker.write_text(json.dumps({'schema':'microduck-controller-compat/1','required':True}))
            self.assertEqual(namespace['guard'](temporary),1)
            files={name:name.encode() for name in C.VOICE_FILES}
            for name,data in files.items():
                path=new/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            (new/'suite-version.json').write_text(json.dumps({'version':'2026.10.31','contracts':{'padd_mapping':1},
                'files':{name:SHA(data) for name,data in files.items()}}))
            current.unlink();current.symlink_to('releases/2026.10.31')
            self.assertEqual(namespace['guard'](temporary),0)
            current.unlink();current.symlink_to('releases/2026.10.27')
            self.assertEqual(namespace['guard'](temporary),1)
            marker.unlink()
            self.assertEqual(namespace['guard'](temporary),0)
