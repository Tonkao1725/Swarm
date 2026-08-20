"""Regression for physical, action-agnostic stationary-turn classification."""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "swarm_simulate"))

from swarm_baseline import BaselineSwarmRunner, ScoutState


def main() -> int:
    # This narrow unit fixture intentionally avoids a world: classification
    # consumes measured movement/heading change, not phase/action strings.
    runner = object.__new__(BaselineSwarmRunner)
    runner.return_stationary_turn_limit = 12
    for phase in ("EXPLORE", "RETURN_HOME"):
        scout = ScoutState(scout_id=0, rng=random.Random(1), phase=phase)
        for _ in range(11):
            runner._record_physical_stationary_rotation(
                scout, moved_m=0.0, turned=True, angular_velocity_radps=0.9,
            )
        assert not scout.persistent_stationary_turn_deadlock
        runner._record_physical_stationary_rotation(
            scout, moved_m=0.0, turned=True, angular_velocity_radps=0.9,
        )
        assert scout.persistent_stationary_turn_deadlock, phase
        runner._record_physical_stationary_rotation(
            scout, moved_m=0.022, turned=False, angular_velocity_radps=0.0,
        )
        assert scout.stationary_rotation_steps == 0
    out = ROOT / "results" / "persistent_stationary_turn_deadlock_test_20260819"
    out.mkdir(parents=True, exist_ok=True)
    (out / "persistent_stationary_turn_deadlock_test.json").write_text(json.dumps({
        "classification": "NOT_RESEARCH_DATA", "detector_input": "physical motion only",
        "action_string_used": False, "explore_checked": True,
        "return_home_checked": True, "translation_resets_counter": True, "verdict": "PASS",
    }, indent=2), encoding="utf-8")
    print("PASS: PERSISTENT_STATIONARY_TURN_DEADLOCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
