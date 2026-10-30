"""Publisher injection is optional, fixed and part of signed suite provenance."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import build_package as B


class NativePackage(unittest.TestCase):
    def frozen(self,native_source=None):
        if native_source is None:
            native_source=(Path(__file__).resolve().parents[2]/'studio/deploy/native_update.py').read_bytes()
        buffer=io.BytesIO()
        with tarfile.open(fileobj=buffer,mode='w') as archive:
            for name,data in {'software/studio/deploy/microduck-helper':b'helper','software/studio/deploy/native_update.py':native_source}.items():
                info=tarfile.TarInfo(name);info.size=len(data);archive.addfile(info,io.BytesIO(data))
        return buffer.getvalue()

    def build(self,native=None,*,native_source=None):
        self.assertIn('native_robotd',__import__('inspect').signature(B.build).parameters,'missing optional native publisher input')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);binary=root/'native';binary.write_bytes(native or b'')
            def run(argv,**kwargs):
                if argv[0]=='fake-zstd': kwargs['stdout'].write(kwargs['input'])
                if '-S' in argv: Path(argv[argv.index('-x')+1]).write_bytes(b'signature')
            with mock.patch.object(B.subprocess,'check_output',side_effect=['a'*40,self.frozen(native_source)]), mock.patch.object(B.subprocess,'run',side_effect=run), mock.patch.object(B.shutil,'which',return_value='fake-zstd'):
                B.build(root,'HEAD','2026.10.30',root,'secret','public',zstd='fake-zstd',native_robotd=binary if native else None)
            with tarfile.open(root/'2026.10.30.tar.zst') as archive:
                return {item.name:archive.extractfile(item).read() for item in archive}

    def test_no_native_input_retains_no_payload(self):
        files=self.build()
        self.assertNotIn('studio/deploy/native/robotd',files)
        self.assertNotIn('studio/deploy/native/manifest.json',files)

    def test_reviewed_actual_arm64_pie_is_injected_with_hash_bound_manifest(self):
        artifact=Path('F:/chengshenzhilu/Robot/Microduck/artifacts/imu-independent-20261030/robotd-independent-imu-arm64')
        if not artifact.exists():
            artifact=Path('/mnt/f/chengshenzhilu/Robot/Microduck/artifacts/imu-independent-20261030/robotd-independent-imu-arm64')
        if not artifact.exists(): self.skipTest('reviewed local release input not present')
        try:
            files=self.build(artifact.read_bytes())
        except ValueError as error:
            self.fail(str(error))
        suite=json.loads(files['suite-version.json']);manifest=json.loads(files['studio/deploy/native/manifest.json'])
        for name in ('studio/deploy/native/robotd','studio/deploy/native/manifest.json'):
            self.assertEqual(suite['files'][name],hashlib.sha256(files[name]).hexdigest())
        self.assertEqual(manifest['sha256'],'725b74cd93660a312970a44879abe5b75e8becf108499a1b8798961e48ca5f00')
        self.assertEqual(manifest['source_revision'],'931ce978f2efb27c157b7a583ee402793131a0d2')
        self.assertEqual(manifest['schema'],'microduck-native-payload/1')
        self.assertEqual(manifest['build'],'0791fcd-feetech-qinmo-control.47')
        self.assertEqual(manifest['official_version'],'0.15.1')
        self.assertEqual(manifest['architecture'],'aarch64')
        self.assertEqual(manifest['software_version'],'2026.10.30')
        self.assertEqual(manifest['size'],5606976)
        self.assertEqual(manifest['model_api'],2)
        self.assertEqual(manifest['ipc_api'],42)
        self.assertEqual(manifest['supported_installed_sha256'],[
            'edf182edb7bf11aeeeedfdab98170ab2ec48a9ec18417f9b68c744b0a60c6d16',
            'febf44e2e5d4e573f4513f25a1ae6480b976c3988dd3d5e7cdfcf84d2a2d5063',
            '3dbbf1723c0315afc15fd9f28787c0cfc194622a67802adcd1f5aa397ea47422'])

    def test_unreviewed_bytes_are_refused(self):
        with self.assertRaises(ValueError): self.build(b'foreign binary')

    def reviewed_binary(self):
        relative='artifacts/imu-independent-20261030/robotd-independent-imu-arm64'
        for root in (Path('F:/chengshenzhilu/Robot/Microduck'),Path('/mnt/f/chengshenzhilu/Robot/Microduck')):
            if (root/relative).is_file():return (root/relative).read_bytes()
        self.skipTest('reviewed local release input not present')

    def test_native_manifest_comes_from_frozen_revision_not_builder_worktree(self):
        source=(Path(__file__).resolve().parents[2]/'studio/deploy/native_update.py').read_bytes()
        altered=source.replace(b"SOURCE = '931ce978f2efb27c157b7a583ee402793131a0d2'",b"SOURCE = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'")
        self.assertNotEqual(source,altered)
        files=self.build(self.reviewed_binary(),native_source=altered)
        self.assertEqual(json.loads(files['studio/deploy/native/manifest.json'])['source_revision'],'b'*40)

    def test_frozen_validator_cannot_be_bypassed_by_valid_builder_worktree(self):
        source=(Path(__file__).resolve().parents[2]/'studio/deploy/native_update.py').read_bytes()
        altered=source.replace(b"REVIEWED_SHA256 = '725b74cd93660a312970a44879abe5b75e8becf108499a1b8798961e48ca5f00'",b"REVIEWED_SHA256 = '1111111111111111111111111111111111111111111111111111111111111111'")
        self.assertNotEqual(source,altered)
        with self.assertRaises(ValueError):self.build(self.reviewed_binary(),native_source=altered)


if __name__=='__main__':unittest.main()
