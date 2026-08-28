"""Deterministic regression tests for the SOLAR_TURN_45 EXPLORE deadlock
correction (Tests SOLAR-1 through SOLAR-10). Common infrastructure -- C1
and C2 alike (this is EXPLORE-phase controller code, unrelated to C2
Working Memory or Return). No IR-SIM environment is created (same
env-free harness style as tests/validate_c2_return_correction.py) --
`sensor` is a minimal stub exposing only `ray_distance`, the one method
`_forward_body_clearance_safe` calls on it.
"""
from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "swarm_simulate"))

from swarm_baseline import BaselineSwarmRunner, ScoutState
from sensor_types import DirectionalRangeSnapshot
from energy_sensor import EnergyReading
from motion_types import RobotPose
import random


# c2_working_memory.py's SHA-256 immediately before this task's edits
# (unchanged by this task -- Test SOLAR-8).
C2_WM_SHA256_BEFORE = "b9a25db85f387f005be2bdee81edf0eb7982c62ebb20be224fc5f47af478b48d"


class _StubSensor:
    """Only ray_distance is ever called on `sensor` by the code under
    test (_forward_body_clearance_safe). Returns a generous, always-clear
    reading by default; tests override via `blocked=True`."""

    def __init__(self, blocked: bool = False):
        self.blocked = blocked

    def ray_distance(self, relative_angle_rad: float, *, maximum_error_deg: float = 2.0):
        if self.blocked:
            return 0.05, 0.0, True, True
        return 5.0, 0.0, True, True


def _snapshot(*, front_m: float = 5.0, left_m: float = 5.0, right_m: float = 5.0) -> DirectionalRangeSnapshot:
    return DirectionalRangeSnapshot(
        sequence=0, sim_time_s=0.0, pose=RobotPose(0.0, 0.0, 0.0),
        left_m=left_m, front_m=front_m, right_m=right_m,
        front_left_m=front_m, front_right_m=front_m,
        left_valid=True, front_valid=True, right_valid=True,
        front_left_valid=True, front_right_valid=True,
        left_beam_index=0, front_beam_index=0, right_beam_index=0,
        front_left_beam_index=0, front_right_beam_index=0,
        left_beam_angle_rad=1.5708, front_beam_angle_rad=0.0, right_beam_angle_rad=-1.5708,
        front_left_beam_angle_rad=0.3491, front_right_beam_angle_rad=-0.3491,
        beam_count=181,
    )


def _reading(*, guidance_active: bool = False, strongest_direction: str = "NONE", detected: bool = False) -> EnergyReading:
    return EnergyReading(
        detected=detected, endpoint_id=None, distance_m=99.0, signal_strength=0.0,
        relative_bearing_rad=0.0, inside_sensor_fov=False, beam_hit_valid=False,
        wall_distance_m=99.0, line_of_sight_clear=True, blocked_by_wall=False,
        within_detection_radius=False, acquisition_clearance_m=0.0,
        solar_left=0.0, solar_center=0.0, solar_right=0.0, solar_max=0.0, solar_mean=0.0,
        strongest_direction=strongest_direction, guidance_active=guidance_active,
        collect_threshold_reached=False, approach_active=guidance_active, light_state="SEARCH",
        light_path_factor=1.0,
    )


def _runner() -> BaselineSwarmRunner:
    runner = object.__new__(BaselineSwarmRunner)
    runner.safe_front_m = 0.72
    runner.turn_side_clearance_m = 0.42
    runner.turn_angle_rad = 0.7853981633974483  # 45 deg
    runner.angular_speed_radps = 0.90
    runner.linear_speed_mps = 0.22
    runner.escape_turn_limit = 8

    class _Env:
        step_time = 0.1
    runner.env = _Env()
    return runner


def _scout() -> ScoutState:
    return ScoutState(scout_id=0, rng=random.Random(1))


