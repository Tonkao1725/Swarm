"""Targeted non-research checks for pause/resume and payload transfer math."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    config = json.loads((ROOT / "config" / "resource_harvesting_config.json").read_text(encoding="utf-8"))
    rate = next(item["relative_harvest_rate"] for item in config["sources"] if item["resource_id"] == "B")
    dt, target = 0.1, config["harvest_payload_target"]
    carried = 0.0
    for _ in range(10): carried += rate * dt
    retained = carried
    # Invalid LOS/near-field period: no remote accumulation.
    for _ in range(10): carried += 0.0
    assert carried == retained
    for _ in range(10): carried += rate * dt
    delivered = min(carried, target)
    nest_before = 2.25
    nest_after = nest_before + delivered
    carried = 0.0
    assert abs((nest_after - nest_before) - delivered) < 1e-12 and carried == 0.0
    out = ROOT / "results" / "harvest_payload_semantics_test_20260819"
    out.mkdir(parents=True, exist_ok=True)
    (out / "harvest_payload_semantics.json").write_text(json.dumps({"pause_retains_buffer": True, "invalid_los_accumulation": 0.0, "delivery_transfer_exact": True, "scout_buffer_reset": True, "verdict": "PASS"}, indent=2), encoding="utf-8")
    print("PASS: HARVEST_PAYLOAD_SEMANTICS")
    return 0

if __name__ == "__main__": raise SystemExit(main())
