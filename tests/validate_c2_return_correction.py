"""Deterministic regression tests for the F3/F4 Return correction.

Tests M, N, O, P, Q from the correction task. These exercise
``BaselineSwarmRunner._return_command`` directly against a minimal,
env-free harness (no IR-SIM instance is created), so they run fast and
without a display. Only the fields ``_return_command`` and the helper
methods it calls actually touch are set on the runner/scout/snapshot
stand-ins; the class is never asked to do anything beyond that one method.
"""
from __future__ import annotations

import math
import random
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "swarm_simulate"))

from c2_working_memory import CycleWorkingMemory
from swarm_baseline import BaselineSwarmRunner, ScoutState


def make_runner(*, stuck_limit: int = 5) -> BaselineSwarmRunner:
    """Build a BaselineSwarmRunner with only the attributes _return_command
    and its helpers read -- no IR-SIM environment is created."""
    runner = object.__new__(BaselineSwarmRunner)
    runner.working_memory_enabled = True
    runner.safe_front_m = 0.72
    runner.turn_side_clearance_m = 0.42
    runner.linear_speed_mps = 0.30
    runner.turn_angle_rad = math.radians(45.0)
    runner.angular_speed_radps = math.radians(90.0)
    runner.return_stationary_turn_limit = stuck_limit
    runner.env = SimpleNamespace(step_time=0.1)
    return runner


def make_scout(cycle_id: int = 1) -> ScoutState:
    scout = ScoutState(scout_id=0, rng=random.Random(1))
    scout.phase = "RETURN_HOME"
    scout.cycle_id = cycle_id
    return scout


def clear_snapshot(front_m: float = 5.0, left_m: float = 5.0, right_m: float = 5.0):
    return SimpleNamespace(front_m=front_m, left_m=left_m, right_m=right_m)


def clear_sensor():
    # inside=False means _forward_body_clearance_safe's corner check never
    # fires -- a deliberately "nothing nearby" fixture for isolating WM
    # decision logic from local-safety behavior in Tests M/N/P.
    return SimpleNamespace(ray_distance=lambda offset: (5.0, None, False, False))


def build_memory_with_single_origin(dx: float, dy: float) -> CycleWorkingMemory:
    """A WM whose only remaining entry is the cycle origin, with the Scout
    currently `dx, dy` away from it -- the exact end-of-retrace state
    identified in the root-cause analysis (Part K / F4)."""
    memory = CycleWorkingMemory(enabled=True)
    memory.start_cycle(1)
    memory.x_m, memory.y_m = dx, dy
    assert len(memory.entries) == 1, "fixture must start with only the origin entry"
    return memory


def test_m_final_origin_retrace() -> None:
    """TEST M -- WM must keep steering toward the final origin breadcrumb
    instead of silently switching to the untargeted C1 stateless fallback
    merely because only one entry (the origin) remains."""
    runner = make_runner()
    scout = make_scout()
    scout.working_memory = build_memory_with_single_origin(dx=0.50, dy=0.0)
    assert len(scout.working_memory.entries) == 1

    snapshot = clear_snapshot()
    sensor = clear_sensor()
    linear, angular, action = runner._return_command(scout, snapshot, sensor)

    assert action.startswith("WM_"), (
        f"expected WM-guided action with one valid origin entry remaining, got {action!r}"
    )
    assert not action.startswith("RETURN_LOCAL_"), (
        "must not fall back to the untargeted C1 stateless branch while a "
        "valid single-entry WM target still exists"
    )
    print("PASS Test M: final-origin breadcrumb remains a valid WM navigation target")


def test_n_origin_nest_handoff_gap() -> None:
    """TEST N -- inside the WM pop tolerance (0.28 m) but outside the Nest
    delivery radius (0.12 m), the Scout must not lose its WM reference."""
    from c2_working_memory import CycleWorkingMemory as _CWM
    import inspect
    src = inspect.getsource(_CWM.pop_if_reached)
    assert "0.28" in src, "WM pop tolerance constant moved; re-check gap assumption"

    NEST_DELIVERY_RADIUS_M = 0.12  # swarm_baseline.py: self.nest_delivery_radius_m
    WM_POP_TOLERANCE_M = 0.28      # c2_working_memory.py: pop_if_reached tolerance_m
    gap_distance = 0.20            # strictly inside (0.12, 0.28)
    assert NEST_DELIVERY_RADIUS_M < gap_distance < WM_POP_TOLERANCE_M

    runner = make_runner()
    scout = make_scout()
    scout.working_memory = build_memory_with_single_origin(dx=gap_distance, dy=0.0)

    snapshot = clear_snapshot()
    sensor = clear_sensor()
    linear, angular, action = runner._return_command(scout, snapshot, sensor)

    assert action.startswith("WM_"), (
        f"Scout at {gap_distance} m (inside WM pop tolerance, outside Nest "
        f"delivery radius) must still receive WM-guided final-approach "
        f"navigation, got {action!r}"
    )
    print("PASS Test N: WM guidance is preserved inside the pop-tolerance/Nest-radius gap")