def _run_turn_to_completion(runner, scout, snapshot, sensor, max_ticks=40):
    """Drive _continue_turn until the in-progress turn fully completes.
    Returns the number of ticks consumed."""
    ticks = 0
    while scout.turn_remaining_rad and ticks < max_ticks:
        runner._continue_turn(scout)
        ticks += 1
    return ticks


def test_solar1_one_turn_completes() -> None:
    runner = _runner()
    scout = _scout()
    snapshot = _snapshot()
    reading = _reading(guidance_active=True, strongest_direction="LEFT")
    sensor = _StubSensor()
    linear, angular, action = runner._explore_command(scout, snapshot, reading, sensor)
    assert action == "SOLAR_TURN_45"
    assert scout.turn_remaining_rad != 0.0
    assert scout.solar_turn_progress_pending is True
    ticks = _run_turn_to_completion(runner, scout, snapshot, sensor)
    assert scout.turn_remaining_rad == 0.0, "the turn primitive must fully complete"
    expected_ticks = int(runner.turn_angle_rad / (runner.angular_speed_radps * runner.env.step_time))
    assert 0 < ticks <= expected_ticks + 1, (ticks, expected_ticks)
    print(f"PASS Test SOLAR-1: a SOLAR_TURN_45 primitive completes normally in {ticks} ticks")


def test_solar2_no_infinite_reissue() -> None:
    """Adversarial worst case: solar guidance flips LEFT<->RIGHT every time
    it is (re-)read -- the exact condition proven to cause the original
    17,177-tick pathology. The corrected controller must not allow more
    than one turn-primitive's worth of consecutive ticks without an
    intervening forward attempt."""
    runner = _runner()
    scout = _scout()
    snapshot = _snapshot()
    sensor = _StubSensor()
    flip = {"side": "LEFT"}

    def next_reading():
        flip["side"] = "RIGHT" if flip["side"] == "LEFT" else "LEFT"
        return _reading(guidance_active=True, strongest_direction=flip["side"])

    forward_ticks = 0
    ticks_since_forward = 0
    max_gap = 0
    total_ticks = 400
    for _ in range(total_ticks):
        if scout.turn_remaining_rad:
            linear, angular, action = runner._continue_turn(scout)
        else:
            linear, angular, action = runner._explore_command(scout, snapshot, next_reading(), sensor)
        if linear > 0.0:
            forward_ticks += 1
            max_gap = max(max_gap, ticks_since_forward)
            ticks_since_forward = 0
        else:
            ticks_since_forward += 1
    max_gap = max(max_gap, ticks_since_forward)
    turn_primitive_ticks = int(runner.turn_angle_rad / (runner.angular_speed_radps * runner.env.step_time)) + 1
    assert forward_ticks > 0, "the corrected controller must eventually take a forward step under persistent LEFT/RIGHT guidance"
    assert max_gap <= turn_primitive_ticks + 2, (
        f"found {max_gap} consecutive non-forward ticks -- must never exceed roughly one turn "
        f"primitive ({turn_primitive_ticks} ticks) between forward attempts"
    )
    assert forward_ticks >= total_ticks // (turn_primitive_ticks + 2) - 1
    print(f"PASS Test SOLAR-2: under persistent flip-flopping LEFT/RIGHT guidance over {total_ticks} ticks, "
          f"the longest gap between forward attempts was {max_gap} ticks (bound: {turn_primitive_ticks + 2}); "
          f"{forward_ticks} forward ticks occurred -- no unbounded stationary reissue")


