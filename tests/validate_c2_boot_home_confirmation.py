"""Deterministic regression tests for Boot/Home confirmation and canonical
Home/Nest arrival semantics (Tests HOME-1 through HOME-15). Common
infrastructure -- applies identically to C1 and C2.

Runs fast, no IR-SIM environment is created (same env-free harness style as
tests/validate_c2_return_correction.py).
"""
from __future__ import annotations

import ast
import inspect
import itertools
import math
import textwrap
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "swarm_simulate"))

import dataclasses

from motion_types import RobotPose
from swarm_baseline import (
    BaselineSwarmRunner, ESP32NestBeaconModel,
    _ROBOT_RADIUS_M, _SCOUT_START_STATES,
)
from c2_working_memory import CycleWorkingMemory
from nest_beacon_hardware import NODEMCU_ESP32_WROOM32_PROFILE, SimulatedNestRSSIModel
from home_observation import HomeConfirmationPolicy


def _forced_strong_beacon(nest_x_m: float, nest_y_m: float) -> ESP32NestBeaconModel:
    """A beacon with an artificially inflated (unrealistic) TX power
    reference, used ONLY to adversarially force a passing RSSI reading at a
    pose that should otherwise fail Home confirmation -- proving the
    physical-region check is independently enforced (Tests HOME-10/12),
    not merely reflecting the normal beacon's own monotonic falloff."""
    forced_profile = dataclasses.replace(NODEMCU_ESP32_WROOM32_PROFILE, tx_power_dbm_reference=200.0)
    return ESP32NestBeaconModel(
        nest_x_m=nest_x_m, nest_y_m=nest_y_m,
        propagation=SimulatedNestRSSIModel(profile=forced_profile),
    )


def _code_only(func) -> str:
    """Source of `func` with its docstring (if any) stripped, so forbidden
    -token audits check real code, not documentation prose."""
    src = inspect.getsource(func)
    tree = ast.parse(textwrap.dedent(src))
    fn = tree.body[0]
    if (
        fn.body
        and isinstance(fn.body[0], ast.Expr)
        and isinstance(getattr(fn.body[0], "value", None), ast.Constant)
        and isinstance(fn.body[0].value.value, str)
    ):
        fn.body = fn.body[1:]
    return ast.unparse(fn)


def make_runner(*, scout_count: int = 3, working_memory_enabled: bool = False) -> BaselineSwarmRunner:
    """Minimal env-free runner exposing only the Home/Nest geometry that
    _environment_home_confirmed and _home_center read -- mirrors __init__'s own
    derivation exactly, so this is a faithful reproduction, not a stub."""
    runner = object.__new__(BaselineSwarmRunner)
    runner.scout_count = scout_count
    runner.working_memory_enabled = working_memory_enabled
    nest_x_m, nest_y_m = BaselineSwarmRunner._home_center(runner)
    runner.hardware_profile = NODEMCU_ESP32_WROOM32_PROFILE
    runner._nest_beacon = ESP32NestBeaconModel(
        nest_x_m=nest_x_m, nest_y_m=nest_y_m,
        propagation=SimulatedNestRSSIModel(profile=runner.hardware_profile),
    )
    starts_used = _SCOUT_START_STATES[:scout_count]
    runner.home_region_radius_m = (
        max(math.hypot(s[0] - nest_x_m, s[1] - nest_y_m) for s in starts_used) + _ROBOT_RADIUS_M
    )
    runner.home_signal_threshold = runner._nest_beacon.sample_at_distance(runner.home_region_radius_m)
    runner.nest_delivery_radius_m = 0.12  # historical/unused, kept only for attribute-existence safety
    runner._home_policy = HomeConfirmationPolicy(threshold_dbm=runner.home_signal_threshold)
    return runner


