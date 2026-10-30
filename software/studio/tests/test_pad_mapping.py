import copy
import threading
import unittest

from studio.pad_mapping import MappingError, PadMapping


def device():
    return {'id':'bt-controller-1','name':'测试手柄','bus':5,'vendor':1,'product':2,
            'buttons':[{'code':code,'name':f'BTN_{code}','pressed':False} for code in range(304,320)],
            'axes':[{'code':code,'name':f'ABS_{code}','min':-100,'max':100,'value':0,'flat':0,'fuzz':0}
                    for code in (0,1,3,4)] + [{'code':2,'name':'ABS_Z','min':0,'max':255,'value':0}]
                    +[{'code':code,'name':'HAT','min':-1,'max':1,'value':0,'flat':0,'fuzz':0} for code in (16,17)]}


class Native:
    def __init__(self):
        self.calls=[]
        self.status={'device':device(),'raw':{'seq':0,'buttons':{},'axes':{'0':0,'1':0,'3':0,'4':0,'2':0},'events':[]},
                     'profile':None,'session':None,'mapped':None,'preview':None,'output_blocked':False}
    def call(self, request):
        self.calls.append(copy.deepcopy(request))
        op=request['op']
        if op=='begin':
            self.status.update(output_blocked=True,session={'phase':'learning','remaining_ms':5000})
        if op in ('save','cancel','reset'):
            if op=='save': self.status['profile']={'schema':1,'name':request['name'],'bindings':request['bindings']}
            if op=='reset': self.status['profile']=None
            self.status['session']={'phase':'waiting_neutral','remaining_ms':0}
        result={'ok':True,'version':1,'status':copy.deepcopy(self.status)}
        if op=='begin': result['token']='fixture-private-token'
        return result
    def event(self, kind, code, value):
        raw=self.status['raw']; raw['seq']+=1
        raw['events'].append({'seq':raw['seq'],'kind':kind,'code':code,'value':value})
        raw['buttons' if kind==1 else 'axes'][str(code)]=bool(value) if kind==1 else value


