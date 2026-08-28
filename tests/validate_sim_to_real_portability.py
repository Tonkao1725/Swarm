"""Deterministic regression tests for sim-to-real software-architecture
portability (Tests PORT-1 through PORT-12). Common infrastructure -- C1 and
C2 alike. No IR-SIM environment is created (same env-free harness style as
tests/validate_c2_boot_home_confirmation.py).

Canonical Sim-to-Real definition under test (see
docs/SIM_TO_REAL_SOFTWARE_ARCHITECTURE.md): the same core controller CODE
(WM, Home confirmation, state machine, energy policy) must be reusable on
real hardware. Geometric scale equivalence between simulation and the real
world is explicitly NOT required.
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path
import sys
import textwrap

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "swarm_simulate"))

from motion_types import RobotPose
from swarm_baseline import BaselineSwarmRunner, ESP32NestBeaconModel, _SCOUT_START_STATES
from c2_working_memory import CycleWorkingMemory
from home_observation import HomeObservation, HomeConfirmationPolicy, RealHomeAdapterStub
from nest_beacon_hardware import NODEMCU_ESP32_WROOM32_PROFILE, SimulatedNestRSSIModel

sys.path.insert(0, str(ROOT / "tests"))
from validate_c2_boot_home_confirmation import make_runner  # noqa: E402


def _code_only(func) -> str:
    src = inspect.getsource(func)
    tree = ast.parse(textwrap.dedent(src))
    fn = tree.body[0]
    if (
        fn.body and isinstance(fn.body[0], ast.Expr)
        and isinstance(getattr(fn.body[0], "value", None), ast.Constant)
        and isinstance(fn.body[0].value.value, str)
    ):
        fn.body = fn.body[1:]
    return ast.unparse(fn)


def test_port1_no_scale_in_controller() -> None:
    src = (ROOT / "src" / "swarm_simulate" / "swarm_baseline.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    # Every module-level import must not pull in the scale-conversion name.
    module_names = {n.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names}
    imported_from = {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names
    }
    assert "sim_to_real_linear_scale" not in imported_from, (
        "swarm_baseline.py must not import the geometric scale-conversion function"
    )
    # No decision method may reference it either (belt and suspenders --
    # catches any local re-derivation, not just the top-level import).
    for method_name in ("_return_command", "_explore_command", "_environment_home_confirmed",
                        "_environment_nest_reached", "_command_for", "run"):
        method_src = inspect.getsource(getattr(BaselineSwarmRunner, method_name))
        assert "sim_to_real_linear_scale" not in method_src and "SIM_TO_REAL_LINEAR_SCALE" not in method_src, (
            f"{method_name} must not depend on geometric sim-to-real scale conversion"
        )
    wm_src = Path(ROOT / "src" / "swarm_simulate" / "c2_working_memory.py").read_text(encoding="utf-8")
    assert "scale" not in wm_src.lower(), "CycleWorkingMemory must have no scale dependency at all"
    runner = make_runner(scout_count=3)
    assert not hasattr(runner, "sim_to_real_linear_scale"), "the active runner must not carry a scale attribute"
    print("PASS Test PORT-1: no C1/C2/WM/Return/Home decision depends on geometric sim-to-real scale conversion")


def test_port2_wm_backend_independent() -> None:
    src = Path(ROOT / "src" / "swarm_simulate" / "c2_working_memory.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported_modules = {
        n.name for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names
    } | {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    forbidden_modules = {"irsim", "swarm_baseline", "nest_beacon_hardware", "energy_sensor", "irsim_range_sensor"}
    hit = imported_modules & forbidden_modules
    assert not hit, f"CycleWorkingMemory must not import {hit}"
    for forbidden_text in ("nest_x", "nest_y", "irsim", "esp32", "wifi", "rssi"):
        assert forbidden_text not in src.lower(), f"CycleWorkingMemory source must not mention {forbidden_text!r}"
    # The module's own docstring legitimately documents the ABSENCE of a
    # Resource dependency ("no ... Resource ... dependency") -- that is the
    # desired statement, not a violation; the import-set check above is
    # the actual dependency guard.
    print("PASS Test PORT-2: CycleWorkingMemory imports nothing from IR-SIM, Nest/Resource geometry, or the ESP32 API")


def test_port3_home_policy_backend_independent() -> None:
    src = Path(ROOT / "src" / "swarm_simulate" / "home_observation.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported_modules = {
        n.name for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names
    } | {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    allowed = {"dataclasses", "typing", "__future__"}
    assert imported_modules <= allowed, f"home_observation.py must only import stdlib, found: {imported_modules - allowed}"
    policy_src = inspect.getsource(HomeConfirmationPolicy)
    assert "pose" not in policy_src.lower() and "world" not in policy_src.lower() and "x_m" not in policy_src, (
        "HomeConfirmationPolicy must require no world pose"
    )
    # Behavioral: the policy operates purely on the abstract observation + threshold.
    policy = HomeConfirmationPolicy(threshold_dbm=-30.0)
    assert policy.evaluate(HomeObservation(nest_presence=True, rssi_dbm=-20.0)) is True
    assert policy.evaluate(HomeObservation(nest_presence=False, rssi_dbm=-20.0)) is False
    assert policy.evaluate(HomeObservation(nest_presence=True, rssi_dbm=-40.0)) is False
    assert policy.evaluate(HomeObservation(nest_presence=True, rssi_dbm=None)) is False
    print("PASS Test PORT-3: Home confirmation policy operates from an abstract observation + threshold only, "
          "with zero world-pose dependency")


def test_port4_sim_home_adapter() -> None:
    runner = make_runner(scout_count=3)
    nx, ny = runner._nest_beacon.nest_x_m, runner._nest_beacon.nest_y_m
    pose = RobotPose(nx, ny, 0.0)
    confirmed, rssi, nest_presence = runner._environment_home_confirmed(pose)
    assert nest_presence and confirmed
    # Confirm the sim adapter's source builds a HomeObservation and
    # delegates to the policy, rather than reimplementing the AND-logic.
    adapter_src = _code_only(BaselineSwarmRunner._environment_home_confirmed)
    assert "HomeObservation(" in adapter_src
    assert "self._home_policy.evaluate(" in adapter_src
    print("PASS Test PORT-4: the simulation adapter transforms environment Nest membership + simulated RSSI "
          "into a HomeObservation and delegates the decision to the portable policy")


def test_port5_real_home_interface() -> None:
    assert RealHomeAdapterStub.REAL_NEST_PRESENCE_SENSOR == "TBD / HARDWARE DESIGN PENDING"
    stub = RealHomeAdapterStub()
    try:
        stub.read()
        raise AssertionError("RealHomeAdapterStub.read() must not silently succeed -- no real sensor is decided")
    except NotImplementedError as exc:
        assert "HomeObservation" in str(exc)
    # No simulation dependency: the module defining this stub imports
    # nothing beyond stdlib (same module as PORT-3's check).
    src = Path(ROOT / "src" / "swarm_simulate" / "home_observation.py").read_text(encoding="utf-8")
    assert "irsim" not in src.lower() and "swarm_baseline" not in src.lower()
    print("PASS Test PORT-5: RealHomeAdapterStub defines a clear, simulation-independent real-backend "
          "contract (read() -> HomeObservation) without inventing real Home-presence hardware")


def test_port6_rssi_no_navigation() -> None:
    for method_name in ("_return_command", "_explore_command"):
        src = inspect.getsource(getattr(BaselineSwarmRunner, method_name))
        assert "_nest_beacon" not in src and "rssi_dbm" not in src
    print("PASS Test PORT-6: RSSI influences only Home confirmation/logging; navigation uses = 0")


def test_port7_nest_presence_no_navigation() -> None:
    for method_name in ("_return_command", "_explore_command"):
        src = inspect.getsource(getattr(BaselineSwarmRunner, method_name))
        for token in ("nest_presence", "home_region_radius_m", "_home_center", "NestRegion"):
            assert token not in src, f"{method_name} must not reference {token!r}"
    print("PASS Test PORT-7: nest_presence influences only Home confirmation/lifecycle; navigation uses = 0")


def test_port8_same_home_policy_sim_real() -> None:
    threshold = -30.0
    policy = HomeConfirmationPolicy(threshold_dbm=threshold)
    # "Simulation-style" observation (as the sim adapter would build it).
    sim_style = HomeObservation(nest_presence=True, rssi_dbm=-25.0)
    # "Real-style" observation (as a hypothetical real adapter would build
    # it, from entirely different sensors) -- same VALUES, different origin.
    real_style = HomeObservation(nest_presence=True, rssi_dbm=-25.0)
    assert policy.evaluate(sim_style) == policy.evaluate(real_style) is True
    sim_style_fail = HomeObservation(nest_presence=True, rssi_dbm=-40.0)
    real_style_fail = HomeObservation(nest_presence=True, rssi_dbm=-40.0)
    assert policy.evaluate(sim_style_fail) == policy.evaluate(real_style_fail) is False
    print("PASS Test PORT-8: identical-valued sim-style and real-style HomeObservations produce identical "
          "HOME_CONFIRMED decisions through the same policy code")


def test_port9_same_wm_input_semantics() -> None:
    # Synthetic executed odometry, no IR-SIM object anywhere in this test.
    wm = CycleWorkingMemory(enabled=True)
    wm.start_cycle(1)
    wm.update_executed_motion(moved_m=0.3, heading_delta_rad=0.0, cycle_id=1)
    wm.update_executed_motion(moved_m=0.3, heading_delta_rad=0.7853981633974483, cycle_id=1)
    assert wm.size >= 1
    assert wm.cycle_id == 1
    print("PASS Test PORT-9: CycleWorkingMemory consumes synthetic executed odometry "
          "(moved_m, heading_delta_rad, cycle_id) with no IR-SIM involvement")


def test_port10_nodemcu_profile_decoupled() -> None:
    for method_name in ("_return_command", "_explore_command"):
        src = inspect.getsource(getattr(BaselineSwarmRunner, method_name))
        for literal in ("WROOM", "NodeMCU", "hardware_profile", "tx_power"):
            assert literal not in src, f"{method_name} must not reference {literal!r}"
    runner = make_runner(scout_count=3)
    alt_profile = dataclasses.replace(NODEMCU_ESP32_WROOM32_PROFILE, tx_power_dbm_reference=15.0)
    alt_beacon = ESP32NestBeaconModel(
        nest_x_m=runner._nest_beacon.nest_x_m, nest_y_m=runner._nest_beacon.nest_y_m,
        propagation=SimulatedNestRSSIModel(profile=alt_profile),
    )
    runner._nest_beacon = alt_beacon
    runner.home_signal_threshold = alt_beacon.sample_at_distance(runner.home_region_radius_m)
    runner._home_policy = HomeConfirmationPolicy(threshold_dbm=runner.home_signal_threshold)
    for x, y, _h in _SCOUT_START_STATES[:3]:
        confirmed, _r, _p = runner._environment_home_confirmed(RobotPose(x, y, 0.0))
        assert confirmed
    print("PASS Test PORT-10: NodeMCU/ESP32-WROOM-32 hardware profile remains available for real-backend "
          "configuration; changing it requires no WM/controller/navigation code change")


def test_port11_physical_dimensions_not_causal() -> None:
    src = (ROOT / "src" / "swarm_simulate" / "swarm_baseline.py").read_text(encoding="utf-8")
    for token in ("REAL_ROBOT_RADIUS_M", "REAL_NEST_WIDTH_M", "REAL_NEST_HEIGHT_M"):
        assert token not in src, f"swarm_baseline.py must not reference {token!r} (PHYSICAL_IMPLEMENTATION_REFERENCE only)"
    r1 = make_runner(scout_count=3)
    r2 = make_runner(scout_count=3)
    assert r1.home_region_radius_m == r2.home_region_radius_m
    assert r1.home_signal_threshold == r2.home_signal_threshold
    print("PASS Test PORT-11: physical-dimension metadata (real robot diameter, real Nest size) is absent "
          "from swarm_baseline.py entirely -- it cannot alter active behavioral simulation")


def test_port12_current_c1_c2_behavior_preserved() -> None:
    # Structural check here; the full before/after trajectory comparison
    # (git-stash-based, live smoke run) is reported separately in
    # tests/SIM_TO_REAL_PORTABILITY_REPORT.md section R, since it requires
    # constructing a real IR-SIM environment (not this env-free harness).
    runner = make_runner(scout_count=3)
    for x, y, _h in _SCOUT_START_STATES[:3]:
        confirmed, _r, physical_ok = runner._environment_home_confirmed(RobotPose(x, y, 0.0))
        assert physical_ok and confirmed, "Boot/Home confirmation pass/fail boundary must be unchanged by this refactor"
    assert runner.home_region_radius_m == 1.05, runner.home_region_radius_m
    print("PASS Test PORT-12 (structural check): Home confirmation pass/fail boundary (home_region_radius_m=1.05 m) "
          "is unchanged; see tests/SIM_TO_REAL_PORTABILITY_REPORT.md for the live C1/C2 before/after trajectory diff")


def main() -> int:
    test_port1_no_scale_in_controller()
    test_port2_wm_backend_independent()
    test_port3_home_policy_backend_independent()
    test_port4_sim_home_adapter()
    test_port5_real_home_interface()
    test_port6_rssi_no_navigation()
    test_port7_nest_presence_no_navigation()
    test_port8_same_home_policy_sim_real()
    test_port9_same_wm_input_semantics()
    test_port10_nodemcu_profile_decoupled()
    test_port11_physical_dimensions_not_causal()
    test_port12_current_c1_c2_behavior_preserved()
    print("PASS Tests PORT-1 through PORT-12: sim-to-real software-architecture portability regression suite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
