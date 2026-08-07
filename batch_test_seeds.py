from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SEEDS = [1, 2, 3, 4, 5, 10, 25, 42, 100, 12345]

@dataclass(frozen=True)
class BatchConfig:
    seeds: list[int]
    render: bool
    timeout_s: float
    label: str
    keep_success_logs: bool
    experiment_mode: str

def parse_seed_spec(spec: str) -> list[int]:
    """Parse `1-100`, `1,3,5`, or combinations such as `1-10,25,42`."""
    result: list[int] = []
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start, end = int(start_text), int(end_text)
            step = 1 if end >= start else -1
            result.extend(range(start, end + step, step))
        else:
            result.append(int(token))
    if not result:
        raise ValueError("No seeds were parsed.")
    return list(dict.fromkeys(result))

def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def read_last_error(run_dir: Path) -> str:
    traceback_path = run_dir / "error_traceback.txt"
    if traceback_path.exists():
        lines = [line.strip() for line in traceback_path.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines() if line.strip()]
        return lines[-1] if lines else "UNKNOWN_ERROR"
    return ""


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as handle:
        return max(0, sum(1 for _ in handle) - 1)


def safe_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def mean(values: Iterable[float | None]) -> float | None:
    cleaned = [value for value in values if value is not None]
    return sum(cleaned) / len(cleaned) if cleaned else None


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def collect_row(
    *,
    seed: int,
    run_dir: Path,
    process_return_code: int,
    wall_clock_s: float,
    timed_out: bool,
) -> dict[str, Any]:
    foraging = read_json(run_dir / "foraging_summary.json")
    motion = read_json(run_dir / "summary.json")
    metadata = read_json(run_dir / "metadata.json")

    status = str(foraging.get("status") or motion.get("status") or "NO_SUMMARY")
    passed = (
        process_return_code == 0
        and status == "PASS"
        and foraging.get("energy_collected") is True
        and foraging.get("home_reached") is True
    )

    return {
        "seed": seed,
        "run_id": run_dir.name,
        "experiment_mode": metadata.get(
            "configuration", {}
        ).get("experiment_mode", {}).get("mode", ""),
        "pass": passed,
        "status": status,
        "process_return_code": process_return_code,
        "timed_out": timed_out,
        "energy_endpoint": foraging.get("detected_endpoint_id", ""),
        "energy_collected": foraging.get("energy_collected", False),
        "home_reached": foraging.get("home_reached", False),
        "simulation_time_s": motion.get("simulation_time_s", ""),
        "wall_clock_s": round(wall_clock_s, 4),
        "total_distance_m": foraging.get(
            "total_actual_distance_m",
            motion.get("total_ground_truth_distance_m", ""),
        ),
        "home_error_m": foraging.get("home_position_error_m", ""),
        "decision_count": foraging.get("decision_count", count_csv_rows(run_dir / "decision.csv")),
        "backtrack_or_recovery_count": foraging.get(
            "collision_recovery_count",
            count_csv_rows(run_dir / "collision_recovery.csv"),
        ),
        "return_command_count": foraging.get(
            "return_command_count",
            count_csv_rows(run_dir / "return_replay.csv"),
        ),
        "working_memory_command_count": foraging.get("working_memory_command_count", ""),
        "junction_cluster_count": foraging.get("junction_cluster_count", ""),
        "max_odometry_position_error_m": motion.get("max_odometry_position_error_m", ""),
        "max_odometry_heading_error_deg": motion.get("max_odometry_heading_error_deg", ""),
        "error": "TIMEOUT" if timed_out else read_last_error(run_dir),
        "run_directory": str(run_dir),
        "algorithm_test_name": metadata.get("configuration", {}).get("test_name", ""),
    }


