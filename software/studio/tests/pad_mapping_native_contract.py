"""Run Studio's real Python client/learner against padd's test-only Unix server.

Run under Linux, passing the Rust test executable as --fixture. No hardware,
production sockets or system paths are touched. The native fixture owns its
synthetic raw descriptor and uses the production mapping socket handler.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studio.pad_mapping import MappingClient,MappingError,PadMapping


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--fixture',required=True);parser.add_argument('--dir',required=True)
    args=parser.parse_args();folder=Path(args.dir);folder.mkdir(parents=True,exist_ok=True)
    if (folder/'mapping.sock').exists():raise RuntimeError('use a fresh isolated fixture directory')
    report={};log=(folder/'native.log').open('w')
    process=subprocess.Popen([args.fixture,'--exact','mapping::native::tests::cross_language_fixture','--nocapture'],
        env={**os.environ,'PAD_MAPPING_FIXTURE_DIR':str(folder)},stdout=log,stderr=subprocess.STDOUT)
    def until(predicate,label,timeout=5):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if predicate():return
            time.sleep(.02)
        raise AssertionError('timeout '+label)
    try:
        until(lambda:(folder/'ready.json').is_file(),'native fixture ready')
        client=MappingClient('unix:'+str(folder/'mapping.sock'));mapping=PadMapping(client)
        def view():mapping.poll(force=True);return mapping.snapshot('owner')
        def inject(kind=None,code=None,value=None,**special):
            before=client.call({'op':'status'})['status'].get('raw') or {}
            with (folder/'events.jsonl').open('a') as out:
                out.write(json.dumps(special or {'kind':kind,'code':code,'value':value})+'\n');out.flush()
            if not special:
                until(lambda:(client.call({'op':'status'})['status'].get('raw') or {}).get('seq',0)>before.get('seq',0),'raw input')
                mapping.poll(force=True)
            else:time.sleep(.15)
        def handle(action,**extra):return mapping.handle({'action':action,**extra},'owner')
        def key(role,code):
            handle('learn',role=role);inject(1,code,1);inject(1,code,0)
            assert view()['draft'][role]=={'kind':'key','code':code}
        # Give both trigger conventions an explicit released baseline.
        inject(3,2,-100);inject(3,5,100)
        handle('begin');assert view()['output_blocked']
        try:mapping.handle({'action':'heartbeat'},'other');raise AssertionError('ownership bypass')
        except MappingError:pass
        report['owner']=True
        key('south',305);key('east',304);key('select',314);key('start',315);key('r3',307)
        handle('learn',role='west');inject(1,305,1);inject(1,305,0)
        assert 'west' not in view()['draft'] and '已用于' in view()['error'];report['duplicate']=True
        for role,code,value in [('du',17,-1),('dd',17,1),('dl',16,-1),('dr',16,1)]:
            handle('learn',role=role);inject(3,code,value);inject(3,code,0)
            assert view()['draft'][role]=={'kind':'axis_button','code':code,'value':value}
        for role,code,invert in [('lx',3,False),('ly',0,True),('rx',1,False),('ry',4,False)]:
            handle('learn',role=role)
            for value in ([-100,100,0] if invert else [100,-100,0]):inject(3,code,value)
            handle('confirm_axis');assert view()['draft'][role]['invert']==invert
        for role,code,values in [('lt',2,[100,-100]),('rt',5,[-100,100])]:
            handle('learn',role=role)
            for value in values:inject(3,code,value)
            handle('confirm_axis')
        handle('deadzone',role='lx',value=.18)
        inject(1,305,1);assert view()['preview']['buttons']['south']
        assert not view()['preview']['buttons']['east'];inject(1,305,0)
        inject(3,3,10);assert view()['preview']['axes']['lx']==0;inject(3,3,0)
        inject(3,0,-100);assert view()['preview']['axes']['ly']==1;inject(3,0,0)
        inject(3,2,100);assert view()['preview']['axes']['lt']==1;inject(3,2,-100)
        inject(3,5,-100);assert view()['preview']['axes']['rt']==1;inject(3,5,100)
        draft=view()['draft'];saved=handle('save',name='cross-language')
        assert saved['profile']['bindings']==draft;report['analog_trigger_axes_hats_preview_save']=True
        until(lambda:not view()['output_blocked'],'neutral recovery')
        runtime=json.loads((folder/'mapping-state.json').read_text())
        assert runtime['profile']['bindings']==draft and 'token' not in runtime and runtime['output_blocked'] is False
        module_spec=importlib.util.spec_from_file_location('voice_pad_mapping',ROOT.parent/'duck-echo/pad_mapping.py')
        voice_mapping=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(voice_mapping)
        voice=voice_mapping.MappingRuntime(folder/'mapping-state.json').read()
        assert not voice['blocked'] and voice['bindings']['r3']=={'kind':'key','code':307}
        assert voice['bindings']['select']=={'kind':'key','code':314}
        report['runtime_voice_contract']=True
        inject(op='reload');until(lambda:view().get('profile',{}).get('name')=='cross-language','profile disk reload')
        inject(op='disconnect');until(lambda:view().get('device') is None,'disconnect')
        inject(op='attach');until(lambda:view().get('device') is not None,'reconnect')
        inject(3,2,-100);inject(3,5,100)
        until(lambda:not view()['output_blocked'],'reconnected neutral')
        assert view()['profile']['bindings']==draft;report['reload_reconnect']=True
        handle('begin');handle('skip',role='r3');handle('cancel')
        until(lambda:not view()['output_blocked'],'cancel neutral')
        assert view()['profile']['bindings']==draft;report['cancel_keeps_profile']=True
        handle('begin');key('rt',311);handle('save',name='digital-trigger')
        assert view()['profile']['bindings']['rt']=={'kind':'key','code':311};report['digital_trigger']=True
        until(lambda:not view()['output_blocked'],'digital neutral')
        handle('begin')
        for role in ('select','start','lx','ly'):handle('clear',role=role)
        try:handle('save',name='incomplete');raise AssertionError('required draft was saved')
        except MappingError:pass
        key('select',315);key('start',314)
        for role,code in [('lx',0),('ly',3)]:
            handle('learn',role=role)
            for value in (100,-100,0):inject(3,code,value)
            handle('confirm_axis')
        handle('save',name='edited-swap')
        edited=view()['profile']['bindings']
        assert [edited[role]['code'] for role in ('select','start','lx','ly')]==[315,314,0,3]
        report['edit_required_swap']=True
        until(lambda:not view()['output_blocked'],'edited swap neutral')
        handle('begin');handle('reset');until(lambda:not view()['output_blocked'],'reset neutral')
        assert view()['profile'] is None;report['reset']=True
        handle('begin');time.sleep(5.2)
        until(lambda:not view()['mine'],'lease expiry');report['lease_expiry']=True
        print(json.dumps(report,indent=2));return 0
    finally:
        (folder/'stop').touch()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=3)
        log.close()


if __name__=='__main__':raise SystemExit(main())