def test_o_oscillation_detection() -> None:
    """TEST O -- a Return that repeatedly re-selects the same WM target
    with zero net local progress must not be allowed to continue
    indefinitely; the route-reacquisition mechanism must activate within
    the bounded window."""
    STUCK_LIMIT = 6
    runner = make_runner(stuck_limit=STUCK_LIMIT)
    scout = make_scout()
    memory = CycleWorkingMemory(enabled=True)
    memory.start_cycle(1)
    # Two entries: origin, plus one outbound breadcrumb the Scout is
    # (nominally) trying to retrace toward but never actually reaches --
    # exactly the repeated-no-progress condition from the root-cause
    # analysis (DEV01_Scout2 et al.), reproduced deterministically instead
    # of relying on the observed 14.8 s period.
    memory.entries.append(memory.entries[0])  # placeholder replaced below
    memory.entries[-1] = type(memory.entries[0])(1, 2.0, 0.0)
    scout.working_memory = memory
    starting_len = len(memory.entries)
    assert starting_len == 2

    snapshot = clear_snapshot()  # no obstacle geometry involved -- isolates the stuck-progress logic itself
    sensor = clear_sensor()

    actions = []
    reacquired_at = None
    for i in range(STUCK_LIMIT + 2):
        # Local pose never advances: no update_executed_motion call, exactly
        # reproducing "commanded motion did not translate the Scout."
        linear, angular, action = runner._return_command(scout, snapshot, sensor)
        actions.append(action)
        if action == "WM_ROUTE_REACQUIRE":
            reacquired_at = i
            break

    assert reacquired_at is not None, (
        f"no-progress WM retrace never triggered route reacquisition within "
        f"{STUCK_LIMIT + 2} ticks (bound={STUCK_LIMIT}); actions={actions}"
    )
    assert reacquired_at + 1 <= STUCK_LIMIT + 1, "reacquisition must fire at/near the configured bound, not late"
    assert len(memory.entries) == starting_len - 1, "reacquisition must drop exactly the stuck target"
    assert memory.skip_count == 1
    print(f"PASS Test O: stuck WM retrace triggers route reacquisition after {reacquired_at} ticks "
          f"(bound={STUCK_LIMIT}); actions={actions}")


def test_p_route_reacquisition_resumes_wm() -> None:
    """TEST P -- after a route-reacquisition event, C2 must resume
    WM-guided retrace (using the next-older breadcrumb) rather than
    permanently falling back to the untargeted C1 stateless branch."""
    STUCK_LIMIT = 4
    runner = make_runner(stuck_limit=STUCK_LIMIT)
    scout = make_scout()
    memory = CycleWorkingMemory(enabled=True)
    memory.start_cycle(1)
    Entry = type(memory.entries[0])
    # origin, then two outbound breadcrumbs at increasing distance so a
    # skip has a genuinely different (reachable) next target to resume on.
    memory.entries.append(Entry(1, 1.0, 0.0))
    memory.entries.append(Entry(1, 3.0, 0.0))
    scout.working_memory = memory

    snapshot = clear_snapshot()
    sensor = clear_sensor()

    saw_reacquire = False
    saw_wm_after_reacquire = False
    for _ in range(STUCK_LIMIT + 3):
        linear, angular, action = runner._return_command(scout, snapshot, sensor)
        if action == "WM_ROUTE_REACQUIRE":
            saw_reacquire = True
            continue
        if saw_reacquire:
            saw_wm_after_reacquire = action.startswith("WM_")
            assert not action.startswith("RETURN_LOCAL_"), (
                "C1 stateless fallback must not permanently replace WM "
                "navigation after a route-reacquisition event"
            )
            break

    assert saw_reacquire, "route reacquisition never triggered in this fixture"
    assert saw_wm_after_reacquire, "WM-guided retrace did not resume after route reacquisition"
    print("PASS Test P: WM retrace resumes on the next-older breadcrumb after route reacquisition")


def test_q_no_global_navigation() -> None:
    """TEST Q -- audit the new F3/F4 code for forbidden global-navigation
    inputs (ground truth, shared map, planner, shortest path, RNG)."""
    baseline_src = (ROOT / "src" / "swarm_simulate" / "swarm_baseline.py").read_text(encoding="utf-8")
    wm_src = (ROOT / "src" / "swarm_simulate" / "c2_working_memory.py").read_text(encoding="utf-8")

    # Isolate exactly the new/changed region so pre-existing, unrelated
    # code elsewhere in the file cannot mask a real finding here.
    start = baseline_src.index("memory = scout.working_memory")
    end = baseline_src.index("if snapshot.front_m <= self.safe_front_m:", start)
    changed_region = baseline_src[start:end]

    forbidden = (
        "nest_x_m", "nest_y_m", "resource_x_m", "resource_y_m",
        "a_star", "a*", "dijkstra", "shortest_path", "global_planner",
        "shared_map", "self.env.robot_list", "ground_truth", "self._pose(",
    )
    lowered = changed_region.lower()
    hits = [tok for tok in forbidden if tok.lower() in lowered]
    assert not hits, f"forbidden global-navigation token(s) found in F3/F4 code: {hits}"
    assert "random" not in changed_region and "rng" not in changed_region.lower(), (
        "F3/F4 route reacquisition must not consume any RNG"
    )
    assert "skip_unreachable" in wm_src and "self.entries" in wm_src.split("def skip_unreachable", 1)[1].split("def ", 1)[0]
    print("PASS Test Q: F3/F4 code uses no global Nest/Resource coordinates, map, planner, or RNG")


def main() -> int:
    test_m_final_origin_retrace()
    test_n_origin_nest_handoff_gap()
    test_o_oscillation_detection()
    test_p_route_reacquisition_resumes_wm()
    test_q_no_global_navigation()
    print("PASS Tests M-Q: F3/F4 Return correction regression suite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