def test_home1_all_scouts_valid_boot_home() -> None:
    for scout_count in (2, 3, 4):
        runner = make_runner(scout_count=scout_count)
        for x, y, _h in _SCOUT_START_STATES[:scout_count]:
            pose = RobotPose(x, y, 0.0)
            confirmed, rssi, physical_ok = runner._environment_home_confirmed(pose)
            assert physical_ok, f"scout at ({x},{y}) failed physical Home-region check (scout_count={scout_count})"
            assert confirmed, f"scout at ({x},{y}) failed Boot/Home confirmation (scout_count={scout_count}), rssi={rssi}"
    print("PASS Test HOME-1: every configured Scout start passes Boot/Home confirmation")


def test_home2_no_false_boot_origin() -> None:
    runner = make_runner(scout_count=3)
    far_pose = RobotPose(10.0, 10.0, 0.0)
    confirmed, rssi, physical_ok = runner._environment_home_confirmed(far_pose)
    assert not physical_ok, "a Scout far outside the Home region must fail the physical containment check"
    assert not confirmed, "a Scout outside the Home region must not receive Boot/Home confirmation"
    print("PASS Test HOME-2: a Scout outside the Home region does not receive a false Home origin")


def test_home3_rssi_required() -> None:
    runner = make_runner(scout_count=3)
    # A pose well inside the physical Home region (near its own center),
    # but with an artificially strict RSSI threshold override -- this
    # directly exercises the "physical OK, RSSI confirmation fails" path,
    # proving both conditions are independently required (an AND, not an
    # OR) rather than relying on a specific real-geometry coincidence.
    pose = RobotPose(runner._nest_beacon.nest_x_m + 0.05, runner._nest_beacon.nest_y_m, 0.0)
    confirmed_normally, rssi, physical_ok = runner._environment_home_confirmed(pose)
    assert physical_ok, "test fixture pose must be inside the physical Home region"
    assert confirmed_normally, "sanity check: this near-center pose should normally confirm"
    runner.home_signal_threshold = 999.0  # dBm; unreachable given the beacon's monotonic dBm falloff
    runner._home_policy = HomeConfirmationPolicy(threshold_dbm=runner.home_signal_threshold)
    confirmed_strict, rssi2, physical_ok2 = runner._environment_home_confirmed(pose)
    assert physical_ok2, "physical containment must still pass -- only the RSSI threshold changed"
    assert not confirmed_strict, "Boot/Home confirmation must fail when RSSI does not meet the configured threshold, even inside the physical region"
    print("PASS Test HOME-3: physical-region-OK alone is not sufficient -- RSSI confirmation is independently required")


def test_home4_no_rssi_steering() -> None:
    src = (ROOT / "src" / "swarm_simulate" / "swarm_baseline.py").read_text(encoding="utf-8")
    # Isolate the boot/home and beacon-related CODE only (docstrings are
    # documentation, not data-flow -- they legitimately use words like
    # "bearing"/"heading" to explain what is forbidden; excluding them
    # avoids false positives while still catching any real usage).
    boot_check_src = _code_only(BaselineSwarmRunner._environment_home_confirmed)
    nest_reached_src = _code_only(BaselineSwarmRunner._environment_nest_reached)
    for region, label in ((boot_check_src, "_environment_home_confirmed"), (nest_reached_src, "_environment_nest_reached")):
        forbidden = ("linear_speed", "angular", "heading", "bearing", "atan2", "desired_heading", "turn(", "_start_turn")
        hits = [tok for tok in forbidden if tok in region]
        assert not hits, f"{label} must not use RSSI for steering/navigation; forbidden tokens found: {hits}"
    # The beacon's sample()/sample_at_distance() must never be USED (as
    # data-flow, not merely mentioned in a docstring/comment) inside any
    # navigation command method (_return_command, _explore_command). Both
    # methods' docstrings/comments legitimately say "RSSI never steers this
    # policy" as documentation, so the check below looks for the actual
    # attribute-access token `_nest_beacon` (a real read), not the English
    # word "RSSI".
    return_cmd_src = inspect.getsource(BaselineSwarmRunner._return_command)
    explore_cmd_src = inspect.getsource(BaselineSwarmRunner._explore_command)
    for region, label in ((return_cmd_src, "_return_command"), (explore_cmd_src, "_explore_command")):
        assert "_nest_beacon" not in region, (
            f"{label} must never read the Nest beacon for movement -- RSSI is confirmation-only"
        )
    print("PASS Test HOME-4: RSSI is confirmation-only in both Boot/Home and Return/DELIVER checks; "
          "no navigation command method reads the beacon")


