"""Focused fixtures for canonical C1 all-depleted termination semantics."""
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


def runner(case: str, *, nest_energy: float) -> dict:
    out = ROOT / "results" / "c1_all_depleted_termination_tests" / case
    out.mkdir(parents=True, exist_ok=True)
    runtime = out / "world.yaml"
    endpoint = EnergyEndpoint("FAR", 11.875, 11.875, relative_harvest_rate=0.1)
    build_runtime_world(base_world_path=ROOT / "config" / "robot_world.yaml", runtime_world_path=runtime, active_energy=endpoint)
    env = irsim.make(str(runtime))
    try:
        sensor = RandomEndpointEnergySensor(endpoints=(endpoint,), detection_radius_m=.2, random_seed=1,
            line_of_sight_margin_m=.03, visible_marker_radius_m=.12, guidance_threshold=.001,
            collect_threshold=.9, light_range_scale_m=4.5, blocked_light_factor=0.0,
            diffuse_guidance_threshold=.003, maximum_diffuse_guidance_distance_m=7.0, angular_exponent=2.0, ambient_light=0.0)
        value = BaselineSwarmRunner(env=env, run_dir=out, energy_sensor=sensor, seed=7, scout_count=3,
            duration_s=2.0, trip_count=3, render_enabled=False, mission_mode="research", nest_energy_target=6,
            initial_internal_energy=0.0, internal_energy_capacity=3.0).run() if nest_energy == 0 else None
        if value is None:
            sim = BaselineSwarmRunner(env=env, run_dir=out, energy_sensor=sensor, seed=7, scout_count=3,
                duration_s=.1, trip_count=3, render_enabled=False, mission_mode="research", nest_energy_target=6,
                initial_internal_energy=0.0, internal_energy_capacity=3.0)
            sim.nest_energy = nest_energy
            value = sim.run()
        return value
    finally:
        env.end()


def main() -> int:
    failed = runner("all_stranded", nest_energy=0.0)
    assert failed["mission_outcome"] == "COLONY_FAILURE_ALL_DEPLETED", failed
    assert failed["termination_reason"] == "COLONY_FAILURE_ALL_DEPLETED", failed
    assert failed["termination_time_s"] < 2.0, failed
    assert all(item["internal_energy"] == 0.0 for item in failed["termination_state"]["scouts"]), failed
    restored = runner("nest_recharge_possible", nest_energy=1.0)
    assert restored["mission_outcome"] == "TIME_LIMIT_REACHED", restored
    assert restored["termination_reason"] == "TIME_LIMIT_REACHED", restored
    assert restored["scouts"][0]["internal_energy_final"] > 0.0, restored
    # SUCCESS is higher priority than the depletion predicate, even if every
    # robot starts with zero internal energy.
    success = runner("success_priority", nest_energy=6.0)
    assert success["mission_outcome"] == "MISSION_SUCCESS", success
    assert success["termination_reason"] == "NEST_ENERGY_TARGET_REACHED", success
    assert success["total_robot_nest_withdrawal"] == 0.0, success
    (ROOT / "results" / "c1_all_depleted_termination_tests" / "report.json").write_text(json.dumps({"all_stranded": failed, "recharge_possible": restored, "success_priority": success}, indent=2), encoding="utf-8")
    print("PASS: C1_ALL_DEPLETED_TERMINATION")


if __name__ == "__main__":
    raise SystemExit(main())
