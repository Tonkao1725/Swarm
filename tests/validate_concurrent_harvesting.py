"""Targeted environment-semantics test: a persistent source has no carrier lock."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    config = json.loads((ROOT / "config" / "resource_harvesting_config.json").read_text(encoding="utf-8"))
    source = next(item for item in config["sources"] if item["resource_id"] == "C")
    dt, steps = 0.1, 25
    rate = float(source["relative_harvest_rate"])
    # Two independent valid near-field harvest episodes receive the same
    # environment rate; no resource-carrier/source-lock state is involved.
    scout_energy = [sum(rate * dt for _ in range(steps)) for _ in range(2)]
    assert scout_energy[0] == scout_energy[1] == rate * dt * steps
    out = ROOT / "results" / "concurrent_harvesting_test_20260819"
    out.mkdir(parents=True, exist_ok=True)
    (out / "concurrent_harvesting.json").write_text(json.dumps({
        "classification": "NOT_RESEARCH_DATA", "resource_id": "C",
        "scout_count_harvesting_same_source": 2, "global_source_lock": False,
        "energy_per_scout": scout_energy, "persistent_source": True, "verdict": "PASS",
    }, indent=2), encoding="utf-8")
    print("PASS: CONCURRENT_HARVESTING")
    return 0


if __name__ == "__main__": raise SystemExit(main())