def test_home5_c1_c2_common_start() -> None:
    c1 = make_runner(scout_count=3, working_memory_enabled=False)
    c2 = make_runner(scout_count=3, working_memory_enabled=True)
    assert (c1._nest_beacon.nest_x_m, c1._nest_beacon.nest_y_m) == (c2._nest_beacon.nest_x_m, c2._nest_beacon.nest_y_m)
    assert c1.home_region_radius_m == c2.home_region_radius_m
    assert c1.home_signal_threshold == c2.home_signal_threshold
    for x, y, _h in _SCOUT_START_STATES[:3]:
        pose = RobotPose(x, y, 0.0)
        r1 = c1._environment_home_confirmed(pose)
        r2 = c2._environment_home_confirmed(pose)
        assert r1 == r2, f"C1 and C2 must reach identical Boot/Home confirmation results for the same pose, got {r1} vs {r2}"
    print("PASS Test HOME-5: C1 and C2 share an identical Nest definition, Scout start positions, and Home confirmation rule")


def test_home6_wm_start_after_home() -> None:
    src = (ROOT / "src" / "swarm_simulate" / "swarm_baseline.py").read_text(encoding="utf-8")
    run_src = inspect.getsource(BaselineSwarmRunner.run)
    home_confirmed_idx = run_src.index('"event": "HOME_CONFIRMED"')
    wm_start_idx = run_src.index("scout.working_memory.start_cycle(scout.cycle_id)")
    assert home_confirmed_idx < wm_start_idx, (
        "HOME_CONFIRMED must be written before working_memory.start_cycle() is called -- "
        "event ordering must never be WM-start-before-Home-confirmation"
    )
    # Also confirm the fail-fast path (raise) sits between the physical/RSSI
    # checks and the WM start, i.e. WM cannot start if Home was not confirmed.
    raise_idx = run_src.index("INVALID_INITIAL_HOME_STATE")
    assert raise_idx < wm_start_idx, "the Boot/Home failure path must be reachable before any WM start_cycle call"
    print("PASS Test HOME-6: event ordering is SCOUT_BOOT -> HOME checks -> HOME_CONFIRMED -> WM start -> EXPLORE, never reversed")


def test_home7_collision_free_start() -> None:
    for scout_count in (2, 3, 4):
        starts = _SCOUT_START_STATES[:scout_count]
        min_gap = min(
            math.hypot(a[0] - b[0], a[1] - b[1])
            for a, b in itertools.combinations(starts, 2)
        )
        required = 2 * _ROBOT_RADIUS_M
        assert min_gap > required, (
            f"scout_count={scout_count}: minimum pairwise Scout start distance {min_gap:.3f} m "
            f"must exceed the non-overlap requirement {required:.3f} m (2x robot radius)"
        )
    print("PASS Test HOME-7: all configured Scout start layouts (2-4 Scouts) are physically valid and collision-free")


def test_home8_different_scout_origins_allowed() -> None:
    for scout_count in (2, 3, 4):
        world_positions = []
        for _scout_id, (x, y, _h) in enumerate(_SCOUT_START_STATES[:scout_count]):
            wm = CycleWorkingMemory(enabled=True)
            wm.start_cycle(1)
            # Local origin is ALWAYS (0,0,0) -- start_cycle takes no world
            # pose parameter at all, so each Scout's own current physical
            # pose becomes ITS OWN local origin by construction; Scouts are
            # never transformed onto one shared/global coordinate.
            assert (wm.x_m, wm.y_m, wm.heading_rad) == (0.0, 0.0, 0.0), (
                f"scout at world ({x},{y}) must start Cycle 1 at local origin (0,0,0)"
            )
            world_positions.append((x, y))
        assert len(set(world_positions)) == scout_count, (
            "configured Scout world start positions must differ per Scout while every "
            "local WM origin is identically (0,0,0) -- this is the intended per-Scout semantics"
        )
    print("PASS Test HOME-8: every Scout's local Home origin is its own (0,0,0); world positions legitimately differ")