def run_seed(
    seed: int,
    *,
    batch_root: Path,
    render: bool,
    timeout_s: float,
    experiment_mode: str,
) -> dict[str, Any]:
    run_id = f"seed_{seed:010d}"
    run_dir = batch_root / "runs" / run_id
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    if run_dir.exists():
        shutil.rmtree(run_dir)

    env = os.environ.copy()
    env["FORAGING_SEED"] = str(seed)
    env["SWARM_EXPERIMENT_MODE"] = experiment_mode
    env["IRSIM_RENDER"] = "1" if render else "0"
    env["SWARM_RESULTS_ROOT"] = str(run_dir.parent)
    env["SWARM_RUN_ID"] = run_id
    if not render:
        env.setdefault("MPLBACKEND", "Agg")

    started = time.perf_counter()
    timed_out = False
    try:
        completed = subprocess.run(
            [sys.executable, "main.py"],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_s,
        )
        return_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        return_code = 124
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""

    wall_clock_s = time.perf_counter() - started
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "console_stdout.txt").write_text(str(stdout), encoding="utf-8", errors="replace")
    (run_dir / "console_stderr.txt").write_text(str(stderr), encoding="utf-8", errors="replace")

    row = collect_row(
        seed=seed,
        run_dir=run_dir,
        process_return_code=return_code,
        wall_clock_s=wall_clock_s,
        timed_out=timed_out,
    )
    (run_dir / "batch_result.json").write_text(
        json.dumps(row, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return row


def make_statistics(rows: list[dict[str, Any]], config: BatchConfig) -> dict[str, Any]:
    passed_rows = [row for row in rows if row["pass"]]
    failed_rows = [row for row in rows if not row["pass"]]

    endpoint_counts: dict[str, int] = {}
    for row in rows:
        endpoint = str(row.get("energy_endpoint") or "UNKNOWN")
        endpoint_counts[endpoint] = endpoint_counts.get(endpoint, 0) + 1

    return {
        "batch_label": config.label,
        "total_runs": len(rows),
        "passed_runs": len(passed_rows),
        "failed_runs": len(failed_rows),
        "pass_rate_percent": round(100.0 * len(passed_rows) / len(rows), 3) if rows else 0.0,
        "average_simulation_time_s_passed": mean(safe_number(row["simulation_time_s"]) for row in passed_rows),
        "average_wall_clock_s_all": mean(safe_number(row["wall_clock_s"]) for row in rows),
        "average_distance_m_passed": mean(safe_number(row["total_distance_m"]) for row in passed_rows),
        "average_home_error_m_passed": mean(safe_number(row["home_error_m"]) for row in passed_rows),
        "maximum_home_error_m_passed": max(
            (value for value in (safe_number(row["home_error_m"]) for row in passed_rows) if value is not None),
            default=None,
        ),
        "average_decision_count_passed": mean(safe_number(row["decision_count"]) for row in passed_rows),
        "average_recovery_count_passed": mean(safe_number(row["backtrack_or_recovery_count"]) for row in passed_rows),
        "endpoint_distribution": endpoint_counts,
        "failed_seeds": [row["seed"] for row in failed_rows],
        "timeout_seeds": [row["seed"] for row in rows if row["timed_out"]],
        "render_enabled": config.render,
        "timeout_per_seed_s": config.timeout_s,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the current SwarmSimulation over multiple deterministic seeds."
    )
    parser.add_argument(
        "--seeds",
        default="",
        help="Seed specification, e.g. 1-100 or 1,5,10,12345.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="Run seeds 1..COUNT when --seeds is omitted.",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        help="Show IR-SIM while running. Default is headless/no render.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=900.0,
        help="Wall-clock timeout per seed in seconds. Default: 900.",
    )
    parser.add_argument(
        "--label",
        default="",
        help="Optional batch label. Defaults to timestamp.",
    )
    parser.add_argument(
        "--mode",
        default="memory_only",
        choices=[
            "baseline", "memory_only", "rat_exchange",
            "memory_exchange", "all",
        ],
    )
    parser.add_argument(
        "--keep-success-logs",
        action="store_true",
        help="Keep all raw logs for passed runs. Default keeps them too; reserved for future compaction.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.seeds:
        seeds = parse_seed_spec(args.seeds)
    elif args.count > 0:
        seeds = list(range(1, args.count + 1))
    else:
        seeds = DEFAULT_SEEDS

    label = args.label.strip() or datetime.now().strftime("batch_%Y%m%d_%H%M%S")
    config = BatchConfig(
        seeds=seeds,
        render=bool(args.render),
        timeout_s=float(args.timeout),
        label=label,
        keep_success_logs=bool(args.keep_success_logs),
        experiment_mode=str(args.mode),
    )

    batch_root = PROJECT_ROOT / "batch_results" / label
    if batch_root.exists():
        raise RuntimeError(f"Batch output already exists: {batch_root}")
    (batch_root / "runs").mkdir(parents=True)
    (batch_root / "failures").mkdir(parents=True)

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "project_root": str(PROJECT_ROOT),
        "main_file": str(PROJECT_ROOT / "main.py"),
        "seeds": seeds,
        "render": config.render,
        "timeout_per_seed_s": config.timeout_s,
        "algorithm_source_snapshot": [
            "main.py",
            "autonomous_foraging_controller.py",
            "working_memory.py",
            "energy_sensor.py",
            "motion_controller.py",
            "irsim_backend.py",
        ],
    }
    (batch_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    rows: list[dict[str, Any]] = []
    for index, seed in enumerate(seeds, start=1):
        print(f"[{index}/{len(seeds)}] seed={seed} ...", flush=True)
        row = run_seed(
            seed,
            batch_root=batch_root,
            render=config.render,
            timeout_s=config.timeout_s,
            experiment_mode=config.experiment_mode,
        )
        rows.append(row)
        result_word = "PASS" if row["pass"] else "FAIL"
        print(
            f"    {result_word} endpoint={row['energy_endpoint']} "
            f"sim={row['simulation_time_s']}s home_error={row['home_error_m']}",
            flush=True,
        )

        if not row["pass"]:
            source = Path(row["run_directory"])
            failure_link = batch_root / "failures" / source.name
            # Copy rather than symlink for Windows compatibility and portable ZIPs.
            shutil.copytree(source, failure_link, dirs_exist_ok=True)

        write_csv(batch_root / "summary.csv", rows)

    failures = [row for row in rows if not row["pass"]]
    write_csv(batch_root / "failures.csv", failures)
    statistics = make_statistics(rows, config)
    (batch_root / "statistics.json").write_text(
        json.dumps(statistics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\nBatch complete")
    print(f"Passed: {statistics['passed_runs']}/{statistics['total_runs']}")
    print(f"Pass rate: {statistics['pass_rate_percent']}%")
    print(f"Results: {batch_root}")
    return 0 if statistics["failed_runs"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
