"""Engineering-only proof that the one RSSI sample cannot cross episodes."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "swarm_simulate"))

import irsim
from energy_sensor import EnergyEndpoint, RandomEndpointEnergySensor
from swarm_baseline import BaselineSwarmRunner
from world_builder import build_runtime_world


def main() -> int:
    out = ROOT / "results" / "rssi_state_reset_test_20260819"
    out.mkdir(parents=True, exist_ok=True)
    runtime = out / "world.yaml"
    endpoint = EnergyEndpoint("TEST_SOURCE", 11.875, 11.875)
    build_runtime_world(
        base_world_path=ROOT / "config" / "robot_world.yaml",
        runtime_world_path=runtime, active_energy=endpoint,
    )
    env = irsim.make(str(runtime))
    try:
        sensor = RandomEndpointEnergySensor(
            endpoints=(endpoint,), detection_radius_m=0.20, random_seed=1,
            line_of_sight_margin_m=0.03, visible_marker_radius_m=0.12,
            guidance_threshold=0.001, collect_threshold=0.90,
            light_range_scale_m=4.5, blocked_light_factor=0.0,
            diffuse_guidance_threshold=0.003, maximum_diffuse_guidance_distance_m=7.0,
            angular_exponent=2.0, ambient_light=0.0,
        )
        runner = BaselineSwarmRunner(
            env=env, run_dir=out, energy_sensor=sensor, seed=1, scout_count=3,
            duration_s=1, trip_count=3, render_enabled=False, mission_mode="research",
            nest_energy_target=6,
        )
        scout = runner.scouts[0]
        assert scout.previous_nest_rssi is None
        scout.previous_nest_rssi = 0.7
        scout.phase = "COLLECT"
        runner._command_for(scout, runner.sensors[0])
        assert scout.phase == "RETURN_HOME"
        assert scout.previous_nest_rssi is None
        scout.previous_nest_rssi = 0.8
        scout.phase = "DELIVER"
        runner.resource_carrier_id = scout.scout_id
        runner._command_for(scout, runner.sensors[0])
        assert scout.phase == "EXPLORE"
        assert scout.previous_nest_rssi is None
    finally:
        env.end()
    (out / "rssi_state_reset_test.json").write_text(json.dumps({
        "classification": "NOT_RESEARCH_DATA", "max_retained_rssi_samples": 1,
        "reset_on_collect_to_return": True, "reset_on_deliver": True,
        "cross_trip_route_or_position_state": False, "verdict": "PASS",
    }, indent=2), encoding="utf-8")
    print("PASS: RSSI_STATE_RESET")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
