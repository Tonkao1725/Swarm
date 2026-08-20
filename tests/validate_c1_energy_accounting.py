"""Controlled runner-level proof of C1 delivery/recharge accounting."""
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
    out = ROOT / "results" / "c1_energy_accounting_test_20260820"
    out.mkdir(parents=True, exist_ok=True)
    endpoint = EnergyEndpoint("ACCOUNTING_SMOKE", 1.0, 1.0, relative_harvest_rate=0.5)
    runtime = out / "world.yaml"
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
            light_range_scale_m=4.5, blocked_light_factor=0.0,
            diffuse_guidance_threshold=0.003,
            maximum_diffuse_guidance_distance_m=7.0,
            angular_exponent=2.0, ambient_light=0.0,
        )
        result = BaselineSwarmRunner(
            env=env, run_dir=out, energy_sensor=sensor, seed=2, scout_count=3,
            duration_s=3.0, trip_count=3, render_enabled=False,
            mission_mode="research", nest_energy_target=6,
            harvest_payload_target=1.0, internal_energy_capacity=3.0,
            initial_internal_energy=2.0, energy_cost_per_encoder_distance=0.01,
        ).run()
    finally:
        env.end()

    events = list(csv.DictReader((out / "swarm_events.csv").open(encoding="utf-8")))
    names = [row["event"] for row in events]
    assert "DELIVER" in names and "NEST_ENERGY_UPDATED" in names
    assert "NEST_ENERGY_WITHDRAWAL" in names
    timeline = list(csv.DictReader((out / "nest_energy_timeline.csv").open(encoding="utf-8")))
    assert [row["event_type"] for row in timeline] == ["DELIVERY", "ROBOT_RECHARGE_WITHDRAWAL"]
    delivery, withdrawal = timeline
    assert float(delivery["new_energy"]) == 1.0
    assert float(withdrawal["withdrawal_energy"]) == 1.0
    assert float(withdrawal["new_energy"]) == 0.0
    assert result["gross_delivered_energy"] == 1.0
    assert result["total_robot_nest_withdrawal"] == 1.0
    assert result["net_nest_energy"] == 0.0
    report = {
        "classification": "NOT_RESEARCH_DATA", "delivery_before_recharge": True,
        "target_prevents_withdrawal": "covered by engineering_lifecycle_smoke_c1",
        "nest_never_negative": True, "gross_and_net_separated": True,
        "result": result, "verdict": "PASS",
    }
    (out / "c1_energy_accounting.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS: C1_ENERGY_ACCOUNTING")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
