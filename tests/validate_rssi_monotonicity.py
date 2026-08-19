"""Unit-level contract test for the environment-owned common Nest beacon."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "swarm_simulate"))

from swarm_baseline import IdealizedRSSILikeNestBeacon, RobotPose


def main() -> int:
    beacon = IdealizedRSSILikeNestBeacon(nest_x_m=1.0, nest_y_m=1.0, scale_m=2.0)
    near = beacon.sample(RobotPose(1.5, 1.0, 0.0))
    middle = beacon.sample(RobotPose(2.0, 1.0, 0.0))
    far = beacon.sample(RobotPose(3.0, 1.0, 0.0))
    assert 0.0 < far < middle < near <= 1.0
    report = {
        "classification": "NOT_RESEARCH_DATA",
        "cue": "IDEALIZED_RSSI_LIKE_COMMON_NEST_CUE",
        "samples": {"0.5_m": near, "1.0_m": middle, "2.0_m": far},
        "monotonic_with_nest_distance": True,
        "controller_exposure": "scalar_only",
        "verdict": "PASS",
    }
    out = ROOT / "results" / "rssi_monotonicity_test_20260819"
    out.mkdir(parents=True, exist_ok=True)
    (out / "rssi_monotonicity_test.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print("PASS: RSSI_MONOTONICITY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
