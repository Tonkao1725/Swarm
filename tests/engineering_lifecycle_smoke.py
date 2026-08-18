"""Controlled, non-research fixture for the frozen C1 lifecycle."""
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
    run_dir = ROOT / "results" / "engineering_lifecycle_smoke_20260818"
    run_dir.mkdir(parents=True, exist_ok=True)
    endpoint = EnergyEndpoint("ENGINEERING_SMOKE_SOURCE", 1.0, 1.0)
    runtime = run_dir / "engineering_lifecycle_world.yaml"
    build_runtime_world(base_world_path=ROOT / "config" / "robot_world.yaml", runtime_world_path=runtime, active_energy=endpoint)
    env = irsim.make(str(runtime))
    try:
        sensor = RandomEndpointEnergySensor(endpoints=(endpoint,), detection_radius_m=0.20, random_seed=1, line_of_sight_margin_m=0.03, visible_marker_radius_m=0.12, guidance_threshold=0.001, collect_threshold=0.90, light_range_scale_m=4.50, blocked_light_factor=0.0, diffuse_guidance_threshold=0.003, maximum_diffuse_guidance_distance_m=7.0, angular_exponent=2.0, ambient_light=0.0)
        result = BaselineSwarmRunner(env=env, run_dir=run_dir, energy_sensor=sensor, seed=1, scout_count=3, duration_s=5.0, trip_count=3, render_enabled=False, mission_mode="research", nest_energy_target=6).run()
    finally:
        env.end()
    events = (run_dir / "swarm_events.csv").read_text(encoding="utf-8")
    required = ["RESOURCE_DETECTED", "COLLECT", "RETURN_HOME_START", "NEST_REACHED", "DELIVER", "NEST_ENERGY_UPDATED", "NEXT_TRIP_START"]
    missing = [event for event in required if event not in events]
    assert not missing, missing
    assert result["nest_energy_units"] == 6
    (run_dir / "ENGINEERING_LIFECYCLE_SMOKE_TEST.json").write_text(json.dumps({"classification":"NOT_RESEARCH_DATA", "required_events":required, "result":result}, indent=2), encoding="utf-8")
    print("PASS: ENGINEERING_LIFECYCLE_SMOKE_TEST")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
