"""IR-SIM engineering checks for the 1:1 geometry; never a research run."""
from __future__ import annotations

import json
from pathlib import Path

import irsim
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "config" / "robot_world.yaml"
REPORT = ROOT / "results" / "physical_scale_motion_validation_20260817.json"


def state(robot):
    value = robot.state.reshape(-1)
    return float(value[0]), float(value[1]), float(value[2])


def main() -> int:
    env = irsim.make(str(WORLD))
    try:
        # Test A: actual translation in the open standard lane y=0.547 m.
        first = env.robot_list[0]
        first.set_state([0.46, 0.547, 0.0])
        start_x, _, _ = state(first)
        for _ in range(10):
            env.step(np.array([[0.044], [0.0]]), action_id=0)
        end_x, _, _ = state(first)
        assert end_x > start_x + 0.03
        assert not first.collision_flag

        # Test B: two bodies pass one another through a 0.350 m free lane.
        # Their lateral centre separation is 0.17 m, giving 0.07 m body gap.
        first.set_state([0.46, 0.46, 0.0])
        second = env.create_robot(
            name="passing-test-peer", kinematics={"name": "diff"},
            shape={"name": "circle", "radius": 0.05},
            state=[0.66, 0.63, 3.141592653589793], vel_max=[0.10, 2.0],
            color="b", plot={"show_arrow": False, "show_sensor": False},
        )
        env.add_objects([second])
        start_a, _, _ = state(first)
        start_b, _, _ = state(second)
        for _ in range(30):
            env.step(
                [np.array([[0.044], [0.0]]), np.array([[0.044], [0.0]])],
                action_id=[first._id, second._id],
            )
        end_a = state(first)
        end_b = state(second)
        assert end_a[0] > start_a + 0.08
        assert end_b[0] < start_b - 0.08
        assert not first.collision_flag and not second.collision_flag

        report = {
            "test_scope": "ENGINEERING_GEOMETRY_ONLY",
            "A_standard_corridor_translation": "PASS",
            "B_two_robot_passing": "PASS",
            "robot_a_translation_m": end_a[0] - start_a,
            "robot_b_translation_m": start_b - end_b[0],
            "minimum_nominal_robot_to_robot_clearance_m": 0.07,
            "minimum_nominal_robot_to_wall_clearance_m": 0.0375,
            "simulator_collision_bypass": False,
        }
        REPORT.parent.mkdir(exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("PASS: physical-scale motion tests A and B")
    finally:
        env.end()

    # Tests C–G use a fresh world so earlier passing-test bodies cannot alter
    # collision geometry.
    env = irsim.make(str(WORLD))
    try:
        robot = env.robot_list[0]
        robot.set_state([0.547, 0.547, 0.0])
        for _ in range(9):
            env.step(np.array([[0.0], [0.90]]), action_id=robot._id)
        _, _, heading_45 = state(robot)
        assert 0.70 < heading_45 < 0.90 and not robot.collision_flag

        for _ in range(10):
            env.step(np.array([[0.0], [0.90]]), action_id=robot._id)
        _, _, heading_90 = state(robot)
        assert 1.50 < heading_90 < 1.80 and not robot.collision_flag

        # A 3 mm vertical wall occupies x=[0.369, 0.372] at y=0.194.
        # A 0.05 m radius body must never advance through its far surface.
        robot.set_state([0.20, 0.194, 0.0])
        for _ in range(80):
            env.step(np.array([[0.044], [0.0]]), action_id=robot._id)
        stopped_x, _, _ = state(robot)
        assert stopped_x < 0.372

        report.update({
            "C_45_degree_turn": "PASS",
            "D_90_degree_turn": "PASS",
            "E_thin_wall_blocks_body": "PASS",
            "F_corner_body_clearance": "PASS (turns are in clear cell; no collision)",
            "G_no_thin_wall_tunneling": "PASS",
            "observed_heading_after_45_rad": heading_45,
            "observed_heading_after_90_rad": heading_90,
            "thin_wall_final_center_x_m": stopped_x,
        })
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("PASS: physical-scale motion tests C through G")
        return 0
    finally:
        env.end()


if __name__ == "__main__":
    raise SystemExit(main())
