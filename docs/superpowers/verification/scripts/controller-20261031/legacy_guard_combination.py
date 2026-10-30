"""Original-27 control/API + actual ARM engine + real non-root voice guard.

Process mode uses real owned child processes behind an explicit service fixture.
It never calls host systemctl and is NOT evidence of genuine systemd semantics.
"""
import argparse,hashlib,importlib.util,io,json,os,pwd,grp,runpy,signal,socket,socketserver
import subprocess,sys,tempfile,threading,time
from pathlib import Path

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def demote():os.setgroups([]);os.setgid(65534);os.setuid(65534)
def request(path,value):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(180);connection.connect(str(path));connection.sendall(json.dumps(value).encode()+b'\n')
        with connection.makefile('rb') as reader:return json.loads(reader.readline(1024*1024))

if len(sys.argv)>1 and sys.argv[1]=='worker':
    current,report=map(Path,sys.argv[2:4])
    try:
        probe=socket.socket(socket.AF_NETLINK,socket.SOCK_RAW,socket.NETLINK_ROUTE);probe.close();netlink=True
    except OSError:netlink=False
    report.write_text(json.dumps({'pid':os.getpid(),'uid':os.getuid(),'version':current.resolve().name,'groups':os.getgroups(),'netlink':netlink}))
    while True:time.sleep(1)
if len(sys.argv)>1 and sys.argv[1]=='service-proxy':
    arguments=sys.argv[3:]
    value=request(sys.argv[2],{'args':arguments})
    if value.get('stdout'):sys.stdout.write(value['stdout'])
    raise SystemExit(value['exit'])
if len(sys.argv)>1 and sys.argv[1]=='client':
    print(json.dumps(request(sys.argv[2],{'op':sys.argv[3]})));raise SystemExit(0)
if len(sys.argv)>1 and sys.argv[1]=='engine-launch':
    shims=Path(sys.argv[2])
    for name in ('systemctl','systemd-run'):
        subprocess.run(['/usr/bin/mount','--bind',str(shims/name),'/usr/bin/'+name],check=True)
    os.execvp(sys.argv[3],sys.argv[3:])

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--old-source',type=Path,required=True)
parser.add_argument('--source',type=Path,required=True)
parser.add_argument('--assets',type=Path,required=True)
parser.add_argument('--library-root',type=Path,required=True)
parser.add_argument('--report',type=Path,required=True)
parser.add_argument('--restore-first',action='store_true')
parser.add_argument('--systemd',action='store_true')
args=parser.parse_args()
assert os.geteuid()==0
if args.systemd:
    assert Path('/proc/1/comm').read_text().strip()=='systemd'
    assert Path('/etc/microduck-proof-distro').read_text().strip()=='microduck-systemd-proof-v1'
expected={'updaterd-original27':'d5f9086bae5c2ec10ba75fc2d41c27578236a12d9a6364bffa8d9315fda97fa6',
 '2026.10.27.software-update.tar':'b6543c9f3a2ad6477106410dbed9753be9fa37c61b79ea0350767a18229d0e55',
 '2026.10.31.software-update.tar':'5f6a597abe27d9c4af8e137841c9dcab4b6c4b378f44c8f88f4c7b4f6ae09204',
 'robotd-original27':'edf182edb7bf11aeeeedfdab98170ab2ec48a9ec18417f9b68c744b0a60c6d16',
 'padd-original27':'85fc8051df2ce496abf32bbb5eba3c94c44d875365a8f33a2f53f90facba90db'}
