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
    def frozen(self,native_source=None,*,bundle_source=None,extra=None):
        if native_source is None:
            native_source=(Path(__file__).resolve().parents[2]/'studio/deploy/native_update.py').read_bytes()
        buffer=io.BytesIO()
        members={'software/studio/deploy/microduck-helper':b'helper','software/studio/deploy/native_update.py':native_source}
        if bundle_source is not None:members['software/studio/deploy/controller_bundle.py']=bundle_source
        members.update(extra or {})
        with tarfile.open(fileobj=buffer,mode='w') as archive:
            for name,data in members.items():
                info=tarfile.TarInfo(name);info.size=len(data);archive.addfile(info,io.BytesIO(data))
        return buffer.getvalue()

    def build(self,native=None,*,native_source=None,padd=None,bundle_source=None,extra=None):
        self.assertIn('native_robotd',__import__('inspect').signature(B.build).parameters,'missing optional native publisher input')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);binary=root/'native';binary.write_bytes(native or b'')
            kwargs={}
            if padd is not None:
                self.assertIn('native_padd',__import__('inspect').signature(B.build).parameters,'missing explicit reviewed padd input')
                padd_file=root/'padd';padd_file.write_bytes(padd);kwargs['native_padd']=padd_file
            def run(argv,**kwargs):
                if argv[0]=='fake-zstd': kwargs['stdout'].write(kwargs['input'])
                if '-S' in argv: Path(argv[argv.index('-x')+1]).write_bytes(b'signature')
            with mock.patch.object(B.subprocess,'check_output',side_effect=['a'*40,self.frozen(native_source,bundle_source=bundle_source,extra=extra)]), mock.patch.object(B.subprocess,'run',side_effect=run), mock.patch.object(B.shutil,'which',return_value='fake-zstd'):
                B.build(root,'HEAD','2026.10.30',root,'secret','public',zstd='fake-zstd',native_robotd=binary if native else None,**kwargs)
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

    def bundle_fixture(self):
        # Synthetic bytes test the publisher boundary, not production ELF acceptance.
        padd=b'publisher-contract-fixture'
        source=f'''import hashlib
def bundle_manifest(version,robotd,padd):
    return {{'schema':'synthetic-controller-contract/1','software_version':version,
             'padd_sha256':hashlib.sha256(padd).hexdigest(),
             'robotd_sha256':hashlib.sha256(robotd).hexdigest(),'frozen_marker':'fixture-only'}}
def validate_bundle(robotd,padd,manifest,version):
    if padd!={padd!r} or hashlib.sha256(robotd).hexdigest()!='725b74cd93660a312970a44879abe5b75e8becf108499a1b8798961e48ca5f00' or manifest!=bundle_manifest(version,robotd,padd):
        raise ValueError('not the reviewed fixture inputs')
'''.encode()
        return padd,source

    def test_companion_requires_matching_explicit_robotd_input(self):
        padd,source=self.bundle_fixture()
        with self.assertRaises(ValueError):self.build(padd=padd,bundle_source=source)

    def test_companion_and_manifest_are_bound_to_signed_suite(self):
        padd,source=self.bundle_fixture()
        files=self.build(self.reviewed_binary(),padd=padd,bundle_source=source)
        manifest=json.loads(files['studio/deploy/native/controller-manifest.json'])
        suite=json.loads(files['suite-version.json'])
        self.assertEqual(manifest['frozen_marker'],'fixture-only')
        self.assertEqual(files['studio/deploy/native/padd'],padd)
        for name in ('robotd','manifest.json','padd','controller-manifest.json'):
            path='studio/deploy/native/'+name
            self.assertEqual(suite['files'][path],hashlib.sha256(files[path]).hexdigest())

    def test_unreviewed_companion_is_refused_by_frozen_validator(self):
        padd,source=self.bundle_fixture()
        with self.assertRaises(ValueError):self.build(self.reviewed_binary(),padd=padd+b'tamper',bundle_source=source)

    def test_companion_cannot_be_injected_by_git_archive_without_explicit_input(self):
        with self.assertRaises(ValueError):
            self.build(extra={'software/studio/deploy/native/padd':b'foreign'})


if __name__=='__main__':unittest.main()
