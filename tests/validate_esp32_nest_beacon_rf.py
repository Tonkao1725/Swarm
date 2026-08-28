"""Deterministic regression tests for the NodeMCU ESP32 Nest Beacon
hardware profile and the simulated RSSI sensor model (Tests RF-1 through
RF-12). Common infrastructure -- C1 and C2 alike. No IR-SIM environment is
created (same env-free harness style as
tests/validate_c2_boot_home_confirmation.py).

**2026-08-27 reclassification** (SIM-TO-REAL ARCHITECTURE CORRECTION task):
the original RF-3 ("SIM_TO_REAL_DISTANCE") and RF-5 ("ANALYTICAL_PATH_LOSS")
tested the geometric sim-to-real distance conversion as an ACTIVE
behavioral requirement. Per the corrected canonical Sim-to-Real definition
(same controller CODE reusable on real hardware, NOT matched geometry --
see docs/SIM_TO_REAL_SOFTWARE_ARCHITECTURE.md), that conversion must NOT be
part of the active causal path. Both tests are reclassified below to match:
RF-3 now verifies the ACTIVE model (`SimulatedNestRSSIModel`) uses raw
simulation distance with no scale division, while the geometric-scale
conversion utilities (`DevelopmentFreeSpacePathLossModel`,
`sim_to_real_linear_scale`) are verified to exist and work correctly, but
strictly as OFFLINE/METADATA-only tools the runner never calls (also
covered by PORT-1/PORT-11 in tests/validate_sim_to_real_portability.py).
RF-5 now verifies the ACTIVE model's own FSPL formula directly, against an
independent reference computation, over simulation-scale distance.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "swarm_simulate"))

from motion_types import RobotPose
from swarm_baseline import BaselineSwarmRunner, ESP32NestBeaconModel, _ROBOT_RADIUS_M, _SCOUT_START_STATES
from nest_beacon_hardware import (
    NODEMCU_ESP32_WROOM32_PROFILE, SimulatedNestRSSIModel,
    DevelopmentFreeSpacePathLossModel, sim_to_real_linear_scale,
    wifi_channel_to_center_frequency_hz, SPEED_OF_LIGHT_MPS,
)

sys.path.insert(0, str(ROOT / "tests"))
from validate_c2_boot_home_confirmation import make_runner, _forced_strong_beacon  # noqa: E402


def test_rf1_target_hardware_profile() -> None:
    p = NODEMCU_ESP32_WROOM32_PROFILE
    assert "NodeMCU" in p.board_family, p.board_family
    assert "ESP32-WROOM-32" in p.radio_module, p.radio_module
    assert "ESP32-S3" not in p.radio_module and "ESP32S3" not in p.radio_module.replace("-", ""), (
        f"active profile must not identify an ESP32-S3 radio module: {p.radio_module}"
    )
    assert "S3" not in p.profile_id
    assert p.hardware_profile_status == "PROVISIONAL_UNTIL_BOARD_MARKING_VERIFIED", p.hardware_profile_status
    print("PASS Test RF-1: active Nest hardware profile identifies NodeMCU ESP32 / classic ESP32-WROOM-32, not ESP32-S3")


def test_rf2_source_provenance() -> None:
    json_path = ROOT / "config" / "nest_beacon_hardware_profile.json"
    md_path = ROOT / "docs" / "NEST_BEACON_HARDWARE_PROFILE.md"
    assert json_path.exists(), f"missing {json_path}"
    assert md_path.exists(), f"missing {md_path}"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["profile_id"] == "NODEMCU_ESP32_WROOM32"
    assert "sources" in data and len(data["sources"]) >= 1
    required_source_fields = {"parameter_name", "value", "unit", "source_document", "classification"}
    for src in data["sources"]:
        missing = required_source_fields - set(src.keys())
        assert not missing, f"source entry missing fields {missing}: {src}"
        assert src["classification"] in {
            "DATASHEET", "ESP_IDF", "DEVELOPMENT_ASSUMPTION", "PHYSICAL_MEASUREMENT_PENDING",
        }, src["classification"]
    datasheet_or_idf = [s for s in data["sources"] if s["classification"] in {"DATASHEET", "ESP_IDF"}]
    assert len(datasheet_or_idf) >= 4, "expected multiple datasheet/ESP-IDF-sourced constants on record"
    print(f"PASS Test RF-2: {len(data['sources'])} RF constants recorded with source/unit/classification "
          f"({len(datasheet_or_idf)} DATASHEET/ESP_IDF-classified)")


def test_rf3_sim_to_real_distance() -> None:
    """Reclassified (see module docstring): the ACTIVE model must use raw
    simulation distance, unconverted; the offline scale-conversion tools
    must remain available but separate, and must NOT be constructed by the
    active runner."""
    active_model = SimulatedNestRSSIModel(profile=NODEMCU_ESP32_WROOM32_PROFILE)
    # No scale-dividing step exists to bypass in the active model -- prove
    # this by confirming its dataclass fields contain no scale parameter.
    field_names = {f.name for f in dataclasses.fields(active_model)}
    assert "sim_to_real_linear_scale" not in field_names, (
        f"the ACTIVE simulated RSSI model must not carry a scale field, found: {field_names}"
    )
    # Directly feeding simulation distance produces the same FSPL-shaped
    # falloff a naive (unconverted) real-distance call would -- i.e. the
    # active model treats its input as its own self-contained distance unit.
    d1, d2 = 1.0, 2.0
    assert active_model.received_power_dbm(d1) > active_model.received_power_dbm(d2), (
        "active model must still be monotonically decreasing with its own (unconverted) distance input"
    )
    # The runner never constructs the offline scale-conversion classes.
    runner = make_runner(scout_count=3)
    assert not hasattr(runner, "sim_to_real_linear_scale"), (
        "the active runner must not carry a geometric sim-to-real scale attribute"
    )
    assert not hasattr(runner, "real_scaled_nest_region"), (
        "the active runner must not carry a real-scaled Nest region attribute"
    )
    assert isinstance(runner._nest_beacon.propagation, SimulatedNestRSSIModel), (
        "the active beacon must use SimulatedNestRSSIModel, not the offline scale-based model"
    )
    # The offline conversion utilities still exist and still work correctly
    # (available for optional future physical-fidelity analysis).
    scale = sim_to_real_linear_scale(_ROBOT_RADIUS_M)
    offline_model = DevelopmentFreeSpacePathLossModel(profile=NODEMCU_ESP32_WROOM32_PROFILE, sim_to_real_linear_scale=scale)
    assert offline_model.received_power_dbm_at_sim_distance(1.0) == offline_model.received_power_dbm_at_real_distance(1.0 / scale)
    print(f"PASS Test RF-3: the active RSSI model uses raw simulation distance (no scale coupling); "
          f"the offline scale-conversion tool (scale={scale}) still works but is not constructed by the runner")


def test_rf4_dbm_output() -> None:
    assert NODEMCU_ESP32_WROOM32_PROFILE.rssi_unit == "dBm"
    runner = make_runner(scout_count=3)
    pose = RobotPose(runner._nest_beacon.nest_x_m, runner._nest_beacon.nest_y_m, 0.0)
    value = runner._nest_beacon.sample(pose)
    assert isinstance(value, float)
    # A 0-1 unitless scalar would never plausibly exceed ~1.0; a dBm reading
    # near a 2 dBm TX-power beacon at zero distance should be close to (not
    # bounded by) that TX power, not clamped into [0,1].
    assert value > 1.0, f"expected a dBm-scale reading near TX power, got {value} (looks like the old 0-1 scalar)"
    src = (ROOT / "src" / "swarm_simulate" / "swarm_baseline.py").read_text(encoding="utf-8")
    assert "class IdealizedRSSILikeNestBeacon" not in src, "old unitless beacon class must not remain active"
    print(f"PASS Test RF-4: Beacon output is dBm-scale ({value:.2f} dBm at zero distance), "
          "no active Home logic uses the old 0-1 scalar")


def test_rf5_analytical_path_loss() -> None:
    """Reclassified (see module docstring): verifies the ACTIVE model's own
    FSPL formula, over simulation-scale distance directly -- no
    sim-to-real conversion involved."""
    model = SimulatedNestRSSIModel(profile=NODEMCU_ESP32_WROOM32_PROFILE)
    freq_hz = NODEMCU_ESP32_WROOM32_PROFILE.center_frequency_hz
    wavelength_m = SPEED_OF_LIGHT_MPS / freq_hz
    for d in (0.05, 0.2, 1.0, 3.0):
        # Independent reference computation (not calling the production
        # method), same FSPL formula from first principles, over raw
        # simulation distance.
        fspl_ref_db = 20.0 * math.log10(4.0 * math.pi * d / wavelength_m)
        pr_ref_dbm = NODEMCU_ESP32_WROOM32_PROFILE.tx_power_dbm_reference - fspl_ref_db
        pr_model_dbm = model.received_power_dbm(d)
        assert math.isclose(pr_ref_dbm, pr_model_dbm, abs_tol=1e-9), (
            f"d={d}: independent reference {pr_ref_dbm} != model {pr_model_dbm}"
        )
    # Monotonic: farther must never be stronger.
    ds = [0.05, 0.1, 0.5, 1.0, 3.0, 10.0]
    values = [model.received_power_dbm(d) for d in ds]
    assert all(values[i] > values[i + 1] for i in range(len(values) - 1)), values
    print("PASS Test RF-5: the active model's analytical free-space path loss matches an independently "
          "computed reference at several simulation-scale distances and is monotonically decreasing")


def test_rf6_home_threshold_not_rx_sensitivity() -> None:
    runner = make_runner(scout_count=3)
    assert runner.home_signal_threshold != runner.hardware_profile.rx_sensitivity_dbm_reference, (
        "the Home confirmation threshold must never be conflated with radio receiver sensitivity"
    )
    # Conceptual separation: RX sensitivity is a hardware detectability
    # floor (very low, e.g. -97 dBm); the Home threshold is a much
    # stricter, geometry-derived SIMULATION_DEVELOPMENT_THRESHOLD (not a
    # real hardware fact) that must sit well above it for the Home
    # decision to be meaningful.
    assert runner.home_signal_threshold > runner.hardware_profile.rx_sensitivity_dbm_reference + 20.0, (
        f"Home threshold ({runner.home_signal_threshold} dBm) should be well above the RX-sensitivity "
        f"detectability floor ({runner.hardware_profile.rx_sensitivity_dbm_reference} dBm), not merely equal to it"
    )
    print(f"PASS Test RF-6: Home threshold ({runner.home_signal_threshold:.2f} dBm) is conceptually and "
          f"numerically distinct from RX sensitivity ({runner.hardware_profile.rx_sensitivity_dbm_reference} dBm)")


def test_rf7_different_scout_origins() -> None:
    runner = make_runner(scout_count=3)
    for x, y, _h in _SCOUT_START_STATES[:3]:
        pose = RobotPose(x, y, 0.0)
        confirmed, rssi, physical_ok = runner._environment_home_confirmed(pose)
        assert confirmed, f"scout at ({x},{y}) must independently Home-confirm"
    from c2_working_memory import CycleWorkingMemory
    origins = []
    for x, y, _h in _SCOUT_START_STATES[:3]:
        wm = CycleWorkingMemory(enabled=True)
        wm.start_cycle(1)
        origins.append((wm.x_m, wm.y_m))
    assert all(o == (0.0, 0.0) for o in origins)
    print("PASS Test RF-7: multiple Scouts at different valid Nest positions each Home-confirm independently "
          "and each creates its own local (0,0) origin")


def test_rf8_outside_nest_strong_rssi() -> None:
    runner = make_runner(scout_count=3)
    outside_pose = RobotPose(runner._nest_beacon.nest_x_m + 5.0, runner._nest_beacon.nest_y_m, 0.0)
    forced = _forced_strong_beacon(runner._nest_beacon.nest_x_m, runner._nest_beacon.nest_y_m)
    assert forced.sample(outside_pose) >= runner.home_signal_threshold, "fixture must force a passing RSSI"
    runner._nest_beacon = forced
    confirmed, _rssi, physical_ok = runner._environment_home_confirmed(outside_pose)
    assert not physical_ok
    assert not confirmed, "outside-Nest pose with strong RSSI must never be HOME"
    assert not runner._environment_nest_reached(outside_pose), "and must never be NEST_REACHED either"
    print("PASS Test RF-8: a pose outside the Nest region with strong (forced) RSSI is NOT Home/NEST_REACHED")


def test_rf9_no_rssi_navigation() -> None:
    for method_name in ("_return_command", "_explore_command"):
        src = inspect.getsource(getattr(BaselineSwarmRunner, method_name))
        assert "_nest_beacon" not in src, f"{method_name} must never read the Nest beacon"
    # WM target/breadcrumb selection lives in c2_working_memory.py; confirm
    # it has no RF/beacon import or reference at all.
    import c2_working_memory
    wm_src = Path(c2_working_memory.__file__).read_text(encoding="utf-8")
    assert "nest_beacon" not in wm_src.lower() and "rssi" not in wm_src.lower(), (
        "CycleWorkingMemory must have no RSSI/beacon dependency whatsoever"
    )
    print("PASS Test RF-9: RSSI influences no linear/angular velocity, turn direction, WM target, "
          "breadcrumb consumption, or route selection")


def test_rf10_c1_c2_common_beacon() -> None:
    c1 = make_runner(scout_count=3, working_memory_enabled=False)
    c2 = make_runner(scout_count=3, working_memory_enabled=True)
    assert c1.hardware_profile == c2.hardware_profile
    assert c1.home_signal_threshold == c2.home_signal_threshold
    assert c1.home_region_radius_m == c2.home_region_radius_m
    assert (c1._nest_beacon.nest_x_m, c1._nest_beacon.nest_y_m) == (c2._nest_beacon.nest_x_m, c2._nest_beacon.nest_y_m)
    for x, y, _h in _SCOUT_START_STATES[:3]:
        pose = RobotPose(x, y, 0.0)
        assert c1._nest_beacon.sample(pose) == c2._nest_beacon.sample(pose)
    print("PASS Test RF-10: C1 and C2 share an identical hardware profile, Beacon RF model, Home threshold, and NestRegion")


def test_rf11_channel_frequency_mapping() -> None:
    p = NODEMCU_ESP32_WROOM32_PROFILE
    expected = wifi_channel_to_center_frequency_hz(p.wifi_channel)
    assert p.center_frequency_hz == expected
    assert p.wifi_band_low_hz <= p.center_frequency_hz <= p.wifi_band_high_hz, (
        f"channel {p.wifi_channel} center frequency {p.center_frequency_hz} Hz must fall inside the "
        f"declared band [{p.wifi_band_low_hz}, {p.wifi_band_high_hz}] Hz"
    )
    print(f"PASS Test RF-11: Wi-Fi channel {p.wifi_channel} maps to {p.center_frequency_hz/1e6:.0f} MHz, "
          "consistent with the declared 2.4 GHz band")


def test_rf12_hardware_profile_switchability() -> None:
    for method_name in ("_return_command", "_explore_command"):
        src = inspect.getsource(getattr(BaselineSwarmRunner, method_name))
        for literal in ("2412", "2437", "2484", "dBm", "WROOM", "NodeMCU", "tx_power", "wifi_channel"):
            assert literal not in src, f"{method_name} must contain no RF/hardware-profile literal ({literal!r})"
    # Behaviorally: swapping to a DIFFERENT hardware profile (different TX
    # power) changes only the RF numbers, with zero change required to any
    # navigation method -- construct a runner-equivalent Beacon with a
    # different profile and confirm Home confirmation still functions
    # end-to-end through the unmodified _environment_home_confirmed.
    from home_observation import HomeConfirmationPolicy
    runner = make_runner(scout_count=3)
    alt_profile = dataclasses.replace(NODEMCU_ESP32_WROOM32_PROFILE, tx_power_dbm_reference=20.0)
    alt_beacon = ESP32NestBeaconModel(
        nest_x_m=runner._nest_beacon.nest_x_m, nest_y_m=runner._nest_beacon.nest_y_m,
        propagation=SimulatedNestRSSIModel(profile=alt_profile),
    )
    runner._nest_beacon = alt_beacon
    runner.home_signal_threshold = alt_beacon.sample_at_distance(runner.home_region_radius_m)
    runner._home_policy = HomeConfirmationPolicy(threshold_dbm=runner.home_signal_threshold)
    for x, y, _h in _SCOUT_START_STATES[:3]:
        confirmed, _rssi, physical_ok = runner._environment_home_confirmed(RobotPose(x, y, 0.0))
        assert physical_ok and confirmed, "Home confirmation must keep working under a swapped hardware profile"
    print("PASS Test RF-12: RF/hardware-profile constants are confined to the hardware-profile/beacon layer -- "
          "navigation methods contain none, and swapping profiles requires no navigation code change")


def main() -> int:
    test_rf1_target_hardware_profile()
    test_rf2_source_provenance()
    test_rf3_sim_to_real_distance()
    test_rf4_dbm_output()
    test_rf5_analytical_path_loss()
    test_rf6_home_threshold_not_rx_sensitivity()
    test_rf7_different_scout_origins()
    test_rf8_outside_nest_strong_rssi()
    test_rf9_no_rssi_navigation()
    test_rf10_c1_c2_common_beacon()
    test_rf11_channel_frequency_mapping()
    test_rf12_hardware_profile_switchability()
    print("PASS Tests RF-1 through RF-12: NodeMCU ESP32 Nest Beacon hardware profile + simulated RSSI sensor model regression suite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