class MappingTest(unittest.TestCase):
    def setUp(self):
        self.native=Native(); self.mapping=PadMapping(self.native)
        self.mapping.handle({'action':'begin'},'page-a')
    def learn_key(self, role, code):
        self.mapping.handle({'action':'learn','role':role},'page-a')
        self.native.event(1,code,1); self.mapping.poll(force=True)
        self.native.event(1,code,0); self.mapping.poll(force=True)
    def test_learns_raw_pressed_code_and_preview_ack(self):
        self.learn_key('south',305)
        view=self.mapping.snapshot('page-a')
        self.assertEqual(view['draft']['south'],{'kind':'key','code':305})
        self.assertTrue(any(c['op']=='preview' for c in self.native.calls))
        self.assertNotIn('fixture-private-token',str(view))
    def test_owner_and_held_key_cannot_be_stolen(self):
        with self.assertRaises(MappingError): self.mapping.handle({'action':'learn','role':'south'},'page-b')
        self.native.event(1,304,1); self.mapping.poll(force=True)
        with self.assertRaises(MappingError): self.mapping.handle({'action':'learn','role':'south'},'page-a')
    def test_duplicate_binding_is_rejected_without_replacing_first(self):
        self.learn_key('south',305); self.learn_key('east',305)
        view=self.mapping.snapshot('page-a')
        self.assertNotIn('east',view['draft']); self.assertIn('已用于',view['error'])
    def test_axis_sweep_requires_both_ends_and_return_to_center(self):
        self.mapping.handle({'action':'learn','role':'lx'},'page-a')
        self.native.event(3,0,90); self.mapping.poll(force=True)
        with self.assertRaises(MappingError): self.mapping.handle({'action':'confirm_axis'},'page-a')
        self.native.event(3,0,-90); self.mapping.poll(force=True)
        self.native.event(3,0,0); self.mapping.poll(force=True)
        self.mapping.handle({'action':'confirm_axis'},'page-a')
        binding=self.mapping.snapshot('page-a')['draft']['lx']
        self.assertEqual((binding['min'],binding['max'],binding['center'],binding['invert']),(-90,90,0,False))
    def test_negative_first_direction_inverts_axis(self):
        self.mapping.handle({'action':'learn','role':'ly'},'page-a')
        for value in (-100,100,0):
            self.native.event(3,1,value); self.mapping.poll(force=True)
        self.mapping.handle({'action':'confirm_axis'},'page-a')
        self.assertTrue(self.mapping.snapshot('page-a')['draft']['ly']['invert'])
    def test_trigger_can_be_digital_and_invalid_device_cancels_capture(self):
        self.learn_key('rt',312)
        self.assertEqual(self.mapping.snapshot('page-a')['draft']['rt']['kind'],'key')
        self.mapping.handle({'action':'learn','role':'south'},'page-a')
        self.native.status['device']=None; self.mapping.poll(force=True)
        self.assertIsNone(self.mapping.snapshot('page-a')['capture'])
        self.assertIn('断开',self.mapping.snapshot('page-a')['error'])
    def test_save_incomplete_does_not_write(self):
        with self.assertRaises(MappingError): self.mapping.handle({'action':'save','name':'我的手柄'},'page-a')
        self.assertFalse(any(c['op']=='save' for c in self.native.calls))
    def test_snapshot_is_memory_only_and_heartbeat_is_explicit(self):
        count=len(self.native.calls)
        self.mapping.snapshot('page-a'); self.mapping.snapshot('page-b')
        self.assertEqual(len(self.native.calls),count)
        self.assertFalse(any(c['op']=='renew' for c in self.native.calls))
        self.mapping.handle({'action':'heartbeat'},'page-a')
        self.assertEqual(self.native.calls[-1]['op'],'renew')
    def test_begin_guard_refusal_never_sends_native_begin(self):
        n=Native()
        def guard(): raise MappingError('请先停下')
        manager=PadMapping(n,guard=guard)
        with self.assertRaises(MappingError): manager.handle({'action':'begin'},'a')
        self.assertFalse(any(c['op']=='begin' for c in n.calls))
    def test_arm_uses_fresh_raw_baseline_not_poll_cache(self):
        self.native.event(1,304,1)  # Pressed before arming, after last worker poll.
        with self.assertRaises(MappingError):self.mapping.handle({'action':'learn','role':'south'},'page-a')
        self.assertNotIn('south',self.mapping.snapshot('page-a')['draft'])
    def test_device_replacement_releases_owner_without_leasing_other_device(self):
        self.native.status['device']=None;self.native.status['session']=None
        self.mapping.poll(force=True)
        self.assertFalse(self.mapping.snapshot('page-a')['mine'])
        self.assertFalse(self.mapping.snapshot('page-a')['owned'])
    def test_all_hat_directions_and_opposite_direction_reuse(self):
        for role,code,value in [('du',17,-1),('dd',17,1),('dl',16,-1),('dr',16,1)]:
            self.mapping.handle({'action':'learn','role':role},'page-a')
            self.native.event(3,code,value);self.mapping.poll(force=True)
            self.native.event(3,code,0);self.mapping.poll(force=True)
            self.assertEqual(self.mapping.snapshot('page-a')['draft'][role],{'kind':'axis_button','code':code,'value':value})
    def test_analog_trigger_and_digital_trigger_are_both_learned(self):
        self.mapping.handle({'action':'learn','role':'lt'},'page-a')
        for value in (255,0):self.native.event(3,2,value);self.mapping.poll(force=True)
        self.mapping.handle({'action':'confirm_axis'},'page-a')
        self.learn_key('rt',313)
        draft=self.mapping.snapshot('page-a')['draft']
        self.assertEqual(draft['lt'],{'kind':'axis','code':2,'min':0,'max':255,'center':0,'invert':False,'deadzone':.04})
        self.assertEqual(draft['rt'],{'kind':'key','code':313})
    def test_syn_dropped_invalidates_capture(self):
        self.mapping.handle({'action':'learn','role':'south'},'page-a')
        self.native.event(0,3,0);self.native.event(1,305,1);self.mapping.poll(force=True)
        self.assertNotIn('south',self.mapping.snapshot('page-a')['draft'])
        self.assertEqual(self.mapping.snapshot('page-a')['capture']['state'],'error')
    def test_history_gap_requires_rearm(self):
        self.mapping.handle({'action':'learn','role':'south'},'page-a')
        self.native.status['raw'].update(seq=300,events=[{'seq':300,'kind':1,'code':305,'value':1}])
        self.mapping.poll(force=True)
        self.assertNotIn('south',self.mapping.snapshot('page-a')['draft'])
        self.assertEqual(self.mapping.snapshot('page-a')['capture']['state'],'error')
    def test_begin_blocks_other_motion_before_native_ack(self):
        n=Native();entered=threading.Event();release=threading.Event();original=n.call
        def delayed(request):
            if request['op']=='begin':entered.set();release.wait(1)
            return original(request)
        n.call=delayed;manager=PadMapping(n)
        worker=threading.Thread(target=lambda:manager.handle({'action':'begin'},'a'));worker.start()
        self.assertTrue(entered.wait(1));self.assertTrue(manager.blocked)
        release.set();worker.join(1);self.assertFalse(worker.is_alive())
    def test_lost_begin_ack_keeps_local_gate_until_fresh_native_status(self):
        n=Native();original=n.call
        def lost_ack(request):
            response=original(request)
            if request['op']=='begin':raise MappingError('reply lost')
            return response
        n.call=lost_ack;manager=PadMapping(n)
        with self.assertRaises(MappingError):manager.handle({'action':'begin'},'a')
        self.assertTrue(n.status['output_blocked']);self.assertTrue(manager.blocked)
        manager.poll(force=True);self.assertTrue(manager.blocked)
        n.status.update(output_blocked=False,session=None);manager.poll(force=True)
        self.assertFalse(manager.blocked)
    def test_required_bindings_can_be_cleared_in_draft_for_swap_but_not_saved_incomplete(self):
        n=Native()
        original={'select':{'kind':'key','code':314},'start':{'kind':'key','code':315},
            **{role:{'kind':'axis','code':code,'min':-100,'max':100,'center':0,'invert':False,'deadzone':.12}
               for role,code in [('lx',0),('ly',1),('rx',3),('ry',4)]}}
        n.status['profile']={'schema':1,'name':'original','bindings':copy.deepcopy(original)}
        manager=PadMapping(n);manager.handle({'action':'begin'},'a')
        for role in ('select','start','lx','ly'):manager.handle({'action':'clear','role':role},'a')
        self.assertEqual(set(manager.snapshot('a')['required_missing']),{'select','start','lx','ly'})
        with self.assertRaises(MappingError):manager.handle({'action':'save','name':'edited'},'a')
        self.assertEqual(n.status['profile']['bindings'],original)
        for role,code in [('select',315),('start',314)]:
            manager.handle({'action':'learn','role':role},'a')
            n.event(1,code,1);manager.poll(force=True);n.event(1,code,0);manager.poll(force=True)
        for role,code in [('lx',1),('ly',0)]:
            manager.handle({'action':'learn','role':role},'a')
            for value in (100,-100,0):n.event(3,code,value);manager.poll(force=True)
            manager.handle({'action':'confirm_axis'},'a')
        saved=manager.handle({'action':'save','name':'edited'},'a')['profile']['bindings']
        self.assertEqual([saved[r]['code'] for r in ('select','start','lx','ly')],[315,314,1,0])
