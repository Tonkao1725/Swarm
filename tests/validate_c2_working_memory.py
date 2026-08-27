"""Deterministic acceptance checks for C2's bounded cycle-local WM."""
from __future__ import annotations

import inspect
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "swarm_simulate"))

from c2_working_memory import CycleWorkingMemory
from experiment_modes import resolve_experiment_mode


def fill(memory: CycleWorkingMemory, cycle: int, count: int = 8) -> None:
    memory.start_cycle(cycle)
    for _ in range(count):
        memory.update_executed_motion(moved_m=0.30, heading_delta_rad=0.0, cycle_id=cycle)


def main() -> int:
    # A — disabled C1 isolation.
    c1 = CycleWorkingMemory(enabled=False)
    assert not c1.start_cycle(1) and c1.size == 0 and c1.return_target(1) is None
    assert not resolve_experiment_mode("baseline").working_memory_enabled

    # B/C — local cycle starts empty then accepts only current-cycle entries.
    wm = CycleWorkingMemory(enabled=True, maximum_entries=4, spacing_m=0.20)
    assert wm.start_cycle(1) and wm.size == 1
    assert wm.update_executed_motion(moved_m=0.25, heading_delta_rad=0.0, cycle_id=1) == "WM_ADD"
    assert wm.size == 2 and all(x.cycle_id == 1 for x in wm.entries)
    assert wm.update_executed_motion(moved_m=0.25, heading_delta_rad=0.0, cycle_id=2) is None

    # D — current cycle can read and consume retrace entries.
    assert wm.return_target(1) is not None and wm.read_count == 1
    wm.x_m, wm.y_m = wm.entries[-1].x_m, wm.entries[-1].y_m
    assert wm.pop_if_reached(1) and wm.pop_count == 1

    # E/F — reset destroys all prior-cycle information.
    assert wm.reset() and wm.size == 0 and wm.return_target(1) is None
    wm.start_cycle(2)
    assert wm.size == 1 and all(x.cycle_id == 2 for x in wm.entries)

    # H — central-place state machine still hard-codes HARVEST -> RETURN_HOME.
    baseline_source = (ROOT / "src" / "swarm_simulate" / "swarm_baseline.py").read_text(encoding="utf-8")
    assert 'scout.phase = "RETURN_HOME"' in baseline_source
    assert "WM_RETRACE" not in baseline_source.split("def _explore_command", 1)[1].split("def _return_command", 1)[0]

    # I — bound and pruning are strict on long exploration.
    bounded = CycleWorkingMemory(enabled=True, maximum_entries=4, spacing_m=0.01)
    fill(bounded, 7, 30)
    assert bounded.size == 4 and bounded.prune_count > 0 and bounded.max_size == 4

    # J — same executed odometry yields identical internal route state.
    left = CycleWorkingMemory(enabled=True); right = CycleWorkingMemory(enabled=True)
    fill(left, 3); fill(right, 3)
    assert left.entries == right.entries and left.return_target(3) == right.return_target(3)

    # G — code-level forbidden-ground-truth audit.
    module = inspect.getsource(sys.modules["c2_working_memory"])
    forbidden = ("nest_x_m", "nest_y_m", "resource_x_m", "resource_y_m", "A*", "Dijkstra", "planner", "random")
    assert not any(token.lower() in module.lower() for token in forbidden)
    print("PASS C2 acceptance A-J: isolation, cycle scope, return use, reset, bound, determinism, and ground-truth audit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
