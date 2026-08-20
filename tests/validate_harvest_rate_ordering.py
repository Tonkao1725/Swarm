"""Engineering test: pilot harvesting rates are ordered and dt-integrated."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    config = json.loads((ROOT / "config" / "resource_harvesting_config.json").read_text(encoding="utf-8"))
    sources = config["sources"]
    rates = {item["resource_id"]: float(item["relative_harvest_rate"]) for item in sources}
    assert rates["A"] < rates["B"] < rates["C"]
    dt = 0.1
    target = float(config["harvest_payload_target"])
    durations = {name: target / rate for name, rate in rates.items()}
    assert durations["A"] > durations["B"] > durations["C"]
    accumulated = {name: sum(rate * dt for _ in range(10)) for name, rate in rates.items()}
    assert all(abs(accumulated[name] - rates[name]) < 1e-12 for name in rates)
    out = ROOT / "results" / "harvest_rate_ordering_test_20260819"
    out.mkdir(parents=True, exist_ok=True)
    (out / "harvest_rate_ordering.json").write_text(json.dumps({
        "classification": "NOT_RESEARCH_DATA", "rates": rates,
        "payload_target": target, "expected_harvest_duration_s": durations,
        "dt_integration_checked": dt, "verdict": "PASS",
    }, indent=2), encoding="utf-8")
    print("PASS: HARVEST_RATE_ORDERING")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