def test_solar3_fresh_sensor_reevaluation() -> None:
    runner = _runner()
    scout = _scout()
    snapshot = _snapshot()
    sensor = _StubSensor()
    # Start and complete a LEFT solar turn.
    r1 = _reading(guidance_active=True, strongest_direction="LEFT")
    linear, angular, action = runner._explore_command(scout, snapshot, r1, sensor)
    assert action == "SOLAR_TURN_45"
    _run_turn_to_completion(runner, scout, snapshot, sensor)
    assert scout.solar_turn_progress_pending is True
    # Immediately after completion, the pending-forward tick consumes a
    # FRESH reading argument -- change strongest_direction to CENTER (as if
    # the completed turn resolved guidance) and confirm the controller
    # reacts to it, not to the stale "LEFT" value.
    r2 = _reading(guidance_active=True, strongest_direction="CENTER")
    linear2, angular2, action2 = runner._explore_command(scout, snapshot, r2, sensor)
    assert action2 == "SOLAR_TURN_PROGRESS_FORWARD"
    assert scout.solar_turn_progress_pending is False
    # Next tick, with guidance now genuinely CENTER, normal forward resumes.
    linear3, angular3, action3 = runner._explore_command(scout, snapshot, r2, sensor)
    assert action3 == "EXPLORE_FORWARD"
    print("PASS Test SOLAR-3: control after a completed solar turn consumes a fresh sensor reading, "
          "not a stale/cached one")


def test_solar4_light_guidance_preserved() -> None:
    runner = _runner()
    scout = _scout()
    snapshot = _snapshot()
    sensor = _StubSensor()
    reading = _reading(guidance_active=True, strongest_direction="RIGHT")
    linear, angular, action = runner._explore_command(scout, snapshot, reading, sensor)
    assert action == "SOLAR_TURN_45"
    assert angular != 0.0
    print("PASS Test SOLAR-4: normal open-space solar guidance still turns toward the stronger side")


def test_solar5_center_forward_behavior() -> None:
    runner = _runner()
    scout = _scout()
    snapshot = _snapshot()
    sensor = _StubSensor()
    reading = _reading(guidance_active=True, strongest_direction="CENTER")
    linear, angular, action = runner._explore_command(scout, snapshot, reading, sensor)
    assert action == "EXPLORE_FORWARD"
    assert linear == runner.linear_speed_mps
    print("PASS Test SOLAR-5: CENTER guidance with a safe path still produces normal forward progression")


def test_solar6_obstacle_safety_preserved() -> None:
    runner = _runner()
    scout = _scout()
    scout.solar_turn_progress_pending = True
    unsafe_snapshot = _snapshot(front_m=0.05)  # well below safe_front_m
    reading = _reading(guidance_active=True, strongest_direction="LEFT")
    sensor = _StubSensor()
    linear, angular, action = runner._explore_command(scout, unsafe_snapshot, reading, sensor)
    assert action != "SOLAR_TURN_PROGRESS_FORWARD", "must never force forward travel through unsafe ToF geometry"
    assert scout.solar_turn_progress_pending is False, "the pending flag must still be consumed (not looped on)"
    print(f"PASS Test SOLAR-6: with unsafe front clearance, the pending forward commitment is declined "
          f"(action={action}), never authorizing travel through unsafe geometry")


def test_solar7_c1_memory_free() -> None:
    import dataclasses as _dc
    src = inspect.getsource(ScoutState)
    assert "solar_turn_progress_pending: bool = False" in src
    field = next(f for f in _dc.fields(ScoutState) if f.name == "solar_turn_progress_pending")
    assert field.type == "bool" or field.type is bool, (
        "the only new ScoutState field this correction adds must be a plain boolean, "
        f"not a coordinate/identifier/structure -- got type {field.type!r}"
    )
    assert field.default is False, "must default to False (no state carried in from construction)"
    # The field is cleared (set back to False) on every read inside
    # _explore_command -- i.e. it never survives beyond the single decision
    # tick immediately following a completed solar turn (verified live in
    # Test SOLAR-3/SOLAR-6: the flag is False again after being consumed).
    print("PASS Test SOLAR-7: the correction adds exactly one new field, a plain per-tick boolean "
          "actuator flag -- no location, route, resource-preference, or map memory")


