"""Real frozen Rust mapping handler + Studio learner and bundle socket probe.

All mutable paths and injected inputs belong to the existing test-only fixture.
This does not launch a hardware daemon or replace a system service.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import runpy
import sys

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=Path,required=True)
parser.add_argument('--fixture',type=Path,required=True)
parser.add_argument('--dir',type=Path,required=True)
parser.add_argument('--report',type=Path,required=True)
args=parser.parse_args()
expected='a0991b8ffa951013fdac53baeb969c83afb1edc060601e4d15ecdb5af2c13825'
actual=hashlib.sha256(args.fixture.read_bytes()).hexdigest()
assert actual==expected,(actual,expected)
studio=args.source/'software/studio'
sys.path.insert(0,str(studio))
from studio.pad_mapping import MappingClient
spec=importlib.util.spec_from_file_location('frozen_controller_contract',studio/'deploy/controller_bundle.py')
bundle=importlib.util.module_from_spec(spec);spec.loader.exec_module(bundle)
original=MappingClient.call
probes=0
def checked(self,request):
    global probes
    if request.get('op')=='status':
        value=bundle.mapping_status(self.address.removeprefix('unix:'))
        assert value.get('ok') is True and type(value.get('version')) is int and value['version']==1
        assert isinstance(value.get('status'),dict)
        probes+=1
    return original(self,request)
MappingClient.call=checked
output=io.StringIO()
script=studio/'tests/pad_mapping_native_contract.py'
sys.argv=[str(script),'--fixture',str(args.fixture),'--dir',str(args.dir)]
try:
    with contextlib.redirect_stdout(output):runpy.run_path(str(script),run_name='__main__')
except SystemExit as result:
    if result.code not in (0,None):raise
report=json.loads(output.getvalue())
assert len(report)==10 and all(value is True for value in report.values()),report
report={'cases':report,'bundle_socket_probes':probes,'fixture_sha256':actual,
        'source_revision':'26150eb61407d3498dc2e2c5d1f9dc3ea130acde','no_hardware':True}
args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
