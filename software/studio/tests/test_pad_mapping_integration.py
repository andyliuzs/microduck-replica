"""Real PadOps gates and read-only rendering, with isolated raw input."""
import copy
import json
import time

from tests.test_pad import PadTestBase,P,bus
from tests.test_pad_mapping import Native
from studio.pad_mapping import PadMapping


class MappingPadIntegration(PadTestBase):
    def setUp(self):
        super().setUp();self.native=Native()
        self.native.status['device'].update(node='/dev/input/event99',unique='98:B6:E9:28:06:09')
        self.ops.mapping=PadMapping(self.native,guard=self.ops._mapping_guard)
        self.robot_ok(posture='holding',policies={'enabled':False})

    def test_active_web_control_is_refused_before_native_pause(self):
        self.ops._driver={'conn':'other','by':'other page','since':time.monotonic(),'seen':time.monotonic()}
        with self.assertRaises(P.Refused):self.ops.handle({'op':'mapping','action':'begin'},conn='learner')
        self.assertFalse(any(c['op']=='begin' for c in self.native.calls))

    def test_all_motion_and_pairing_entrypoints_are_blocked_during_learning(self):
        self.ops.handle({'op':'mapping','action':'begin'},conn='learner')
        for request in ({'op':'stand'},{'op':'walk'},{'op':'key','key':'a'},{'op':'sound','tag':'chirp'},
                        {'op':'mode','mode':'head'},{'op':'sticks','lx':1},{'op':'scan'},
                        {'op':'pair'},{'op':'estop_test','action':'start'},{'op':'audio','listening':True},
                        {'op':'motion','action':'begin_record'}):
            with self.subTest(op=request['op']),self.assertRaises(P.Refused):self.ops.handle(request,conn='learner')
        self.ops.handle({'op':'watch'},conn='learner')

    def test_native_mapped_values_drive_diagram_and_diag_masks_unique(self):
        self.ops._tap_report({'report':'attached','device':copy.deepcopy(self.native.status['device'])})
        self.native.status.update(profile={'schema':1,'name':'saved','bindings':{'select':{'kind':'key','code':305}}},
            mapped={'buttons':{'south':True,'east':False},'axes':{'lx':.8,'ly':0,'rx':0,'ry':0,'lt':0,'rt':0}})
        self.ops.mapping.poll(force=True)
        snapshot=self.ops.snapshot();self.assertTrue(snapshot['live']['buttons']['south'])
        self.assertEqual(snapshot['live']['axes']['lx'],.8)
        self.assertNotIn('98:B6:E9:28:06:09',json.dumps(self.ops.diag()))

    def test_mark_gone_cancels_owned_native_lease(self):
        self.ops.handle({'op':'mapping','action':'begin'},conn='learner')
        self.ops.mark_gone('learner')
        from tests.test_pad import wait_until
        wait_until(lambda:any(c['op']=='cancel' for c in self.native.calls))
        self.assertFalse(self.ops.mapping.snapshot('learner')['mine'])