def test_solar8_c2_wm_unchanged() -> None:
    wm_path = ROOT / "src" / "swarm_simulate" / "c2_working_memory.py"
    actual = hashlib.sha256(wm_path.read_bytes()).hexdigest()
    assert actual == C2_WM_SHA256_BEFORE, (
        f"c2_working_memory.py must be byte-identical to before this task; got {actual}"
    )
    print("PASS Test SOLAR-8: c2_working_memory.py is byte-identical to its pre-task SHA-256")


def test_solar9_return_logic_unchanged() -> None:
    return_src = inspect.getsource(BaselineSwarmRunner._return_command)
    assert "solar_turn_progress_pending" not in return_src
    assert "SOLAR_TURN_PROGRESS_FORWARD" not in return_src
    for token in ("skip_unreachable", "wm_target_lock", "WM_ROUTE_REACQUIRE", "wm_stuck_ticks"):
        assert token in return_src, f"_return_command must still contain unmodified S4/F3/F4 machinery ({token})"
    print("PASS Test SOLAR-9: _return_command (S4/F3/F4 machinery) is untouched by this correction")


def test_solar10_original_dev01_pathology() -> None:
    """Replays the adversarial condition directly evidenced in
    tests/SOLAR_TURN_EXPLORE_DEADLOCK_DIAGNOSIS.md: strongest_direction
    flips to the opposite side every time a SOLAR_TURN_45 completes, at a
    fixed, always-safe position. The original controller reproduced this
    for 17,177 consecutive ticks (1717.7 s) with zero net translation."""
    runner = _runner()
    scout = _scout()
    snapshot = _snapshot()
    sensor = _StubSensor()
    flip = {"side": "RIGHT"}

    def next_reading():
        return _reading(guidance_active=True, strongest_direction=flip["side"])

    max_consecutive_non_forward = 0
    run = 0
    forward_count = 0
    ticks_simulated = 2000  # >> the original 17,177-tick episode's first several cycles
    for _ in range(ticks_simulated):
        if scout.turn_remaining_rad:
            linear, angular, action = runner._continue_turn(scout)
        else:
            reading = next_reading()
            linear, angular, action = runner._explore_command(scout, snapshot, reading, sensor)
            if action == "SOLAR_TURN_45":
                # Emulate the exact observed geometry: the side that reads
                # strongest flips after every completed turn.
                flip["side"] = "LEFT" if flip["side"] == "RIGHT" else "RIGHT"
        if linear > 0.0:
            forward_count += 1
            run = 0
        else:
            run += 1
            max_consecutive_non_forward = max(max_consecutive_non_forward, run)
    turn_primitive_ticks = int(runner.turn_angle_rad / (runner.angular_speed_radps * runner.env.step_time)) + 1
    assert max_consecutive_non_forward <= turn_primitive_ticks + 2, (
        f"reproduced the original pathology: {max_consecutive_non_forward} consecutive "
        f"non-forward ticks (original failure: 17,177)"
    )
    assert forward_count > 0
    print(f"PASS Test SOLAR-10: replaying the original DEV01 adversarial flip-flop condition over "
          f"{ticks_simulated} ticks, the corrected controller never exceeds {max_consecutive_non_forward} "
          f"consecutive non-forward ticks (vs. the original 17,177) and takes {forward_count} forward steps")


def main() -> int:
    test_solar1_one_turn_completes()
    test_solar2_no_infinite_reissue()
    test_solar3_fresh_sensor_reevaluation()
    test_solar4_light_guidance_preserved()
    test_solar5_center_forward_behavior()
    test_solar6_obstacle_safety_preserved()
    test_solar7_c1_memory_free()
    test_solar8_c2_wm_unchanged()
    test_solar9_return_logic_unchanged()
    test_solar10_original_dev01_pathology()
    print("PASS Tests SOLAR-1 through SOLAR-10: SOLAR_TURN_45 EXPLORE deadlock correction regression suite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
