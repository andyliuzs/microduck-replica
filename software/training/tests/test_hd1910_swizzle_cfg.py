"""HD1910 swizzle task must use the Feetech model without changing swizzle conventions."""

import mujoco
import numpy as np
import pytest
from bam.model import load_model
from mjlab.tasks.registry import list_tasks, load_env_cfg, load_rl_cfg


BASE = "Mjlab-Velocity-Swizzle-MicroDuck"
FLAT = f"{BASE}-HD1910"
JOINTS = [
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "neck_pitch", "head_pitch", "head_yaw", "head_roll",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
]


def test_hd1910_swizzle_registered():
    assert FLAT in list_tasks()
    assert BASE in list_tasks()  # XL330 swizzle task preserved


def test_hd1910_swizzle_loads_real_bam_model():
    actuator = load_env_cfg(FLAT).scene.entities["robot"].articulation.actuators[0]
    model = load_model(actuator.json_path)
    assert type(model.actuator).__name__ == "STS3215Actuator"
    assert model.kt.value == pytest.approx(0.6237611235393989)
    assert model.R.value == pytest.approx(4.910191564179625)
    assert actuator.kp_fw == 5.0


@pytest.mark.parametrize("play", [False, True])
def test_hd1910_swizzle_preserves_geometry_pose_and_policy_contract(play):
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
    # Swizzle-specific rewards must survive the actuator swap.
    for term in ("leg_symmetry", "grounded", "com_height_target"):
        assert term in cfg.rewards
    assert list(cfg.observations["actor"].terms) == list(base.observations["actor"].terms)
    assert cfg.actions == base.actions
    assert "expand_bam_friction_fields" in cfg.events
    wheel_joints = [model.joint(i).name for i in range(model.njnt)
                    if model.joint(i).name.startswith("passive_")]
    assert len(wheel_joints) == 4


def test_hd1910_swizzle_factories_do_not_mutate_other_tasks():
    from mjlab_microduck.tasks.microduck_hd1910_swizzle_env_cfg import (
        make_microduck_hd1910_swizzle_env_cfg,
    )
    from mjlab_microduck.tasks.microduck_velocity_swizzle_env_cfg import (
        make_microduck_velocity_swizzle_env_cfg,
    )

    first = make_microduck_hd1910_swizzle_env_cfg()
    first_robot = first.scene.entities["robot"]
    first_robot.articulation.actuators[0].kp_fw = 99
    first_robot.init_state.joint_pos[".*left_hip_pitch.*"] = 1.0
    second = make_microduck_hd1910_swizzle_env_cfg()
    original = make_microduck_velocity_swizzle_env_cfg()
    assert second.scene.entities["robot"].articulation.actuators[0].kp_fw == 5.0
    assert second.scene.entities["robot"].init_state == original.scene.entities["robot"].init_state
    original_actuator = original.scene.entities["robot"].articulation.actuators[0]
    assert original_actuator.motor_name == "xl330"
    assert load_rl_cfg(FLAT).experiment_name != load_rl_cfg(BASE).experiment_name
    assert load_rl_cfg(FLAT).logger == "tensorboard"
