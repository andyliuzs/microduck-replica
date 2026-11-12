"""HD1910 roller task must use the Feetech model without changing roller conventions."""

import mujoco
import numpy as np
import pytest
from bam.model import load_model
from mjlab.tasks.registry import list_tasks, load_env_cfg, load_rl_cfg


BASE = "Mjlab-Velocity-Flat-MicroDuck-Rollers"
FLAT = f"{BASE}-HD1910"
JOINTS = [
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "neck_pitch", "head_pitch", "head_yaw", "head_roll",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
]


def test_hd1910_rollers_registered():
    assert FLAT in list_tasks()
    assert BASE in list_tasks()  # XL330 rollers task preserved


def test_hd1910_rollers_loads_real_bam_model():
    actuator = load_env_cfg(FLAT).scene.entities["robot"].articulation.actuators[0]
    model = load_model(actuator.json_path)
    assert type(model.actuator).__name__ == "STS3215Actuator"
    assert model.kt.value == pytest.approx(0.6237611235393989)
    assert model.R.value == pytest.approx(4.910191564179625)
    assert model.armature.value == pytest.approx(0.0017819049974475338)
    assert model.load_friction_motor_quad.value > 0
    assert model.load_friction_external_stribeck.value > 0
    assert actuator.kp_fw == 5.0
    assert actuator.vin_min <= actuator.vin_range[0] <= actuator.vin_range[1]


@pytest.mark.parametrize("play", [False, True])
def test_hd1910_rollers_preserves_geometry_pose_and_policy_contract(play):
    cfg = load_env_cfg(FLAT, play=play)
    base = load_env_cfg(BASE, play=play)
    robot = cfg.scene.entities["robot"]
    original = base.scene.entities["robot"]
    model = robot.spec_fn().compile()
    base_model = original.spec_fn().compile()
    joint_names = [model.joint(i).name for i in range(model.njnt)
                   if model.jnt_type[i] == mujoco.mjtJoint.mjJNT_HINGE
                   and not model.joint(i).name.startswith("passive_")]
    assert joint_names == JOINTS
    assert model.nu == 14
    np.testing.assert_array_equal(model.body_mass, base_model.body_mass)
    np.testing.assert_array_equal(model.body_inertia, base_model.body_inertia)
    assert robot.init_state == original.init_state
    assert list(cfg.observations["actor"].terms) == list(base.observations["actor"].terms)
    assert cfg.actions == base.actions
    assert cfg.decimation * cfg.sim.mujoco.timestep == pytest.approx(0.02)
    assert "expand_bam_friction_fields" in cfg.events
    # Passive wheels must stay passive: excluded from actuation, still present.
    wheel_joints = [model.joint(i).name for i in range(model.njnt)
                    if model.joint(i).name.startswith("passive_")]
    assert len(wheel_joints) == 4
    actuator_targets = robot.articulation.actuators[0].target_names_expr
    assert actuator_targets == (r"^(?!passive_).*",)


def test_hd1910_rollers_com_height_band_is_the_corrected_one():
    cfg = load_env_cfg(FLAT)
    base = load_env_cfg(BASE)
    params = cfg.rewards["com_height_target"].params
    base_params = base.rewards["com_height_target"].params
    # Corrected band (upstream fix/roller-com-height-band); base keeps the old one.
    assert params["target_height_min"] == pytest.approx(0.125)
    assert params["target_height_max"] == pytest.approx(0.145)
    assert base_params["target_height_min"] == pytest.approx(0.0935)
    assert base_params["target_height_max"] == pytest.approx(0.1235)


def test_hd1910_rollers_factories_do_not_mutate_other_tasks():
    from mjlab_microduck.tasks.microduck_hd1910_rollers_env_cfg import (
        make_microduck_hd1910_rollers_env_cfg,
    )
    from mjlab_microduck.tasks.microduck_velocity_rollers_env_cfg import (
        make_microduck_velocity_rollers_env_cfg,
    )

    first = make_microduck_hd1910_rollers_env_cfg()
    first_robot = first.scene.entities["robot"]
    first_robot.articulation.actuators[0].kp_fw = 99
    first_robot.init_state.joint_pos[".*left_hip_pitch.*"] = 1.0
    first.rewards["com_height_target"].params["target_height_min"] = 0.0
    second = make_microduck_hd1910_rollers_env_cfg()
    original = make_microduck_velocity_rollers_env_cfg()
    assert second.scene.entities["robot"].articulation.actuators[0].kp_fw == 5.0
    assert second.scene.entities["robot"].init_state == original.scene.entities["robot"].init_state
    assert second.rewards["com_height_target"].params["target_height_min"] == pytest.approx(0.125)
    original_actuator = original.scene.entities["robot"].articulation.actuators[0]
    assert original_actuator.motor_name == "xl330"
    assert original_actuator.kp_fw == 200.0
    assert load_rl_cfg(FLAT).experiment_name != load_rl_cfg(BASE).experiment_name
    assert load_rl_cfg(FLAT).actor.obs_normalization
    assert load_rl_cfg(FLAT).logger == "tensorboard"
