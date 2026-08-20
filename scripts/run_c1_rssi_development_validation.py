"""Run the three gated canonical-C1 development validations safely."""
from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
SEEDS = (2118334751, 652974033, 920265301)


def run_one(root: Path, seed: int, duration_s: float) -> dict[str, object]:
    run_id = f"seed{seed}_canonical_c1_3600s"
    run_dir = root / run_id
    env = os.environ.copy()
    env.update({
        "FORAGING_SEED": str(seed), "SWARM_EXPERIMENT_MODE": "baseline",
        "SWARM_SCOUT_COUNT": "3", "SWARM_MISSION_MODE": "research",
        "NEST_ENERGY_TARGET": "6", "FORAGING_TRIPS": "3",
        "SWARM_SIM_DURATION_S": str(duration_s), "SWARM_RESULTS_ROOT": str(root),
        "SWARM_RUN_ID": run_id, "MPLBACKEND": "Agg", "IRSIM_RENDER": "0",
        "FAST_HEADLESS_RESEARCH_MODE": "1",
    })
    process = subprocess.run([str(PYTHON), "main.py"], cwd=ROOT, env=env,
                             text=True, capture_output=True)
    run_dir.mkdir(exist_ok=True)
    (run_dir / "console_stdout.txt").write_text(process.stdout, encoding="utf-8")
    (run_dir / "console_stderr.txt").write_text(process.stderr, encoding="utf-8")
    summary_path = run_dir / "swarm_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    valid = (
        process.returncode == 0
        and summary.get("engineering_status") == "COMPLETED"
        and summary.get("experimental_validity") == "VALID"
        and summary.get("mission_mode") == "research"
        and summary.get("nest_energy_target") == 6
        and summary.get("return_navigation") == "STATELESS_LOCAL_REACTIVE_NO_RSSI_STEERING"
        and not any(scout.get("contact_stalled") for scout in summary.get("scouts", []))
        and not any(scout.get("persistent_stationary_turn_deadlock") for scout in summary.get("scouts", []))
    )
    return {"seed": seed, "run_id": run_id, "returncode": process.returncode,
            "valid": valid, "summary": summary}


def main() -> int:
    duration_s = float(os.environ.get("C1_DEVELOPMENT_DURATION_S", "3600"))
    label = os.environ.get("C1_DEVELOPMENT_LABEL", "canonical_c1_development_validation_20260820")
    root = ROOT / "results" / label
    root.mkdir(parents=True, exist_ok=False)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(SEEDS)) as executor:
        futures = [executor.submit(run_one, root, seed, duration_s) for seed in SEEDS]
        completed = [future.result() for future in futures]
    completed.sort(key=lambda item: SEEDS.index(item["seed"]))
    report = {
        "classification": "DEVELOPMENT_VALIDATION_NOT_RESEARCH_DATA",
        "created_at": datetime.now(timezone.utc).isoformat(), "seeds": list(SEEDS),
        "duration_s": duration_s, "parallel_processes": len(SEEDS),
        "fast_headless_semantics": "same dt, physics, sensors, controller, RNG; rendering disabled only",
        "completed_runs": completed,
        "verdict": "PASS" if all(item["valid"] for item in completed) else "FAIL",
    }
    (root / "development_validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"{report['verdict']}: {root}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
