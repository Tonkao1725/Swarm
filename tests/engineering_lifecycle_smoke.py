"""Controlled, non-research proof of the C1 lifecycle and common ledger."""
from __future__ import annotations

import csv
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
    run_dir = ROOT / "results" / "engineering_lifecycle_smoke_c1"
    run_dir.mkdir(parents=True, exist_ok=True)
    # This source is intentionally colocated with the Nest only for a
    # deterministic engineering state-transition fixture; it is not research
    # geometry or data.
    endpoint = EnergyEndpoint("SMOKE", 1.0, 1.0, relative_harvest_rate=0.5)
    runtime = run_dir / "engineering_lifecycle_world.yaml"
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
            diffuse_guidance_threshold=0.003,
            maximum_diffuse_guidance_distance_m=7.0,
            angular_exponent=2.0, ambient_light=0.0,
        )
        result = BaselineSwarmRunner(
            env=env, run_dir=run_dir, energy_sensor=sensor, seed=1,
            scout_count=3, duration_s=30.0, trip_count=3,
            render_enabled=False, mission_mode="research", nest_energy_target=2,
            harvest_payload_target=1.0, internal_energy_capacity=3.0,
            initial_internal_energy=3.0, energy_cost_per_encoder_distance=0.01,
        ).run()
    finally:
        env.end()

    events = list(csv.DictReader((run_dir / "swarm_events.csv").open(encoding="utf-8")))
    names = [row["event"] for row in events]
    required = ["RESOURCE_LIGHT_DETECTED", "HARVEST_COMPLETE", "RETURN_HOME_START", "NEST_REACHED", "DELIVER", "NEST_ENERGY_UPDATED", "NEXT_CYCLE_START"]
    missing = [event for event in required if event not in names]
    assert not missing, missing
    assert result["gross_delivered_energy"] >= result["net_nest_energy"] >= 0.0
    assert result["total_robot_nest_withdrawal"] >= 0.0
    assert names.count("NEXT_CYCLE_START") == 1, names.count("NEXT_CYCLE_START")
    timeline = list(csv.DictReader((run_dir / "nest_energy_timeline.csv").open(encoding="utf-8")))
    assert any(row["event_type"] == "DELIVERY" for row in timeline)
    (run_dir / "ENGINEERING_LIFECYCLE_SMOKE_TEST.json").write_text(json.dumps({
        "classification": "NOT_RESEARCH_DATA", "required_events": required,
        "result": result, "verdict": "PASS",
    }, indent=2), encoding="utf-8")
    print("PASS: ENGINEERING_LIFECYCLE_SMOKE_TEST")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
