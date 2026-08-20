"""Run an explicitly supplied, bounded C1 advisor-preview stage in parallel."""
from __future__ import annotations

import concurrent.futures
import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
CANONICAL_FIRST_FIVE = {
    "R01": 82784102, "R02": 98386804, "R03": 358777504,
    "R04": 385197017, "R05": 413997162,
}


def parse_stage() -> list[tuple[str, int]]:
    names = [item.strip() for item in os.environ["C1_PREVIEW_IDS"].split(",") if item.strip()]
    if not names or any(name not in CANONICAL_FIRST_FIVE for name in names):
        raise ValueError("C1_PREVIEW_IDS must name only R01-R05")
    return [(name, CANONICAL_FIRST_FIVE[name]) for name in names]


def run_one(root: Path, research_id: str, seed: int) -> dict[str, object]:
    run_id = f"{research_id}_seed{seed}_3600s"
    env = os.environ.copy()
    env.update({
        "FORAGING_SEED": str(seed), "SWARM_EXPERIMENT_MODE": "baseline",
        "SWARM_SCOUT_COUNT": "3", "SWARM_MISSION_MODE": "research",
        "NEST_ENERGY_TARGET": "6", "SWARM_SIM_DURATION_S": "3600",
        "FORAGING_TRIPS": "3", "IRSIM_RENDER": "0", "MPLBACKEND": "Agg",
        "FAST_HEADLESS_RESEARCH_MODE": "1", "SWARM_RESULTS_ROOT": str(root),
        "SWARM_RUN_ID": run_id,
        "SWARM_FREEZE_COMMIT": os.environ["C1_RESEARCH_COMMIT"],
        "SWARM_FREEZE_TAG": os.environ["C1_RESEARCH_TAG"],
        "SWARM_CANONICAL_SEED_SET_SHA256": "85d78ecddf4623f9344ab002e9ab5b84cd8aa71bb30ac3653ebc8a8874d7edd9",
    })
    process = subprocess.run([str(PYTHON), "main.py"], cwd=ROOT, env=env, text=True, capture_output=True)
    run_dir = root / run_id
    run_dir.mkdir(exist_ok=True)
    (run_dir / "console_stdout.txt").write_text(process.stdout, encoding="utf-8")
    (run_dir / "console_stderr.txt").write_text(process.stderr, encoding="utf-8")
    summary_path = run_dir / "swarm_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    valid = process.returncode == 0 and summary.get("engineering_status") == "COMPLETED" and summary.get("experimental_validity") == "VALID"
    return {"research_id": research_id, "seed": seed, "returncode": process.returncode, "valid": valid, "summary": summary}


def main() -> int:
    stage = parse_stage()
    root = ROOT / "results" / os.environ["C1_PREVIEW_STAGE_LABEL"]
    root.mkdir(parents=True, exist_ok=False)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(stage))) as executor:
        results = list(executor.map(lambda item: run_one(root, *item), stage))
    results.sort(key=lambda row: row["research_id"])
    (root / "stage_status.json").write_text(json.dumps({"classification": "PRELIMINARY_C1_ADVISOR_REVIEW", "runs": results}, indent=2), encoding="utf-8")
    return 0 if all(row["valid"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
