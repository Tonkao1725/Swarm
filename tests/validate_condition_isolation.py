"""Fast scope check for Conditions 1–3.

This is intentionally independent of IR-SIM: it protects the experimental
boundary before a long regression run is started.
"""
from __future__ import annotations

import inspect
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = PROJECT_ROOT / "src" / "swarm_simulate"
sys.path.insert(0, str(SOURCE_ROOT))

from autonomous_foraging_controller import AutonomousForagingController
from experiment_modes import resolve_experiment_mode


def main() -> int:
    baseline = resolve_experiment_mode("baseline")
    wm = resolve_experiment_mode("working_memory")
    em = resolve_experiment_mode("experience_memory")

    assert not baseline.working_memory_enabled
    assert not baseline.experience_memory_enabled
    assert wm.working_memory_enabled
    assert not wm.experience_memory_enabled
    assert em.working_memory_enabled
    assert em.experience_memory_enabled

    source = inspect.getsource(AutonomousForagingController)
    assert "_return_home_by_reverse_trail" not in source
    assert "return_commands(" not in source
    assert "motor_command_replay_enabled\":False" in source
    assert "_return_home_baseline" in source
    assert "if not self._working_memory_active:" in source
    assert "if self.config.route_experience_enabled:" in source

    working_memory_source = (SOURCE_ROOT / "working_memory.py").read_text(
        encoding="utf-8"
    )
    assert "def return_commands" not in working_memory_source

    print("PASS: Conditions 1–3 are isolated; no motor-command replay remains")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
