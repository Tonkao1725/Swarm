"""Wait for the final development gate, freeze the source, then start R01-R20."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parent.parent
GATE = PROJECT_ROOT / "results" / "c1_contact_retry_final_validation_20260818_v2" / "development_validation_status.json"
TAG = "baseline-condition1-v3"
LABEL = "baseline_research_20seed_v3_20260818"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=PROJECT_ROOT, text=True).strip()


def main() -> int:
    for _ in range(360):
        if GATE.exists():
            state = json.loads(GATE.read_text(encoding="utf-8"))
            runs = state.get("runs", [])
            if len(runs) == 3:
                if state.get("stopped_early") or not all(row.get("valid") for row in runs):
                    return 1
                break
        time.sleep(10)
    else:
        return 2
    existing = git("tag", "-l", TAG)
    if existing:
        raise RuntimeError(f"Refusing to overwrite existing tag: {TAG}")
    source = git("rev-parse", "HEAD")
    git("tag", "-a", TAG, "-m", "Condition 1 baseline freeze v3: bounded contact recovery verified")
    env = os.environ.copy()
    env.update({"C1_RESEARCH_LABEL": LABEL, "C1_RESEARCH_COMMIT": source,
                "C1_RESEARCH_TAG": TAG})
    return subprocess.call([sys.executable, "scripts/run_c1_research_batch.py"],
                           cwd=PROJECT_ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
