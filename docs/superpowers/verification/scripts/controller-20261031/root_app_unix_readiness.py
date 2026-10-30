"""Production recovery readiness over a real Unix socket to a different UID.

The application and root transaction code come from the frozen source. Robot,
audio and service data remain isolated fixtures; no host services are touched.
"""
import argparse,asyncio,contextlib,importlib.util,json,os,socket,struct,subprocess,sys,tempfile,time
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=Path,required=True)
parser.add_argument('--root',type=Path)
parser.add_argument('--child',action='store_true')
parser.add_argument('--report',type=Path)
args=parser.parse_args()
PY='/usr/bin/python3'
studio=args.source/'software/studio';sys.path[:0]=[str(studio/'deps'),str(studio)]

if args.child:
    from tests.test_updates_native import NativeHttp
    from studio import helper
    async def application():
        fixture=NativeHttp('test_bundle_restore_requires_auth_csrf_and_boolean_confirmation')
        await fixture.asyncSetUp()
        try:
            updates=fixture.updates
            updates.native_state=lambda:helper.native_update_state(root=str(args.root))
            updates.marker=args.root/'software-marker'
            await updates.stop_readiness()
            updates.readiness=args.root/'app-run/update.sock'
            await updates.start_readiness(updates.readiness_snapshot)
            (args.root/'app-run/ready').write_text(str(os.getuid()))
            while not (args.root/'stop').exists():
                fixture.servo.state='opening' if (args.root/'servo-busy').exists() else 'closed'
                await asyncio.sleep(.02)
        finally:
            fixture.servo.state='closed'
            await fixture.asyncTearDown()
    asyncio.run(application());raise SystemExit(0)

assert os.geteuid()==0 and args.report
from tests.test_controller_bundle import BundleTransaction,C,legacy
from unittest import mock
fixture=BundleTransaction();fixture.setUp()
process=None
try:
    class PowerLoss(BaseException):pass
    original=C.BundleTransaction.write
    def die(transaction,path,*values,**fields):
        result=original(transaction,path,*values,**fields)
        if path==C.PREPARED:raise PowerLoss()
        return result
    with mock.patch.object(C.BundleTransaction,'write',die):
        try:fixture.update()
        except PowerLoss:pass
        else:raise AssertionError('fixture did not publish a prepared record')
    root=Path(fixture.tmp);root.chmod(0o755)
    app_run=root/'app-run';app_run.mkdir();os.chown(app_run,65534,65534);app_run.chmod(0o700)
    intent=json.loads(fixture.w.path(C.PREPARED).read_text(encoding='utf-8'))
    assert fixture.w.path(C.PREPARED).stat().st_uid==0
    def demote():os.setgroups([]);os.setgid(65534);os.setuid(65534)
    log=args.report.with_suffix('.child.log').open('w')
    process=subprocess.Popen([PY,'-X','utf8','-I',str(Path(__file__).resolve()),'--child','--source',str(args.source),'--root',str(root)],
                             preexec_fn=demote,stdout=log,stderr=log)
    for _ in range(300):
        if (app_run/'ready').exists():break
        if process.poll() is not None:raise AssertionError('unprivileged real app exited; inspect child log')
        time.sleep(.02)
    endpoint=app_run/'update.sock'
    def ask(body):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.settimeout(3);connection.connect(str(endpoint))
            credentials=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            assert credentials[1]==65534 and credentials[0]==process.pid,credentials
            connection.sendall(json.dumps(body).encode()+b'\n')
            return json.loads(connection.recv(8192))
    normal=ask({'op':'readiness'});assert normal['ready'] is False
    private={'op':'native-recovery-readiness','transaction_id':intent['transaction_id']}
    assert ask(private)['ready'] is True
    assert ask({**private,'transaction_id':'0'*32})['ready'] is False
    with mock.patch.object(legacy.N,'json_socket',side_effect=lambda path,body:ask(body) if path.endswith('/microduck-studio/update.sock') else fixture.socket(path,body)):
        transaction=C.BundleTransaction(legacy.H,fixture.op,fixture.release,legacy.N)
        transaction.owned(intent);transaction.unpublished_readiness(intent);transaction.gate()
    (root/'software-marker').touch();assert ask(private)['ready'] is False;(root/'software-marker').unlink()
    (root/'servo-busy').touch()
    for _ in range(50):
        if ask(private)['ready'] is False:break
        time.sleep(.02)
    else:raise AssertionError('real servo state was ignored')
    (root/'servo-busy').unlink()
    probe='import socket,sys;s=socket.socket(socket.AF_UNIX);s.connect(sys.argv[1])'
    def other_uid():os.setgroups([]);os.setgid(65533);os.setuid(65533)
    denied=subprocess.run([PY,'-I','-c',probe,str(endpoint)],preexec_fn=other_uid,capture_output=True,text=True)
    assert denied.returncode!=0 and 'PermissionError' in denied.stderr
    report={'source':'26150eb61407d3498dc2e2c5d1f9dc3ea130acde','root_client_uid':os.geteuid(),'actual_app_uid':65534,
            'actual_unix_socket':True,'socket_mode':oct(endpoint.stat().st_mode&0o777),'socket_owner':endpoint.stat().st_uid,
            'normal_guard_retained':True,'matching_private_recovery_ready':True,'root_transaction_probe_passed':True,
            'wrong_transaction_refused':True,'software_marker_refused':True,'servo_activity_refused':True,'other_uid_refused':True,
            'application':'real NativeHttp/build_app lifespan, ephemeral loopback port; no port8000','hardware':'synthetic fixtures'}
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
finally:
    if process:
        (Path(fixture.tmp)/'stop').touch()
        try:process.wait(timeout=8)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)
    fixture.doCleanups()
