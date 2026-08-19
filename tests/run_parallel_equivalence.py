"""Prove process-parallel C1 runs preserve each seed's deterministic output."""
from __future__ import annotations

import concurrent.futures
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
SEEDS = (2118334751, 652974033)
FILES = ("swarm_trajectory.csv", "swarm_events.csv", "swarm_trip_summary.csv", "nest_energy_timeline.csv")


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def run_one(root: Path, seed: int, duration_s: float) -> None:
    run_id = f"seed_{seed}"
    env = os.environ.copy()
    env.update({
        "FORAGING_SEED": str(seed), "SWARM_EXPERIMENT_MODE": "baseline",
        "SWARM_SCOUT_COUNT": "3", "SWARM_MISSION_MODE": "research",
        "NEST_ENERGY_TARGET": "6", "FORAGING_TRIPS": "3",
        "SWARM_SIM_DURATION_S": str(duration_s), "SWARM_RESULTS_ROOT": str(root),
        "SWARM_RUN_ID": run_id, "MPLBACKEND": "Agg", "IRSIM_RENDER": "0",
        "FAST_HEADLESS_RESEARCH_MODE": "1",
    })
    subprocess.run([str(PYTHON), "main.py"], cwd=ROOT, env=env, check=True,
                   capture_output=True, text=True)


def equivalent(left: Path, right: Path) -> dict[str, bool]:
    verdict = {name: rows(left / name) == rows(right / name) for name in FILES}
    verdict["swarm_summary.json"] = json.loads((left / "swarm_summary.json").read_text(encoding="utf-8")) == json.loads((right / "swarm_summary.json").read_text(encoding="utf-8"))
    return verdict


def main() -> int:
    duration_s = float(os.environ.get("C1_PARALLEL_EQUIVALENCE_DURATION_S", "20"))
    out = ROOT / "results" / "parallel_equivalence_20260819"
    out.mkdir(parents=True, exist_ok=False)
    serial = out / "serial"
    parallel = out / "parallel"
    serial.mkdir(); parallel.mkdir()
    started = time.perf_counter()
    for seed in SEEDS:
        run_one(serial, seed, duration_s)
    serial_wallclock = time.perf_counter() - started
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(SEEDS)) as executor:
        futures = [executor.submit(run_one, parallel, seed, duration_s) for seed in SEEDS]
        for future in futures:
            future.result()
    parallel_wallclock = time.perf_counter() - started
    comparisons = {
        str(seed): equivalent(serial / f"seed_{seed}", parallel / f"seed_{seed}")
        for seed in SEEDS
    }
    passed = all(all(check.values()) for check in comparisons.values())
    report = {
        "classification": "NOT_RESEARCH_DATA", "seeds": list(SEEDS),
        "duration_s": duration_s, "same_process_per_seed": True,
        "serial_wallclock_s": serial_wallclock, "parallel_wallclock_s": parallel_wallclock,
        "comparisons": comparisons, "verdict": "PASS" if passed else "FAIL",
    }
    (out / "parallel_equivalence_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert passed, report
    print("PASS: PARALLEL_EQUIVALENCE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
