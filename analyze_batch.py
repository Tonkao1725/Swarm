from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a compact report from batch summary.csv.")
    parser.add_argument("batch_directory", type=Path)
    args = parser.parse_args()

    summary_path = args.batch_directory / "summary.csv"
    if not summary_path.exists():
        raise FileNotFoundError(summary_path)

    rows = read_rows(summary_path)
    passed = [row for row in rows if str(row.get("pass", "")).lower() == "true"]
    failed = [row for row in rows if row not in passed]

    distances = [value for row in passed if (value := as_float(row.get("total_distance_m"))) is not None]
    times = [value for row in passed if (value := as_float(row.get("simulation_time_s"))) is not None]

    report = {
        "experiment_modes": sorted({
            str(row.get("experiment_mode") or "UNKNOWN")
            for row in rows
        }),
        "total": len(rows),
        "passed": len(passed),
        "failed": len(failed),
        "pass_rate_percent": round(100 * len(passed) / len(rows), 3) if rows else 0,
        "average_distance_m": sum(distances) / len(distances) if distances else None,
        "average_simulation_time_s": sum(times) / len(times) if times else None,
        "failed_seeds": [row.get("seed") for row in failed],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
