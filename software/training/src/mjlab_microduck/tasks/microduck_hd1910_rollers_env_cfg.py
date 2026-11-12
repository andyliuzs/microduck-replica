"""HD1910 (Feetech M6) actuator baseline on the roller skate velocity task.

Combines the roller skate recipe (roller-blade geometry, wheel_speed task
rewards, 61D observation layout) with the HD1910 velocity baseline's actuator
swap: LuwuDynamics' public 1910 M6 BAM model plus the Feetech controller
simulation (forward kp, supply-voltage drop, communication delay). Parameter
provenance: robot/hd1910/. This does not replace the robot's measured mass,
inertia, calibration, or runtime gain/IMU integration.

com_height_target uses the corrected roller band ([0.125, 0.145] m, from
upstream fix/roller-com-height-band: the original [0.0935, 0.1235] band
rewarded crouching below the roller HOME height; measured roller HOME trunk
z ≈ 0.1386 m, spawn z 0.1335-0.1435 m — consistent with the env's reset_base
z range). The XL330 rollers task keeps its original band untouched.
"""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from mjlab.envs import ManagerBasedRlEnvCfg

from mjlab_microduck.actuator.feetech_bam import FeetechBamActuatorCfg
from .microduck_velocity_rollers_env_cfg import (
    MicroduckRollersRlCfg,
    make_microduck_velocity_rollers_env_cfg,
)


HD1910_M6_JSON = Path(__file__).resolve().parents[1] / "robot" / "hd1910" / "1910_m6.json"

COM_HEIGHT_MIN = 0.125
COM_HEIGHT_MAX = 0.145


def make_microduck_hd1910_rollers_env_cfg(
    play: bool = False,
) -> ManagerBasedRlEnvCfg:
    cfg = make_microduck_velocity_rollers_env_cfg(play=play)
    # MICRODUCK_WALK_ROLLERS_ROBOT_CFG is a module-level EntityCfg shared by
    # other tasks. Copy before replacing actuators, including nested home-pose
    # dictionaries (same discipline as the HD1910 velocity baseline).
    robot = deepcopy(cfg.scene.entities["robot"])
    assert robot.articulation is not None
    robot.articulation.actuators = (
        FeetechBamActuatorCfg(
            json_path=str(HD1910_M6_JSON),
            target_names_expr=(r"^(?!passive_).*",),
            kp_fw=5.0,
            vin_range=(7.4, 8.0),
            vin_drop_gain_range=(0.0, 0.2),
            vin_min=7.0,
            delay_min_lag=3,
            delay_max_lag=6,
        ),
    )
    cfg.scene.entities["robot"] = robot

    cfg.rewards["com_height_target"].params["target_height_min"] = COM_HEIGHT_MIN
    cfg.rewards["com_height_target"].params["target_height_max"] = COM_HEIGHT_MAX
    return cfg


MicroduckHD1910RollersRlCfg = replace(
    deepcopy(MicroduckRollersRlCfg),
    experiment_name="microduck_hd1910_rollers",
    run_name="hd1910_m6_luwu_rollers",
    logger="tensorboard",
)
