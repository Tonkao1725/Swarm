"""Non-research regression for bounded C1 contact-recovery retry.

Replays the local wall/crowding geometry from the R02 research interruption.
It proves that a first recovery with measured motion but persistent contact
receives one fresh-LiDAR retry rather than being classified fatal immediately.
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
    run_dir = ROOT / "results" / "contact_recovery_retry_diagnostic_20260818"
    run_dir.mkdir(parents=True, exist_ok=True)
    endpoint = EnergyEndpoint("DIAGNOSTIC_UNUSED_SOURCE", 11.875, 11.875)
    runtime = run_dir / "contact_recovery_retry_world.yaml"
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
            env=env, run_dir=run_dir, energy_sensor=sensor, seed=98386804,
            scout_count=3, duration_s=5.0, trip_count=3,
            render_enabled=False, mission_mode="research", nest_energy_target=6,
        )
        # Scout 0 is excluded. Scouts 1/2 reproduce the local R02 contact
        # geometry near the x=10 m vertical wall; no peer pose is exposed to
        # the production policy.
        env.robot_list[0]._state = np.asarray([12.0, 11.0, 0.0]).reshape(3, 1)
        runner.scouts[0].phase = "COMPLETE"
        for scout, state in zip(
            runner.scouts[1:],
            ([9.5856504754, 0.9620538583, math.radians(59.06)],
             [9.9994055480, 1.0250023894, math.radians(135.0)]),
            strict=True,
        ):
            env.robot_list[scout.scout_id]._state = np.asarray(state).reshape(3, 1)
            scout.recovery_stage = "BACK_OFF"
            scout.recovery_steps_remaining = runner.bypass_departure_step_count
            scout.contact_recovery_episode_count = 1
            scout.contact_recovery_count = 1
            scout.previous_pose = runner._pose(env, scout.scout_id)
        result = runner.run()
    finally:
        env.end()
    events = (run_dir / "swarm_events.csv").read_text(encoding="utf-8")
    assert "CONTACT_RECOVERY_RETRY" in events, events
    assert "CONTACT_STALLED" not in events, events
    (run_dir / "CONTACT_RECOVERY_RETRY_DIAGNOSTIC.json").write_text(
        json.dumps({"classification": "NOT_RESEARCH_DATA", "result": result}, indent=2),
        encoding="utf-8",
    )
    print("PASS: CONTACT_RECOVERY_RETRY_DIAGNOSTIC")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