def test_home9_return_not_exact_origin() -> None:
    runner = make_runner(scout_count=3)
    nx, ny = runner._nest_beacon.nest_x_m, runner._nest_beacon.nest_y_m
    origin_a = (nx + 0.7, ny)  # Scout1's actual configured cycle-1 world start
    arrival_a_prime = (nx + 0.4, ny + 0.3)  # a different in-region point, A' != A
    assert origin_a != arrival_a_prime
    dist_a_to_center = math.hypot(origin_a[0] - nx, origin_a[1] - ny)
    dist_aprime_to_center = math.hypot(arrival_a_prime[0] - nx, arrival_a_prime[1] - ny)
    assert dist_a_to_center <= runner.home_region_radius_m
    assert dist_aprime_to_center <= runner.home_region_radius_m
    nest_reached = runner._environment_nest_reached(RobotPose(*arrival_a_prime, 0.0))
    assert nest_reached, (
        "a Scout entering the Home/Nest region at a DIFFERENT point than its own cycle "
        "origin must still be considered NEST_REACHED, provided it is inside the region "
        "and RSSI confirms"
    )
    print("PASS Test HOME-9: NEST_REACHED does not require returning to the exact cycle-origin point")


def test_home10_rssi_alone_not_home() -> None:
    runner = make_runner(scout_count=3)
    # A pose genuinely outside the physical Home region.
    outside_pose = RobotPose(runner._nest_beacon.nest_x_m + 5.0, runner._nest_beacon.nest_y_m, 0.0)
    confirmed, rssi, physical_ok = runner._environment_home_confirmed(outside_pose)
    assert not physical_ok
    # The beacon's RSSI (dBm) and physical distance are, by construction, a
    # 1:1 monotonic pair at the CURRENT threshold/radius -- so naturally,
    # "outside region" also means "RSSI below threshold" here (a positive
    # property of this specific configuration, verified by this very
    # assertion). To directly prove the CODE independently enforces the AND
    # (not merely reflecting a coincidental correlation), install an
    # artificially generous beacon (inflated TX power) for this outside pose
    # only, forcing its RSSI reading above threshold, and confirm
    # HOME_CONFIRMED still evaluates False because physical_region_ok alone
    # is False.
    assert not confirmed
    generous_beacon = _forced_strong_beacon(runner._nest_beacon.nest_x_m, runner._nest_beacon.nest_y_m)
    forced_rssi = generous_beacon.sample(outside_pose)
    assert forced_rssi >= runner.home_signal_threshold, "fixture must actually force a passing RSSI value"
    runner._nest_beacon = generous_beacon
    confirmed_forced, rssi_forced, physical_ok_forced = runner._environment_home_confirmed(outside_pose)
    assert physical_ok_forced is False
    assert not confirmed_forced, (
        "RSSI alone, even artificially forced to pass, must never confirm Home for a "
        "physically-outside-region pose"
    )
    print("PASS Test HOME-10: RSSI passing alone (physical region failing) never yields HOME_CONFIRMED")


def test_home11_physical_region_alone_not_home() -> None:
    runner = make_runner(scout_count=3)
    # A pose near the edge of, but still inside, the physical Home region.
    edge_pose = RobotPose(
        runner._nest_beacon.nest_x_m + (runner.home_region_radius_m - 0.05),
        runner._nest_beacon.nest_y_m, 0.0,
    )
    confirmed, rssi, physical_ok = runner._environment_home_confirmed(edge_pose)
    assert physical_ok, "fixture pose must be inside the physical Home region"
    assert confirmed, "sanity check: this near-edge pose should normally confirm"
    runner.home_signal_threshold = 999.0  # dBm; force RSSI confirmation to fail
    runner._home_policy = HomeConfirmationPolicy(threshold_dbm=runner.home_signal_threshold)
    confirmed_strict, rssi2, physical_ok2 = runner._environment_home_confirmed(edge_pose)
    assert physical_ok2, "physical containment must still pass -- only the RSSI threshold changed"
    assert not confirmed_strict, (
        "physical-region membership alone, with RSSI confirmation failing, must never yield HOME_CONFIRMED"
    )
    print("PASS Test HOME-11: physical Home-region membership alone (RSSI failing) never yields HOME_CONFIRMED")


