"""Run standard and FAST_HEADLESS C1 side-by-side and compare raw outputs."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def run(label: str, root: Path, duration: float, fast: bool) -> tuple[Path, float]:
    env = os.environ.copy()
    env.update({
        "FORAGING_SEED": "2118334751", "SWARM_EXPERIMENT_MODE": "baseline",
        "SWARM_SCOUT_COUNT": "3", "SWARM_MISSION_MODE": "research",
        "NEST_ENERGY_TARGET": "6", "FORAGING_TRIPS": "3",
        "SWARM_SIM_DURATION_S": str(duration), "SWARM_RESULTS_ROOT": str(root),
        "SWARM_RUN_ID": label, "MPLBACKEND": "Agg",
        "FAST_HEADLESS_RESEARCH_MODE": "1" if fast else "0",
        "IRSIM_RENDER": "0" if fast else "1",
    })
    started = time.perf_counter()
    subprocess.run([str(PYTHON), "main.py"], cwd=ROOT, env=env, check=True,
                   capture_output=True, text=True)
    return root / label, time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "results" / "headless_equivalence_20260819")
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    standard, standard_s = run("standard", root, args.duration, fast=False)
    fast, fast_s = run("fast_headless", root, args.duration, fast=True)
    files = ("swarm_trajectory.csv", "swarm_events.csv", "swarm_trip_summary.csv", "nest_energy_timeline.csv")
    comparisons: dict[str, bool] = {}
    for name in files:
        comparisons[name] = rows(standard / name) == rows(fast / name)
    left = json.loads((standard / "swarm_summary.json").read_text(encoding="utf-8"))
    right = json.loads((fast / "swarm_summary.json").read_text(encoding="utf-8"))
    comparisons["swarm_summary.json"] = left == right
    report = {
        "classification": "NOT_RESEARCH_DATA", "seed": 2118334751,
        "duration_s": args.duration, "standard_wallclock_s": standard_s,
        "fast_headless_wallclock_s": fast_s,
        "speedup": standard_s / fast_s if fast_s else None,
        "comparisons": comparisons, "verdict": "PASS" if all(comparisons.values()) else "FAIL",
    }
    (root / "headless_equivalence_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert report["verdict"] == "PASS", report
    print("PASS: HEADLESS_EQUIVALENCE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
