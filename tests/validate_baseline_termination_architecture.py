"""Controlled physics integration test for Baseline mission termination.

The endpoint is intentionally placed at Scout 0's nest only for this test.
It exercises collection, return, delivery, nest-energy accounting, the next
trip transition, and colony-level target termination without changing the
research controller or its fixed experimental source.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src" / "swarm_simulate"
sys.path.insert(0, str(SOURCE_ROOT))

import irsim

from energy_sensor import EnergyEndpoint, RandomEndpointEnergySensor
from swarm_baseline import BaselineSwarmRunner
from world_builder import build_runtime_world


def run_case(case_name: str, *, endpoint: EnergyEndpoint, target: int, duration_s: float) -> tuple[dict, list[dict[str, str]]]:
    output_dir = PROJECT_ROOT / "results" / "termination_architecture_tests_20260816" / case_name
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_world = PROJECT_ROOT / "config" / "robot_world_runtime_controlled_target1.yaml"
    build_runtime_world(
        base_world_path=PROJECT_ROOT / "config" / "robot_world.yaml",
        runtime_world_path=runtime_world,
        active_energy=endpoint,
    )
    sensor = RandomEndpointEnergySensor(
        endpoints=(endpoint,), detection_radius_m=0.20, random_seed=1,
        line_of_sight_margin_m=0.03, visible_marker_radius_m=0.12,
        guidance_threshold=0.001, collect_threshold=0.90,
        light_range_scale_m=4.50, blocked_light_factor=0.0,
        diffuse_guidance_threshold=0.003, maximum_diffuse_guidance_distance_m=7.0,
    )
    env = irsim.make(str(runtime_world))
    result = BaselineSwarmRunner(
        env=env, run_dir=output_dir, energy_sensor=sensor, seed=1,
        scout_count=3, duration_s=duration_s, trip_count=1, render_enabled=False,
        mission_mode="research", nest_energy_target=target,
    ).run()
    with (output_dir / "swarm_events.csv").open(newline="", encoding="utf-8") as handle:
        events = list(csv.DictReader(handle))
    return result, events


def main() -> None:
    endpoint = EnergyEndpoint("E_TEST_NEST", 1.0, 1.0)
    result, events = run_case(
        "controlled_physics_target1", endpoint=endpoint, target=1, duration_s=10.0,
    )

    assert result["experimental_validity"] == "VALID", result
    assert result["mission_outcome"] == "MISSION_SUCCESS", result
    assert result["nest_energy_units"] == 1, result
    assert result["target_reached"] is True, result
    assert result["termination_reason"] == "NEST_ENERGY_TARGET_REACHED", result
    assert sum(s["delivery_count"] for s in result["scouts"]) == 1, result
    assert result["scouts"][0]["started_trip_count"] == 2, result

    names = [row["event"] for row in events]
    required = ["DELIVER", "NEST_ENERGY_UPDATED", "NEXT_TRIP_START", "MISSION_COMPLETE"]
    positions = [names.index(name) for name in required]
    assert positions == sorted(positions), names
    assert names.count("DELIVER") == 1, names

    target_two, _ = run_case(
        "controlled_physics_target2", endpoint=endpoint, target=2, duration_s=0.5,
    )
    assert target_two["mission_outcome"] == "TIME_LIMIT_REACHED", target_two
    assert target_two["nest_energy_units"] == 1, target_two
    assert target_two["scouts"][0]["started_trip_count"] == 2, target_two

    target_six, events_six = run_case(
        "controlled_physics_target6_trip1", endpoint=endpoint, target=6, duration_s=10.0,
    )
    assert target_six["mission_outcome"] == "MISSION_SUCCESS", target_six
    assert target_six["nest_energy_units"] == 6, target_six
    assert target_six["scouts"][0]["started_trip_count"] == 7, target_six
    assert sum(row["event"] == "DELIVER" for row in events_six) == 6, events_six

    timeout, _ = run_case(
        "controlled_physics_horizon_before_target",
        endpoint=EnergyEndpoint("E_TEST_FAR", 11.875, 11.875), target=1, duration_s=0.5,
    )
    assert timeout["mission_outcome"] == "TIME_LIMIT_REACHED", timeout
    assert timeout["experimental_validity"] == "VALID", timeout
    assert timeout["nest_energy_units"] == 0, timeout

    output_dir = PROJECT_ROOT / "results" / "termination_architecture_tests_20260816" / "controlled_physics_target1"
    (output_dir / "controlled_test_result.json").write_text(
        json.dumps({"status": "PASS", "summary": result, "target_two": target_two,
                    "target_six": target_six, "timeout": timeout}, indent=2),
        encoding="utf-8",
    )
    print("PASS: controlled Baseline target-1 mission termination architecture")


if __name__ == "__main__":
    main()
