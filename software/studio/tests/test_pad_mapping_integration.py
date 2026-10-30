"""Real PadOps gates and read-only rendering, with isolated raw input."""
import copy
import json
from pathlib import Path
import time

from tests.test_pad import PadTestBase,P,bus
from tests.test_pad_mapping import Native
from studio.pad_mapping import PadMapping
from studio.robotd import Robotd


def recorded_robot_view(log):
    """Actual robotd JSON-RPC capture, including its two different enabled flags."""
    rows=[json.loads(line) for line in (Path(__file__).parent/'fixtures/now-20261018.jsonl').read_text(encoding='utf-8').splitlines()]
    replies={row['method']:row['reply']['result'] for row in rows
             if row.get('kind')=='reply' and isinstance(row.get('reply',{}).get('result'),dict)}
    rd=Robotd('none','none',log);rd.present=True
    rd.bus.set(replies['robot.busStatus']);rd.policies.set(replies['robot.policies']);rd.health.set(replies['robot.health'])
    rd.state.set(next(row['msg']['params'] for row in rows if row.get('kind')=='notify' and row['msg'].get('method')=='robot.state'))
    return P.robot_view(rd)


class MappingPadIntegration(PadTestBase):
    def setUp(self):
        super().setUp();self.native=Native()
        self.native.status['device'].update(node='/dev/input/event99',unique='98:B6:E9:28:06:09')
        self.ops.mapping=PadMapping(self.native,guard=self.ops._mapping_guard)
        self.recorded=recorded_robot_view(self.log)
        self.robot_ok(**self.recorded)

    def test_recorded_policy_configuration_enabled_but_runtime_stopped_can_begin(self):
        self.assertIs(self.recorded['policies']['enabled'],True)
        self.assertIs(self.recorded['bus']['policy_enabled'],False)
        self.assertNotIn('dynamic',self.recorded['bus'])
        self.assertEqual(self.recorded['posture'],'holding')
        result=self.ops.handle({'op':'mapping','action':'begin'},conn='learner')
        self.assertTrue(result['mine']);self.assertTrue(result['output_blocked'])

    def test_current_robotd_serializer_uses_config_enabled_and_flat_stopped_runtime(self):
        wire=json.loads((Path(__file__).parent/'fixtures/robotd-stopped-wire.json').read_text(encoding='utf-8'))
        self.assertEqual(wire['producer'],'robotd::raw_stream::Bus::report + duck_ipc_proto::PoliciesResult/RobotState')
        self.assertEqual(wire['bus']['build'],'0791fcd-feetech-qinmo-control.47')
        self.assertIs(wire['policies']['enabled'],True)
        self.assertIs(wire['bus']['policy_enabled'],False)
        self.assertNotIn('dynamic',wire['bus'])
        rd=Robotd('none','none',self.log);rd.present=True
        rd.bus.set(wire['bus']);rd.policies.set(wire['policies']);rd.state.set(wire['states'][-1])
        view=P.robot_view(rd)
        self.assertEqual(view['posture'],'holding')
        self.robot_ok(**view)
        result=self.ops.handle({'op':'mapping','action':'begin'},conn='learner')
        self.assertTrue(result['mine']);self.assertTrue(result['output_blocked'])

    def test_begin_refuses_running_unknown_transition_and_stale_bus_evidence(self):
        for changed in ({'policy_enabled':True},{'policy_enabled':None},{'home_recovery':True},
                        {'home_recovery':None},{'torque_off_pending':True},{'homed':False},
                        {'home_start_guard':{'ready':False}},{'phase':'read_error'}):
            with self.subTest(changed=changed):
                view=copy.deepcopy(self.recorded);view['bus'].update(changed)
                self.robot_ok(**view)
                with self.assertRaises(P.Refused):self.ops.handle({'op':'mapping','action':'begin'},conn='learner')
        view=copy.deepcopy(self.recorded);view['bus'].pop('policy_enabled');view['bus']['dynamic']={'policy_enabled':False}
        self.robot_ok(**view)
        with self.assertRaises(P.Refused):self.ops.handle({'op':'mapping','action':'begin'},conn='learner')
        view=copy.deepcopy(self.recorded);view['bus_at']=time.monotonic()-4;self.robot_ok(**view)
        with self.assertRaises(P.Refused):self.ops.handle({'op':'mapping','action':'begin'},conn='learner')
        self.assertFalse(any(call['op']=='begin' for call in self.native.calls))

    def test_confirmed_limp_can_begin_with_policy_configuration_enabled(self):
        view=copy.deepcopy(self.recorded)
        view['bus'].update(homed=False,home_start_guard={'ready':False})
        view['bus']['native']['torque_state_confirmed']=False
        view['posture']='limp';self.robot_ok(**view)
        self.assertTrue(self.ops.handle({'op':'mapping','action':'begin'},conn='learner')['mine'])

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