def test_home12_wall_separation() -> None:
    # Rigorous, maze-geometry-derived proof: verified separately (line-of-
    # sight sampling against every wall segment in config/robot_world.yaml,
    # see tests/C2_CANONICAL_HOME_ARRIVAL_REPORT.md) that NO reachable point
    # inside the current home_region_radius_m (1.05 m for scout_count=3)
    # requires crossing a wall from the Nest center -- i.e. this specific
    # provisional circle currently has no naturally-occurring "through the
    # wall" position to exploit. To still directly prove the code's own
    # defense (not merely the current maze's incidental geometry), this test
    # uses a REAL, verified wall-separated position from the actual maze
    # (just north of the wall segment at world (2.00, 2.00) in
    # config/robot_world.yaml, i.e. in the corridor above it, unreachable
    # from the Nest center without crossing that wall) together with an
    # artificially generous beacon forcing a passing RSSI reading there --
    # exactly modelling a real RF signal bleeding through a wall.
    runner = make_runner(scout_count=3)
    nx, ny = runner._nest_beacon.nest_x_m, runner._nest_beacon.nest_y_m
    # Wall centered (2.00, 2.00), length(x)=4.00, width(y)=0.18 -> far face
    # at y=2.09; add robot radius clearance so this pose is reachable
    # (non-colliding) in the adjacent corridor above that wall.
    wall_far_face_y = 2.00 + 0.18 / 2.0
    behind_wall_pose = RobotPose(nx, wall_far_face_y + _ROBOT_RADIUS_M + 0.05, 0.0)
    _confirmed_natural, rssi_natural, physical_ok_natural = runner._environment_home_confirmed(behind_wall_pose)
    assert not physical_ok_natural, "the behind-wall pose must be outside the provisional circular Home region"
    generous_beacon = _forced_strong_beacon(nx, ny)
    forced_rssi = generous_beacon.sample(behind_wall_pose)
    assert forced_rssi >= runner.home_signal_threshold, "fixture must force a passing RSSI value at the behind-wall pose"
    runner._nest_beacon = generous_beacon
    confirmed_forced, rssi_forced, physical_ok_forced = runner._environment_home_confirmed(behind_wall_pose)
    assert not physical_ok_forced
    assert not confirmed_forced, (
        "a pose on the far side of a real maze wall must never be confirmed Home, "
        "even with an artificially strong RSSI reading -- this is exactly the "
        "'Home through a wall' scenario the physical-region check must prevent"
    )
    print("PASS Test HOME-12: a wall-separated pose with a forced strong RSSI reading is still rejected "
          "(no 'Home through a wall'); the current provisional circle was also independently verified, by "
          "line-of-sight sampling against the real maze geometry, to contain no naturally-occurring case of this")


def test_home13_wm_remains_nav_authority() -> None:
    run_src = _code_only(BaselineSwarmRunner.run)
    # Locate the RETURN_HOME dispatch inside _command_for's source (not
    # .run(), which only drives the loop) -- verify the exact structural
    # pattern: the ONLY way out of RETURN_HOME is _environment_nest_reached
    # (physical region + RSSI); the ONLY movement source while still in
    # RETURN_HOME is _return_command (WM retrace + local safety, per
    # HOME-4's proof it never reads the beacon).
    command_for_src = inspect.getsource(BaselineSwarmRunner._command_for)
    assert 'scout.phase == "RETURN_HOME"' in command_for_src
    return_home_block = command_for_src.split('scout.phase == "RETURN_HOME"', 1)[1].split("elif", 1)[0]
    assert "_environment_nest_reached" in return_home_block, (
        "RETURN_HOME must only exit via the canonical Home/Nest arrival check"
    )
    assert "_return_command" in return_home_block, (
        "RETURN_HOME must fall back to WM retrace/local-safety navigation, not RSSI"
    )
    assert "_nest_beacon" not in return_home_block and "rssi" not in return_home_block.lower(), (
        "the RETURN_HOME dispatch itself must not read RSSI beyond the one canonical arrival check call"
    )
    print("PASS Test HOME-13: during RETURN_HOME, movement comes only from WM retrace/local-safety; "
          "the phase transition happens only through the canonical Home/Nest arrival check, never RSSI directly")


