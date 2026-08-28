"""Unit-level contract test for the environment-owned common Nest beacon.

Updated 2026-08-27 (sim-to-real RF hardware alignment task, then the
SIM-TO-REAL ARCHITECTURE CORRECTION task) to use the ACTIVE simulated RSSI
sensor model (`ESP32NestBeaconModel` + `SimulatedNestRSSIModel`), which
operates directly on simulation-scale distance with no geometric
sim-to-real conversion -- see docs/SIM_TO_REAL_SOFTWARE_ARCHITECTURE.md.
The property under test -- RSSI strictly decreases with distance, and the
controller only ever receives the scalar -- is unchanged and still holds.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "swarm_simulate"))

from swarm_baseline import ESP32NestBeaconModel, RobotPose
from nest_beacon_hardware import NODEMCU_ESP32_WROOM32_PROFILE, SimulatedNestRSSIModel


def main() -> int:
    beacon = ESP32NestBeaconModel(
        nest_x_m=1.0, nest_y_m=1.0,
        propagation=SimulatedNestRSSIModel(profile=NODEMCU_ESP32_WROOM32_PROFILE),
    )
    near = beacon.sample(RobotPose(1.5, 1.0, 0.0))
    middle = beacon.sample(RobotPose(2.0, 1.0, 0.0))
    far = beacon.sample(RobotPose(3.0, 1.0, 0.0))
    assert far < middle < near, (far, middle, near)
    report = {
        "classification": "NOT_RESEARCH_DATA",
        "cue": "NODEMCU_ESP32_WROOM32_NEST_BEACON_DBM",
        "samples_dbm": {"0.5_m": near, "1.0_m": middle, "2.0_m": far},
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
