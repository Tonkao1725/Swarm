"""NodeMCU ESP32 Nest Beacon hardware reference + simulated RSSI sensor model.

**2026-08-27 architecture correction**: Sim-to-Real means the same core
controller/decision CODE is reusable on real hardware -- it does NOT mean
simulation geometry must be numerically scaled to match real-world
dimensions. See docs/SIM_TO_REAL_SOFTWARE_ARCHITECTURE.md. Two previously
conflated things are now explicitly separated in this module:

  HARDWARE PROFILE (`NestBeaconHardwareProfile`, `NODEMCU_ESP32_WROOM32_PROFILE`)
        -- real hardware reference facts (datasheet + ESP-IDF API), useful
           for the eventual real-robot implementation. Kept, unchanged in
           spirit, still provenance-tagged.

  ACTIVE SIMULATION GEOMETRY MODEL (`SimulatedNestRSSIModel`)
        -- what actually drives the behavioral simulation's RSSI. Operates
           directly on simulation-scale distance, with NO geometric
           sim-to-real scale conversion in its causal path. This is a
           SIMULATED RSSI SENSOR MODEL with dBm-compatible output
           semantics -- it exercises the Home-signal-presence /
           threshold-confirmation / no-RSSI-navigation architecture. It is
           explicitly NOT a claim that simulation RSSI predicts the real
           NodeMCU's RSSI at the same physical distance.

  `sim_to_real_linear_scale()`, `DevelopmentFreeSpacePathLossModel`,
  `RectangularNestRegion.from_real_nest_spec` (real-equivalent distance
  conversion, real-scaled Nest rectangle) remain available for OPTIONAL
  OFFLINE physical-fidelity analysis / future calibration tooling only.
  `BaselineSwarmRunner` does NOT construct or call them as part of its
  active behavioral decision path (Test PORT-1/PORT-11).

  `HomeConfirmationPolicy` lives in `home_observation.py` (portable,
  backend-independent) -- this module never makes a Home/no-Home decision
  itself; it only produces an RSSI scalar and (via `swarm_baseline.py`'s
  sim adapter) Home-presence ground truth.

Every numeric RF constant below is provenance-tagged. See
docs/NEST_BEACON_HARDWARE_PROFILE.md and
docs/ESP32_WROOM32_RSSI_SIM_TO_REAL_MODEL.md for the full source citations
(document, version, section/table, URL) behind each value, and
config/nest_beacon_hardware_profile.json for the machine-readable record.

REAL ROBOT: the Nest hardware is a NodeMCU ESP32-class development board.
NodeMCU-32S boards (and "NodeMCU ESP32" generically) commonly carry the
classic ESP32-WROOM-32 module; the exact module marking on the specific
purchased board has NOT been physically verified as of this writing.
`HARDWARE_PROFILE_STATUS = PROVISIONAL_UNTIL_BOARD_MARKING_VERIFIED`
reflects this.

SIMULATION: `SimulatedNestRSSIModel` is not a validated indoor/maze
propagation model and is not geometrically tied to real-world distance. It
is a DEVELOPMENT/TEST SENSOR MODEL, deterministic, monotonically
decreasing with simulation distance, dBm-compatible in units only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Physical constants (not hardware-specific; standard values).
# ---------------------------------------------------------------------------
SPEED_OF_LIGHT_MPS = 299_792_458.0

# ---------------------------------------------------------------------------
# HardwareProfile: datasheet + ESP-IDF facts only. No propagation math here.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NestBeaconHardwareProfile:
    """One named hardware profile. Every field's provenance is recorded in
    docs/NEST_BEACON_HARDWARE_PROFILE.md / config/nest_beacon_hardware_profile.json
    -- this class only carries the values, not their justification."""

    profile_id: str
    board_family: str
    radio_module: str
    hardware_profile_status: str
    wifi_band_low_hz: float
    wifi_band_high_hz: float
    wifi_channel: int
    tx_power_esp_idf_units: int  # esp_wifi_set_max_tx_power() raw units (0.25 dBm/unit)
    tx_power_dbm_reference: float
    tx_power_datasheet_max_dbm: float
    rx_sensitivity_dbm_reference: float
    rssi_unit: str = "dBm"
    tx_antenna_gain_dbi: float = 0.0
    rx_antenna_gain_dbi: float = 0.0
    system_loss_db: float = 0.0

    @property
    def center_frequency_hz(self) -> float:
        return wifi_channel_to_center_frequency_hz(self.wifi_channel)


    # NOTE on a removed field, `tx_power_datasheet_min_dbm`: the ESP32-WROOM-32E
    # datasheet's Table 20 (TX Power) lists typical output power PER
    # modulation/data-rate row (802.11b at several rates, 802.11g at
    # several rates, 802.11n HT20/HT40 at several MCS indices), not a
    # single scalar "TX min." An earlier version of this profile extracted
    # a single "-12.0 dBm (802.11n HT40 MCS7)" figure and compared it
    # against a classic-WROOM-32-datasheet "+13.0 dBm" figure as if they
    # were the same universal per-module minimum; on review this risks
    # conflating different table rows/extraction passes rather than a
    # verified, reconciled fact, so the field was removed rather than kept
    # with uncertain provenance. `tx_power_datasheet_max_dbm` (19.5 dBm) is
    # kept -- both datasheets agree on it. The ACTIVE `tx_power_dbm_reference`
    # (2.0 dBm) comes from the separately-verified ESP-IDF
    # `esp_wifi_set_max_tx_power()` quantization table, not from either
    # datasheet's typical-output-power table -- see
    # docs/NEST_BEACON_HARDWARE_PROFILE.md "TX power selection."


def wifi_channel_to_center_frequency_hz(channel: int) -> float:
    """IEEE 802.11 standard 2.4 GHz channel plan (channels 1-13):
    center frequency (MHz) = 2407 + 5 * channel. This is a general 802.11
    standard mapping, not an Espressif-specific datasheet value; channel 14
    (Japan-only, 2484 MHz) is not covered by this linear formula."""
    if not (1 <= channel <= 13):
        raise ValueError("channel must be 1-13 for the standard linear 2.4 GHz mapping")
    return (2407.0 + 5.0 * channel) * 1e6


# TX power quantization table from the official ESP-IDF Wi-Fi API reference
# for esp_wifi_set_max_tx_power() (classic ESP32): unit is 0.25 dBm; raw
# range [8, 84]. Selected {raw_units: actual_dbm} pairs, source-cited in
# docs/NEST_BEACON_HARDWARE_PROFILE.md.
ESP_IDF_TX_POWER_TABLE_DBM: dict[int, float] = {
    8: 2.0, 20: 5.0, 28: 7.0, 34: 8.0, 44: 11.0, 52: 13.0,
    56: 14.0, 60: 15.0, 66: 16.0, 72: 18.0, 80: 20.0,
}

# Development target hardware profile. PROVISIONAL until the actual
# purchased Nest board's module marking is physically read and confirmed.
NODEMCU_ESP32_WROOM32_PROFILE = NestBeaconHardwareProfile(
    profile_id="NODEMCU_ESP32_WROOM32",
    board_family="NodeMCU ESP32",
    radio_module="ESP32-WROOM-32 (classic; NodeMCU-32S boards commonly carry this module)",
    hardware_profile_status="PROVISIONAL_UNTIL_BOARD_MARKING_VERIFIED",
    wifi_band_low_hz=2412e6,
    wifi_band_high_hz=2484e6,
    wifi_channel=6,
    tx_power_esp_idf_units=8,
    tx_power_dbm_reference=ESP_IDF_TX_POWER_TABLE_DBM[8],  # 2.0 dBm
    tx_power_datasheet_max_dbm=19.5,
    rx_sensitivity_dbm_reference=-97.0,
    tx_antenna_gain_dbi=0.0,
    rx_antenna_gain_dbi=0.0,
    system_loss_db=0.0,
)


# ---------------------------------------------------------------------------
# ACTIVE simulation RSSI sensor model. Used by BaselineSwarmRunner. Operates
# directly on simulation-scale distance -- NO geometric sim-to-real scale
# conversion anywhere in this class (Test PORT-1/PORT-11). This is what
# actually drives C1/C2 behavior; the OFFLINE-ONLY classes further below
# are not part of this causal path.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimulatedNestRSSIModel:
    """SIMULATED RSSI SENSOR MODEL -- dBm-compatible output semantics,
    deterministic, monotonically decreasing with simulation-scale distance.

    This is explicitly NOT a claim that the output predicts the real
    NodeMCU Beacon's RSSI at the same physical distance -- simulation and
    real-world geometry are not required to match (see
    docs/SIM_TO_REAL_SOFTWARE_ARCHITECTURE.md). Its purpose is to exercise
    Home-signal presence, threshold confirmation, and the
    no-RSSI-navigation architecture in simulation, not to recreate final
    physical RF propagation.

    Shape follows free-space path loss for realism (a physically-motivated
    monotonic falloff, reusing the hardware profile's TX-power/frequency
    reference values), but the distance parameter is the simulation's OWN
    distance unit -- this class never divides by a sim-to-real scale.

    FSPL(dB) = 20*log10(4*pi*d_sim / lambda), lambda = c / f
    Pr(dBm)  = Pt(dBm) + Gt(dBi) + Gr(dBi) - FSPL(dB) - Lsystem(dB)
    """

    profile: NestBeaconHardwareProfile
    minimum_distance_m: float = 0.01  # avoids log(0) at zero simulation distance

    def _wavelength_m(self) -> float:
        return SPEED_OF_LIGHT_MPS / self.profile.center_frequency_hz

    def free_space_path_loss_db(self, distance_sim_m: float) -> float:
        d = max(distance_sim_m, self.minimum_distance_m)
        return 20.0 * math.log10(4.0 * math.pi * d / self._wavelength_m())

    def received_power_dbm(self, distance_sim_m: float) -> float:
        fspl_db = self.free_space_path_loss_db(distance_sim_m)
        return (
            self.profile.tx_power_dbm_reference
            + self.profile.tx_antenna_gain_dbi
            + self.profile.rx_antenna_gain_dbi
            - fspl_db
            - self.profile.system_loss_db
        )


# ---------------------------------------------------------------------------
# OFFLINE / METADATA ONLY below this line. Not constructed or called by
# BaselineSwarmRunner's active behavioral path. Useful for optional future
# physical-fidelity analysis or real-hardware engineering design, kept as
# PHYSICAL_IMPLEMENTATION_REFERENCE, not ACTIVE_BEHAVIORAL_SIMULATION_CONSTRAINT.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DevelopmentFreeSpacePathLossModel:
    """OFFLINE/METADATA ONLY -- not used by the active simulation (see
    module docstring). Same FSPL shape as `SimulatedNestRSSIModel`, but
    takes a REAL-equivalent distance (or converts simulation distance via
    `sim_to_real_linear_scale`) -- useful only for an optional, explicitly
    separate physical-fidelity comparison, never for behavioral decisions.
    """

    profile: NestBeaconHardwareProfile
    sim_to_real_linear_scale: float
    minimum_distance_m: float = 0.01

    def _wavelength_m(self) -> float:
        return SPEED_OF_LIGHT_MPS / self.profile.center_frequency_hz

    def free_space_path_loss_db(self, distance_real_m: float) -> float:
        d = max(distance_real_m, self.minimum_distance_m)
        return 20.0 * math.log10(4.0 * math.pi * d / self._wavelength_m())

    def received_power_dbm_at_real_distance(self, distance_real_m: float) -> float:
        fspl_db = self.free_space_path_loss_db(distance_real_m)
        return (
            self.profile.tx_power_dbm_reference
            + self.profile.tx_antenna_gain_dbi
            + self.profile.rx_antenna_gain_dbi
            - fspl_db
            - self.profile.system_loss_db
        )

    def received_power_dbm_at_sim_distance(self, distance_sim_m: float) -> float:
        """OFFLINE ONLY: converts simulation-scale distance to a
        REAL-equivalent separation before applying the path-loss equation.
        Not used by the active runner (see module docstring)."""
        distance_real_m = distance_sim_m / self.sim_to_real_linear_scale
        return self.received_power_dbm_at_real_distance(distance_real_m)


# ---------------------------------------------------------------------------
# Sim-to-real linear scale: OFFLINE / METADATA ONLY, derived (not guessed)
# from confirmed physical geometry already on record for this project. Not
# part of the active behavioral simulation's causal path.
# ---------------------------------------------------------------------------

# CONFIRMED_PHYSICAL, source: docs/sim_to_real_parameter_registry.json
# ("robot_radius": 0.05 m, "user specification") /
# docs/PHYSICAL_SCALE_AUDIT.md ("Robot body diameter / radius: 0.100 m /
# 0.050 m -- CONFIRMED_PHYSICAL"). This is the real robot's physical radius,
# independent of whichever simulation config is active.
REAL_ROBOT_RADIUS_M = 0.05

REAL_NEST_WIDTH_M = 0.25
REAL_NEST_HEIGHT_M = 0.25


def sim_to_real_linear_scale(sim_robot_radius_m: float) -> float:
    """SIM_TO_REAL_LINEAR_SCALE = simulation_robot_diameter / real_robot_diameter.

    Derived from the ACTIVE simulation robot radius (caller passes
    `_ROBOT_RADIUS_M` from swarm_baseline.py, itself read from
    config/robot_world.yaml's `shape.radius`) against the CONFIRMED_PHYSICAL
    real robot radius above. Never hardcode this ratio as a bare literal --
    always derive it from the two source radii so a future config change is
    caught rather than silently mismatched.
    """
    return (2.0 * sim_robot_radius_m) / (2.0 * REAL_ROBOT_RADIUS_M)


@dataclass(frozen=True)
class RectangularNestRegion:
    """OFFLINE / METADATA ONLY -- PHYSICAL_IMPLEMENTATION_REFERENCE, not
    part of the active simulation. An explicit rectangle representing the
    simulation-scale mapping of the real 25 cm x 25 cm Nest
    (`REAL_NEST_WIDTH_M` x `REAL_NEST_HEIGHT_M`) via `sim_to_real_linear_scale`,
    useful only for future real-hardware engineering design or an
    explicitly separate physical-fidelity study.

    The ACTIVE simulation NestRegion is `BaselineSwarmRunner.home_region_radius_m`
    (a circle, derived from Scout spawn geometry -- see
    docs/COMMON_NEST_INITIALIZATION_DESIGN.md) -- per the user's explicit
    decision, the simulation is NOT required to numerically match the real
    25x25 cm Nest; it only needs to be the same region for every
    experimental Condition (Test RF-10/PORT-10).

    `BaselineSwarmRunner` does not construct or call this class as part of
    its behavioral decision path. It remains available here as a
    correctly-derived reference for whenever a real Nest is physically
    designed. Note (see docs/NEST_BEACON_HARDWARE_PROFILE.md 'Nest-size
    vs Scout-layout conflict'): this correctly-scaled rectangle would be
    SMALLER than the currently configured Scout start layout in
    `config/robot_world.yaml` needs -- irrelevant to the active simulation
    (which does not use it) but relevant to a future real-hardware layout.
    """

    center_x_m: float
    center_y_m: float
    width_m: float
    height_m: float

    def contains(self, x_m: float, y_m: float) -> bool:
        half_w, half_h = self.width_m / 2.0, self.height_m / 2.0
        return (
            self.center_x_m - half_w <= x_m <= self.center_x_m + half_w
            and self.center_y_m - half_h <= y_m <= self.center_y_m + half_h
        )

    @classmethod
    def from_real_nest_spec(
        cls, *, center_x_m: float, center_y_m: float, sim_robot_radius_m: float,
    ) -> "RectangularNestRegion":
        scale = sim_to_real_linear_scale(sim_robot_radius_m)
        return cls(
            center_x_m=center_x_m, center_y_m=center_y_m,
            width_m=REAL_NEST_WIDTH_M * scale, height_m=REAL_NEST_HEIGHT_M * scale,
        )