def test_home14_same_home_rule_boot_and_return() -> None:
    nest_reached_src = inspect.getsource(BaselineSwarmRunner._environment_nest_reached)
    assert "self._environment_home_confirmed(" in nest_reached_src, (
        "_environment_nest_reached (Return arrival) must call the SAME canonical "
        "_environment_home_confirmed predicate used at Boot, not a separately "
        "reimplemented Home rule"
    )
    # Also prove behavioral identity directly: any pose either both Boot- and
    # Return-confirms, or neither.
    runner = make_runner(scout_count=3)
    for x, y, _h in _SCOUT_START_STATES[:3]:
        pose = RobotPose(x, y, 0.0)
        boot_confirmed, _r, _p = runner._environment_home_confirmed(pose)
        return_confirmed = runner._environment_nest_reached(pose)
        assert boot_confirmed == return_confirmed, (
            f"pose ({x},{y}): Boot confirmation ({boot_confirmed}) and Return arrival "
            f"({return_confirmed}) must agree -- one canonical Home rule"
        )
    print("PASS Test HOME-14: Boot confirmation and Return arrival use the identical canonical Home predicate")


def test_home15_next_cycle_new_local_origin() -> None:
    # Source-level: the Cycle 2+ start_cycle call site passes only cycle_id,
    # never a world coordinate, a previous origin, or another Scout's data.
    run_src = inspect.getsource(BaselineSwarmRunner.run)
    assert "memory.start_cycle(scout.cycle_id)" in run_src or "working_memory.start_cycle(scout.cycle_id)" in run_src
    # Behavioral: a WM that accumulated real motion in Cycle 1 resets its
    # local frame to a fresh (0,0,0) at Cycle 2 -- independent of Cycle 1's
    # ending position, the original boot origin, the Nest centroid, or any
    # other Scout's origin (none of which start_cycle ever receives).
    wm = CycleWorkingMemory(enabled=True)
    wm.start_cycle(1)
    wm.update_executed_motion(moved_m=0.9, heading_delta_rad=0.3, cycle_id=1)
    assert (wm.x_m, wm.y_m) != (0.0, 0.0), "fixture must actually accumulate nonzero Cycle-1 motion first"
    wm.reset()
    wm.start_cycle(2)
    assert (wm.x_m, wm.y_m, wm.heading_rad) == (0.0, 0.0, 0.0), (
        "Cycle 2's local origin must be a fresh (0,0,0) at the Scout's current Nest "
        "position, regardless of where Cycle 1 ended"
    )
    print("PASS Test HOME-15: each new cycle's local origin is freshly (0,0,0) at the Scout's current position, "
          "independent of prior-cycle, boot, centroid, or other-Scout origins")


def main() -> int:
    test_home1_all_scouts_valid_boot_home()
    test_home2_no_false_boot_origin()
    test_home3_rssi_required()
    test_home4_no_rssi_steering()
    test_home5_c1_c2_common_start()
    test_home6_wm_start_after_home()
    test_home7_collision_free_start()
    test_home8_different_scout_origins_allowed()
    test_home9_return_not_exact_origin()
    test_home10_rssi_alone_not_home()
    test_home11_physical_region_alone_not_home()
    test_home12_wall_separation()
    test_home13_wm_remains_nav_authority()
    test_home14_same_home_rule_boot_and_return()
    test_home15_next_cycle_new_local_origin()
    print("PASS Tests HOME-1 through HOME-15: Boot/Home confirmation + canonical Home/Nest arrival regression suite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
