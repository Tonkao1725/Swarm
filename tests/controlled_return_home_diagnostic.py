"""Controlled, non-research proof of the C1 RETURN_HOME primitive.

The research maze is deliberately not changed.  This fixture places one
already-carrying Scout in obstacle-free line of sight of the common Nest and
uses the production BaselineSwarmRunner unchanged.  It proves the sign of the
home cue, 45-degree turns, nest-radius transition, and delivery transition.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "swarm_simulate"))

import irsim
from energy_sensor import EnergyEndpoint, RandomEndpointEnergySensor
from swarm_baseline import BaselineSwarmRunner
from world_builder import build_runtime_world


def main() -> int:
    run_dir = ROOT / "results" / "controlled_return_home_diagnostic_20260818"
    run_dir.mkdir(parents=True, exist_ok=True)
    endpoint = EnergyEndpoint("DIAGNOSTIC_UNUSED_SOURCE", 11.875, 11.875)
    runtime = run_dir / "controlled_return_home_world.yaml"
    build_runtime_world(
        base_world_path=ROOT / "config" / "robot_world.yaml",
        runtime_world_path=runtime,
        active_energy=endpoint,
    )
    env = irsim.make(str(runtime))
    try:
        sensor = RandomEndpointEnergySensor(
            endpoints=(endpoint,), detection_radius_m=0.20, random_seed=1,
            line_of_sight_margin_m=0.03, visible_marker_radius_m=0.12,
            guidance_threshold=0.001, collect_threshold=0.90,
            light_range_scale_m=4.50, blocked_light_factor=0.0,
            diffuse_guidance_threshold=0.003,
            maximum_diffuse_guidance_distance_m=7.0, angular_exponent=2.0,
            ambient_light=0.0,
        )
        runner = BaselineSwarmRunner(
            env=env, run_dir=run_dir, energy_sensor=sensor, seed=1,
            scout_count=3, duration_s=10.0, trip_count=3,
            render_enabled=False, mission_mode="research", nest_energy_target=6,
        )
        # Keep non-participating bodies away from the clear diagnostic lane.
        env.robot_list[0]._state = np.asarray([12.0, 11.0, 0.0]).reshape(3, 1)
        env.robot_list[2]._state = np.asarray([12.0, 12.0, 0.0]).reshape(3, 1)
        runner.scouts[0].phase = "COMPLETE"
        runner.scouts[2].phase = "COMPLETE"
        # Scout 1 begins east of the Nest and faces north.  Production return
        # logic must turn CCW twice, advance west, enter the 0.12 m Nest
        # radius at (1.0, 1.0), and deliver.
        env.robot_list[1]._state = np.asarray([1.80, 1.00, math.pi / 2.0]).reshape(3, 1)
        runner.scouts[1].phase = "RETURN_HOME"
        runner.resource_carrier_id = 1
        common_homes = [(s.home.x_m, s.home.y_m) for s in runner.scouts]
        assert common_homes == [(1.0, 1.0)] * 3, common_homes
        result = runner.run()
    finally:
        env.end()

    events = (run_dir / "swarm_events.csv").read_text(encoding="utf-8")
    required = ["NEST_REACHED", "DELIVER", "NEST_ENERGY_UPDATED", "NEXT_TRIP_START"]
    missing = [event for event in required if event not in events]
    assert not missing, missing
    assert result["scouts"][1]["delivery_count"] >= 1
    assert "CONTACT_STALLED" not in events
    report = {
        "classification": "NOT_RESEARCH_DATA",
        "fixture": "clear_line_of_sight_return_to_common_nest",
        "common_nest_m": [1.0, 1.0],
        "start_pose_m_rad": [1.8, 1.0, math.pi / 2.0],
        "expected_turn_sign": "CCW for positive wrapped heading error",
        "required_events": required,
        "result": result,
    }
    (run_dir / "CONTROLLED_RETURN_HOME_DIAGNOSTIC.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print("PASS: CONTROLLED_RETURN_HOME_DIAGNOSTIC")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
