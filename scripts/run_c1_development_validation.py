"""Run the three frozen Condition 1 development seeds serially.

This is deliberately a development gate, not research data: it stops as soon
as a run is not engineering-complete and experimentally valid.  Each run has
its own result directory and records source/seed-set provenance supplied by
the caller.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEEDS = (2118334751, 652974033, 920265301)
SEED_SET_SHA256 = "85d78ecddf4623f9344ab002e9ab5b84cd8aa71bb30ac3653ebc8a8874d7edd9"
PROJECT_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"


def main() -> int:
    label = os.environ.get("C1_VALIDATION_LABEL", "c1_contact_retry_final_validation")
    root = PROJECT_ROOT / "results" / label
    root.mkdir(parents=True, exist_ok=False)
    python = str(PROJECT_PYTHON if PROJECT_PYTHON.exists() else Path(sys.executable))
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
    ).strip()
    runs: list[dict[str, object]] = []
    for seed in SEEDS:
        run_id = f"seed{seed}_3600s"
        run_dir = root / run_id
        env = os.environ.copy()
        env.update({
            "FORAGING_SEED": str(seed),
            "SWARM_EXPERIMENT_MODE": "baseline",
            "SWARM_SCOUT_COUNT": "3",
            "SWARM_MISSION_MODE": "research",
            "NEST_ENERGY_TARGET": "6",
            "SWARM_SIM_DURATION_S": "3600",
            "FORAGING_TRIPS": "3",
            "IRSIM_RENDER": "0",
            "MPLBACKEND": "Agg",
            "SWARM_RESULTS_ROOT": str(root),
            "SWARM_RUN_ID": run_id,
            "SWARM_FREEZE_COMMIT": source_commit,
            "SWARM_FREEZE_TAG": "DEVELOPMENT_CONTACT_RETRY_FINAL_GATE",
            "SWARM_CANONICAL_SEED_SET_SHA256": SEED_SET_SHA256,
        })
        completed = subprocess.run(
            [python, "main.py"], cwd=PROJECT_ROOT, env=env,
            text=True, capture_output=True,
        )
        run_dir.mkdir(exist_ok=True)
        (run_dir / "console_stdout.txt").write_text(completed.stdout, encoding="utf-8")
        (run_dir / "console_stderr.txt").write_text(completed.stderr, encoding="utf-8")
        summary_path = run_dir / "swarm_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
        valid = (
            completed.returncode == 0
            and summary.get("engineering_status") == "COMPLETED"
            and summary.get("experimental_validity") == "VALID"
        )
        result = {"seed": seed, "returncode": completed.returncode, "valid": valid,
                  "summary": summary}
        runs.append(result)
        (root / "development_validation_status.json").write_text(
            json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(),
                        "source_commit": source_commit, "runs": runs,
                        "stopped_early": not valid}, indent=2),
            encoding="utf-8",
        )
        if not valid:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
