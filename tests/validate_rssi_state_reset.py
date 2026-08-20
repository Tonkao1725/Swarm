"""Engineering-only check: C1 retains no RSSI sample across actions or trips."""
from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "swarm_simulate" / "swarm_baseline.py"
OUT = ROOT / "results" / "c1_rssi_confirmation_tests"


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    retained = [
        node.attr for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and "rssi" in node.attr.lower()
    ]
    assert not retained, retained
    assert "previous_nest_rssi" not in source
    assert "RSSI confirmation" in source
    report = {
        "classification": "NOT_RESEARCH_DATA",
        "retained_rssi_controller_state": False,
        "cross_trip_rssi_state": False,
        "arrival_rule": "physical Nest region AND current environment RSSI confirmation",
        "verdict": "PASS",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "rssi_state_reset_test.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS: RSSI_STATE_RESET")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