for name,want in expected.items():assert sha(args.assets/name)==want,name
sys.path.insert(0,str(args.old_source))
from bootstrap import bootstrap,profile
from control import Controller,Engine,preflight
from service import Server
from package import unpack_outer
import health
spec=importlib.util.spec_from_file_location('frozen_bundle',args.source/'software/studio/deploy/controller_bundle.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
THIS=Path(__file__).resolve();PY='/usr/bin/python3.11' if Path('/usr/bin/python3.11').exists() else '/usr/bin/python3'
def systemctl(*arguments,check=False):return subprocess.run(['/usr/bin/systemctl',*arguments],capture_output=True,text=True,check=check)
NAMES={'robotd':'microduck-proof-robotd','padd':'microduck-proof-padd','microduck-studio':'microduck-proof-studio',
       'duck-echo':'microduck-proof-voice','mediad':'microduck-proof-media'}
def unit_properties(role):
    result=systemctl('show',NAMES[role],'-p','LoadState,ActiveState,SubState,MainPID,InvocationID,ExecMainStartTimestampMonotonic,User,Group,SupplementaryGroups,StateDirectory,RestrictAddressFamilies,ExecStartPre')
    return dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
class SystemdHandle:
    def __init__(self,role):self.role=role
    @property
    def pid(self):return int(unit_properties(self.role).get('MainPID','0'))
    def poll(self):return None if unit_properties(self.role).get('ActiveState')=='active' else 1
    def terminate(self):systemctl('stop',NAMES[self.role],check=True)
    def wait(self,timeout=5):return 0

class UnixFixture(socketserver.ThreadingUnixStreamServer):
    daemon_threads=True
    def __init__(self,path,callback):
        class Handler(socketserver.StreamRequestHandler):
            def handle(inner):
                value=json.loads(inner.rfile.readline(16384));result=callback(value)
                inner.wfile.write(json.dumps(result).encode()+b'\n')
        super().__init__(str(path),Handler)
        os.chmod(path,0o666)
        threading.Thread(target=self.serve_forever,daemon=True).start()

with tempfile.TemporaryDirectory(prefix='microduck-old-guard-',dir='/var/tmp') as temporary:
    root=Path(temporary);root.chmod(0o755);image=root/'image';image.mkdir()
    current=image/'opt/microduck/software/current'
    engine_process=None;servers=[]
    events=[];processes={};lock=threading.RLock()
    runtime=root/'runtime';runtime.mkdir();os.chown(runtime,65534,65534)
    state=root/'service-state.json'
    guard=image/C.VOICE_GUARD.lstrip('/');marker=image/C.COMPAT.lstrip('/')
    binds=[];unit_paths=[];owned_paths=[];systemd_evidence={}
    def output_path(name):
        return Path('/run/'+NAMES[name]+'/state.json') if args.systemd else runtime/(name+'.json')
    def setup_systemd():
        for name in ('robot','padd','radxa','mediad'):
            try:grp.getgrnam(name)
            except KeyError:subprocess.run(['groupadd','--system',name],check=True)
        for name in ('padd','radxa','mediad'):
            try:pwd.getpwnam(name)
            except KeyError:subprocess.run(['useradd','--system','--no-create-home','--shell','/usr/sbin/nologin','--gid',name,name],check=True)
        for role,unit in NAMES.items():
            user='padd' if role=='padd' else 'mediad' if role=='mediad' else 'root' if role=='robotd' else 'radxa'
            path=Path('/run/systemd/system/'+unit+'.service');assert not path.exists()
            extra='SupplementaryGroups=robot\n' if role=='padd' else 'SupplementaryGroups=nogroup\n' if role in ('duck-echo','microduck-studio') else ''
            if role=='mediad':extra+='NoNewPrivileges=true\nRestrictAddressFamilies=AF_UNIX AF_INET AF_INET6\n'
            path.write_text('[Unit]\nDescription=Disposable Microduck validation fixture\nStartLimitIntervalSec=0\n'
                '[Service]\nType=exec\nUser='+user+'\nGroup='+user+'\nRuntimeDirectory='+unit+'\nRuntimeDirectoryMode=0750\n'
                'ExecStart='+PY+' -I '+str(THIS)+' worker '+str(current)+' /run/'+unit+'/state.json\n'+extra)
            unit_paths.append(path)
        target=Path('/opt/microduck/software');target.mkdir(parents=True,exist_ok=True)
        subprocess.run(['mount','--bind',str(image/'opt/microduck/software'),str(target)],check=True);binds.append(target)
        systemctl('daemon-reload',check=True)
    def install_systemd_owned():
        target=Path(C.VOICE_GUARD);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(C.VOICE_GUARD_PROGRAM);target.chmod(0o644)
        public=Path(C.PUBLIC_STATE);public.mkdir(parents=True,exist_ok=True)
        subprocess.run(['mount','--bind',str(marker.parent),str(public)],check=True);binds.append(public)
        before={r:processes[r].pid for r in ('padd','microduck-studio','duck-echo','mediad')}
        robot_pid=processes['robotd'].pid
        old_media=json.loads(output_path('mediad').read_text());assert old_media['netlink'] is False
        media_exe_sha=sha('/proc/'+str(processes['mediad'].pid)+'/exe')
        for production,body in C.UNITS.items():
            role=production.split('/')[-2].removesuffix('.service.d')
            target=Path('/run/systemd/system/'+NAMES[role]+'.service.d/controller.conf');target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(body);owned_paths.append(target)
        systemctl('daemon-reload',check=True)
        for role in before:assert start(role)==0
        robot_gid=grp.getgrnam('robot').gr_gid
        for role in ('microduck-studio','duck-echo'):
            data=json.loads(output_path(role).read_text());assert robot_gid in data['groups'] and grp.getgrnam('nogroup').gr_gid in data['groups']
        directory=Path('/var/lib/padd');info=directory.stat()
        assert info.st_uid==pwd.getpwnam('padd').pw_uid and info.st_gid==grp.getgrnam('padd').gr_gid and info.st_mode&0o777==0o750
        persistent=directory/'mappings.json';persistent.write_bytes(b'{"schema":1,"profiles":{}}\n');os.chown(persistent,info.st_uid,info.st_gid);persistent.chmod(0o600)
        assert json.loads(output_path('mediad').read_text())['netlink'] is True
        assert sha('/proc/'+str(processes['mediad'].pid)+'/exe')==media_exe_sha
        assert all(processes[r].pid!=pid for r,pid in before.items()) and processes['robotd'].pid==robot_pid
        systemd_evidence.update(before_pids=before,after_pids={r:processes[r].pid for r in before},robot_pid=robot_pid,
            effective={r:unit_properties(r) for r in before},state_directory_uid=info.st_uid,state_directory_gid=info.st_gid,state_directory_mode=oct(info.st_mode&0o777),
            robot_gid=robot_gid,netlink_before=False,netlink_after=True,persistent_profile_sha256=sha(persistent))
        systemd_evidence['fixture_media_executable_sha256_unchanged']=media_exe_sha
    def save_state():
        value={name:{'active':p.poll() is None,'pid':p.pid} for name,p in processes.items()}
        value['events']=events.copy();state.write_text(json.dumps(value))
    def stop(name):
        p=processes.get(name)
        if p and p.poll() is None:p.terminate();p.wait(timeout=5)
    def start(name):
        if args.systemd:
            result=systemctl('restart',NAMES[name]);processes[name]=SystemdHandle(name)
            if result.returncode:
                if name=='duck-echo':
                    props=unit_properties(name)
                    assert 'status=1' in props.get('ExecStartPre',''),props
                    events.append({'kind':'guard','version':current.resolve().name,'uid':pwd.getpwnam('radxa').pw_uid,'exit':1,'effective':props})
                save_state();return 1
            output=output_path(name)
            for _ in range(100):
                if output.exists():break
                time.sleep(.01)
            data=json.loads(output.read_text());assert data['uid']==pwd.getpwnam('root' if name=='robotd' else 'padd' if name=='padd' else 'mediad' if name=='mediad' else 'radxa').pw_uid
            events.append({'kind':'worker','service':name,**data});save_state();return 0
        stop(name)
        if name=='duck-echo' and guard.exists():
            body='''import runpy,sys
def trace(frame,event,arg):
 if event=="exception" and frame.f_code.co_filename==sys.argv[1]:print(type(arg[1]).__name__+": "+str(arg[1]),file=sys.stderr)
 return trace
sys.settrace(trace)
raise SystemExit(runpy.run_path(sys.argv[1])["guard"](sys.argv[2]))'''
            result=subprocess.run([PY,'-I','-c',body,str(guard),str(image)],preexec_fn=demote,capture_output=True,text=True)
            events.append({'kind':'guard','version':current.resolve().name,'uid':65534,'exit':result.returncode,
                           'marker_exists':marker.exists(),'marker_path':str(marker),'marker_sha':sha(marker) if marker.exists() else None,'diagnostic':result.stderr[-600:]})
            if result.returncode:save_state();return 1
        output=output_path(name);output.unlink(missing_ok=True)
        p=subprocess.Popen([PY,'-I',str(THIS),'worker',str(current),str(output)],preexec_fn=demote,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        processes[name]=p
        for _ in range(100):
            if output.exists():break
            if p.poll() is not None:raise RuntimeError('fixture worker exited: '+name)
            time.sleep(.01)
        data=json.loads(output.read_text());assert data['uid']==65534
        events.append({'kind':'worker','service':name,**data});save_state();return 0
    def identities():
        if args.systemd:return {name:unit_properties(name) for name in ('robotd','padd')}
        return {name:{'LoadState':'loaded','ActiveState':'active','SubState':'running','MainPID':str(processes[name].pid),
                      'InvocationID':'fixture-'+str(processes[name].pid),'ExecMainStartTimestampMonotonic':str(processes[name].pid)}
                for name in ('robotd','padd')}
    def service_call(value):
        with lock:
            words=value['args'];events.append({'kind':'service-command','args':words})
            if args.systemd and words and words[0] in ('show','is-active','reset-failed') and all(not w in NAMES or w in ('microduck-studio','duck-echo') for w in words[1:]):
                result=systemctl(*[NAMES.get(w,w) for w in words]);return {'exit':result.returncode,'stdout':result.stdout}
            if words and words[0]=='reset-failed' and set(words[1:])<={'microduck-studio','duck-echo'}:return {'exit':0}
            if words and words[0]=='restart' and set(words[1:])<={'microduck-studio','duck-echo'}:
                outcomes=[start(name) for name in words[1:]];return {'exit':max(outcomes,default=0)}
            return {'exit':1}
    manager_socket=root/'services.sock';servers.append(UnixFixture(manager_socket,service_call))
    shims=root/'shims';shims.mkdir()
    (shims/'systemctl').write_text('#!'+PY+'\nimport os,sys\nos.execv('+repr(PY)+','+repr([PY,'-I',str(THIS),'service-proxy',str(manager_socket)])+'+sys.argv[1:])\n')
    (shims/'systemd-run').write_text('#!/bin/sh\nexit 1\n')
    for path in shims.iterdir():path.chmod(0o755)
    env={**os.environ,'PATH':str(shims)+':'+os.environ['PATH']}
    engine_log=(root/'engine.log').open('w')
    try:
        engine=args.assets/'updaterd-original27'
        prefix=['qemu-aarch64','-L',str(args.library_root)]
        if args.systemd:prefix=['unshare','--mount','--propagation','private',PY,'-I',str(THIS),'engine-launch',str(shims),*prefix]
        bootstrap(image,args.assets/'2026.10.27.software-update.tar',args.old_source/'release.pub',engine,
                  prefix,offline=True)
        native=image/'opt/robot/feetech-ft5-r5';native.mkdir(parents=True)
        for role in ('robotd','padd'):(native/role).write_bytes((args.assets/(role+'-original27')).read_bytes())
        cache=root/'candidate'
        with (args.assets/'2026.10.31.software-update.tar').open('rb') as incoming:unpack_outer(incoming,cache)
        if args.systemd:setup_systemd()
        for role in ('robotd','padd','microduck-studio','duck-echo',*(['mediad'] if args.systemd else [])):assert start(role)==0
        initial=identities()
        probe=root/'health.py'
        probe.write_text('import json,sys\nfrom pathlib import Path\ns=json.loads(Path('+repr(str(state))+').read_text())\n'
            'raise SystemExit(0 if all(s[n]["active"] for n in ("microduck-studio","duck-echo")) else 1)\n')
        config=root/'engine.toml'
        config.write_text(profile(image).replace('action = "none"','action = "restart"\nunits = ["microduck-studio", "duck-echo"]')
            .replace('probe = "none"','probe = "command"\nprogram = '+json.dumps(PY)+'\nargs = ['+json.dumps(str(probe))+']\ntimeout = "2s"'))
        engine_socket=root/'engine.sock'
        engine_process=subprocess.Popen([*prefix,str(engine),'--config',str(config),
            '--socket',str(engine_socket),'--robot-socket',str(root/'absent-robot.sock')],env=env,stdout=engine_log,stderr=engine_log)
        api=Engine(str(engine_socket))
        for _ in range(100):
            if engine_socket.exists():
                try:api.call('update.status');break
                except (OSError,ValueError):pass
            if engine_process.poll() is not None:raise RuntimeError('actual ARM engine exited')
            time.sleep(.05)
        assert api.call('update.apply',{'component':'software','target':{'exact':'2026.10.31'},'options':{'from_dir':str(cache)}})['outcome']=='applied'
        assert current.resolve().name=='2026.10.31' and identities()==initial
        for role in ('robotd','padd'):(native/role).write_bytes((current/'studio/deploy/native'/role).read_bytes())
        guard.parent.mkdir(parents=True);guard.write_bytes(C.VOICE_GUARD_PROGRAM);guard.chmod(0o644)
        marker.parent.mkdir(parents=True);marker.write_bytes(C.COMPAT_BYTES);marker.chmod(0o644)
        if args.systemd:
            install_systemd_owned();initial=identities()
        assert start('duck-echo')==0
        marker.parent.chmod(0o700);assert start('duck-echo')==1
        marker.parent.chmod(0o755);assert start('duck-echo')==0
        profile_file=image/'var/lib/padd/mappings.json';profile_file.parent.mkdir(parents=True)
        profile_file.write_bytes(b'{"schema":1,"profiles":{}}\n');profile_file.chmod(0o600);saved_profile=sha(profile_file)
        cycle=0
        def robot(value):
            global cycle
            cycle+=1
            if value['method']=='robot.busStatus':
                result={'mode':'motion','phase':'control','homed':True,'policy_enabled':False,'fresh_sample':True,'all_joints_fresh':True,
                    'cycle':cycle,'native':{'joints':[{'id':i,'feedback_fresh':True,'sample_age_ms':1,'velocity_rad_s':0,'position_rad':0} for i in range(15)]}}
            else:result={'battery':{'volts':7.8,'percent':70}}
            return {'jsonrpc':'2.0','id':value['id'],'result':result}
        robot_socket=root/'robot.sock';servers.append(UnixFixture(robot_socket,robot))
        studio_socket=root/'studio.sock';servers.append(UnixFixture(studio_socket,lambda value:{'ready':True}))
        voice_socket=root/'audio.sock';servers.append(UnixFixture(voice_socket,lambda value:{'ok':True,'status':{'listening':False,'music':False}}))
        control_config={'state_dir':str(root/'control-state'),'marker':str(root/'control-run/installing'),'robot_socket':str(robot_socket),
                        'studio_socket':str(studio_socket),'audio_socket':str(voice_socket)}
        health.identities=identities
        controller=Controller(control_config['state_dir'],api,lambda:preflight(control_config),marker=control_config['marker'])
        control_socket=root/'control.sock';server=Server(controller,control_socket,{0,65534},65534)
        threading.Thread(target=server.serve,daemon=True).start()
        for _ in range(100):
            if control_socket.exists():break
            time.sleep(.01)
        def direct_rollback():
            response=subprocess.run([PY,'-I',str(THIS),'client',str(control_socket),'rollback'],preexec_fn=demote,capture_output=True,text=True,check=True)
            assert json.loads(response.stdout)['ok'] is True
            end=time.monotonic()+80
            while controller.busy and time.monotonic()<end:time.sleep(.03)
            assert not controller.busy,'old control rollback did not settle'
            return dict(controller.job)
        # Native restoration is a fixed-file fixture here, not execution of the
        # production root transaction. That transaction is tested separately.
        if args.restore_first:
            for role in ('robotd','padd'):(native/role).write_bytes((args.assets/(role+'-original27')).read_bytes())
            assert sha(native/'padd')==expected['padd-original27'] and sha(native/'robotd')==expected['robotd-original27']
            marker.unlink();assert not marker.exists()
            if args.systemd:
                for path in owned_paths:path.unlink()
                systemctl('daemon-reload',check=True)
                for role in ('padd','microduck-studio','duck-echo','mediad'):assert start(role)==0
                assert sha(Path('/var/lib/padd/mappings.json'))==systemd_evidence['persistent_profile_sha256']
                initial=identities()
            events.append({'kind':'restore-fixture-marker-removed','path':str(marker)})
        checkpoint=len(events);first=direct_rollback()
        if args.restore_first:
            assert current.resolve().name=='2026.10.27' and processes['duck-echo'].poll() is None,first
            assert json.loads(output_path('duck-echo').read_text())['version']=='2026.10.27'
        else:
            assert any(e.get('kind')=='guard' and e.get('version')=='2026.10.27' and e.get('exit')!=0 for e in events[checkpoint:])
            assert not any(e.get('kind')=='worker' and e.get('service')=='duck-echo' and e.get('version')=='2026.10.27' for e in events[checkpoint:])
            assert current.resolve().name=='2026.10.31' and processes['duck-echo'].poll() is None
        assert sha(profile_file)==saved_profile and identities()==initial
        report={'source':'26150eb61407d3498dc2e2c5d1f9dc3ea130acde','old_control_source':'e382f0741d7dfe4e972605e2843474df7219cade',
            'harness_sha256':sha(THIS),'python':sys.version.split()[0],
            'engine_sha256':sha(engine),'candidate_sha256':sha(args.assets/'2026.10.31.software-update.tar'),
            'direct_client_uid':65534,'voice_guard_uid':pwd.getpwnam('radxa').pw_uid if args.systemd else 65534,'old_control_api_actual':True,'actual_arm_engine':True,
            'new_ui_bypassed':True,'scenario':'restore-first' if args.restore_first else 'guard-denies-bypass',
            'unreadable_marker_denied':True,'expected_final_version':current.resolve().name,
            'profiles_preserved':True,'core_pids_unchanged':True,
            'service_backend':'genuine systemd PID1; fixture daemon bodies' if args.systemd else 'real-child-process fixture; NOT systemd',
            'systemd_evidence':systemd_evidence,'native_restore_backend':'fixed-file fixture; NOT production transaction',
            'preflight_hardware':'synthetic safe robot/studio/audio sockets; original preflight function',
            'rollback_result':first,'events':events}
        args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('events','rollback_result')},indent=2))
    finally:
        args.report.with_suffix('.debug.json').write_text(json.dumps({'current':str(current.resolve()),'events':events},indent=2)+'\n')
        engine_log.flush()
        args.report.with_suffix('.engine.log').write_bytes((root/'engine.log').read_bytes())
        if engine_process and engine_process.poll() is None:engine_process.terminate();engine_process.wait(timeout=10)
        for name in processes:stop(name)
        if args.systemd:
            for path in owned_paths+unit_paths:path.unlink(missing_ok=True)
            systemctl('daemon-reload')
            for path in reversed(binds):subprocess.run(['umount',str(path)],check=True)
            Path(C.VOICE_GUARD).unlink(missing_ok=True)
        for fixture in servers:fixture.shutdown();fixture.server_close()
        engine_log.close()
