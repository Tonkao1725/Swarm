"""Serial canonical Condition 1 research batch; stop immediately on invalid data."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
SEEDS = (82784102, 98386804, 358777504, 385197017, 413997162, 517647040,
         565425870, 711213266, 1055674384, 1116278677, 1173346196,
         1191607443, 1308983833, 1399633088, 1672527435, 1710654405,
         1729431144, 1759674302, 1763236383, 1985724812)
SEED_SET_SHA256 = "85d78ecddf4623f9344ab002e9ab5b84cd8aa71bb30ac3653ebc8a8874d7edd9"


def main() -> int:
    label = os.environ["C1_RESEARCH_LABEL"]
    commit = os.environ["C1_RESEARCH_COMMIT"]
    tag = os.environ["C1_RESEARCH_TAG"]
    root = PROJECT_ROOT / "results" / label
    resume_from = int(os.environ.get("C1_RESEARCH_RESUME_FROM", "1"))
    if resume_from == 1:
        root.mkdir(parents=True, exist_ok=False)
        completed: list[dict[str, object]] = []
    else:
        status_path = root / "batch_status.json"
        if not status_path.exists():
            raise RuntimeError("Resume requested but no prior batch status exists")
        prior = json.loads(status_path.read_text(encoding="utf-8"))
        completed = list(prior.get("completed_runs", []))
        if len(completed) != resume_from - 1 or not all(row.get("valid") for row in completed):
            raise RuntimeError("Resume point does not match an all-valid prior prefix")
    for index, seed in enumerate(SEEDS[resume_from - 1:], start=resume_from):
        suffix = "_rerun" if index == resume_from and resume_from > 1 else ""
        run_id = f"R{index:02d}{suffix}_seed{seed}_3600s"
        run_dir = root / run_id
        env = os.environ.copy()
        env.update({
            "FORAGING_SEED": str(seed), "SWARM_EXPERIMENT_MODE": "baseline",
            "SWARM_SCOUT_COUNT": "3", "SWARM_MISSION_MODE": "research",
            "NEST_ENERGY_TARGET": "6", "SWARM_SIM_DURATION_S": "3600",
            "FORAGING_TRIPS": "3", "IRSIM_RENDER": "0", "MPLBACKEND": "Agg",
            "SWARM_RESULTS_ROOT": str(root), "SWARM_RUN_ID": run_id,
            "SWARM_FREEZE_COMMIT": commit, "SWARM_FREEZE_TAG": tag,
            "SWARM_CANONICAL_SEED_SET_SHA256": SEED_SET_SHA256,
        })
        process = subprocess.run([str(PYTHON), "main.py"], cwd=PROJECT_ROOT,
                                 env=env, text=True, capture_output=True)
        run_dir.mkdir(exist_ok=True)
        (run_dir / "console_stdout.txt").write_text(process.stdout, encoding="utf-8")
        (run_dir / "console_stderr.txt").write_text(process.stderr, encoding="utf-8")
        summary_path = run_dir / "swarm_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
        valid = (process.returncode == 0 and summary.get("engineering_status") == "COMPLETED"
                 and summary.get("experimental_validity") == "VALID")
        completed.append({"research_id": f"R{index:02d}", "seed": seed,
                          "returncode": process.returncode, "valid": valid,
                          "summary": summary})
        status = {"updated_at": datetime.now(timezone.utc).isoformat(), "source_commit": commit,
                  "freeze_tag": tag, "canonical_seed_set_sha256": SEED_SET_SHA256,
                  "completed_runs": completed, "stopped_early": not valid}
        (root / "batch_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        if not valid:
            (root / "BATCH_STOPPED.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
