# Nest Beacon Hardware Profile — NodeMCU ESP32 / ESP32-WROOM-32

**2026-08-27 architecture-correction addendum:** this profile is a REAL
HARDWARE REFERENCE record only. The ACTIVE simulation RSSI model is a
separate SIMULATED RSSI SENSOR MODEL (`nest_beacon_hardware.SimulatedNestRSSIModel`)
that does **not** apply the geometric sim-to-real scale conversion
described in §G/§H below in its active causal path -- that conversion
(`sim_to_real_linear_scale`, `DevelopmentFreeSpacePathLossModel`,
`RectangularNestRegion`) is now OFFLINE/METADATA ONLY. See
`docs/SIM_TO_REAL_SOFTWARE_ARCHITECTURE.md` and
`tests/SIM_TO_REAL_PORTABILITY_REPORT.md`.

**2026-08-28 provenance correction (freeze v2):** the `tx_power_datasheet_min_dbm`
field/table row previously in this document was corrected in prose at the
time of the Sim-to-Real task above, but `config/nest_beacon_hardware_profile.json`
and this document's own table (§C) were not actually updated then --
`docs/C1_C2_RESEARCH_FREEZE_MANIFEST.md` "RF provenance correction (v2)"
now completes that correction in both files. The originally-recorded
`-12.0 dBm` figure was a data-extraction error: it does not correspond to
the ESP32-WROOM-32E Wi-Fi 802.11n HT40 MCS7 typical-TX-power row at all --
that figure belongs to Bluetooth RF power-control information, not the
Wi-Fi table. §C below is now corrected accordingly.

Status: DEVELOPMENT. `hardware_profile_status = PROVISIONAL_UNTIL_BOARD_MARKING_VERIFIED`.
Machine-readable record: `config/nest_beacon_hardware_profile.json`.
Code: `src/swarm_simulate/nest_beacon_hardware.py` (`NestBeaconHardwareProfile`,
`DevelopmentFreeSpacePathLossModel`, `RectangularNestRegion`).

## A. Intended Nest hardware — what was found

Repo-wide search (`grep -rn -i "esp32\|nodemcu"`) found **no** prior
reference to ESP32-S3 anywhere in active source or documentation. Every
prior mention was a generic, unspecified "ESP32"/"Nest ESP32"/"ESP32
Beacon" — no exact module was previously identified.

- **Intended board**: NodeMCU ESP32-class development board (user-specified).
- **Expected radio module**: NodeMCU-32S boards (the common "NodeMCU
  ESP32" dev board) carry the classic **ESP32-WROOM-32** module — verified
  via public board documentation (espboards.dev, Espressif module
  datasheets); NodeMCU-32S itself is not an Espressif-branded product, so
  no Espressif "NodeMCU" datasheet exists — the module inside it is the
  authoritative RF reference.
- **Exact module marking known?** **No** — the specific purchased board's
  printed module marking has not been physically verified.
- **Did code/docs previously assume ESP32-S3?** **No** — confirmed absent.

Per the task's explicit fallback: profile `NODEMCU_ESP32_WROOM32` is used
as the development target, marked
`hardware_profile_status = PROVISIONAL_UNTIL_BOARD_MARKING_VERIFIED`.

## B. Authoritative sources used

1. **ESP32-WROOM-32E & ESP32-WROOM-32UE Datasheet**, v2.1, Espressif
   Systems — [PDF](https://www.espressif.com/sites/default/files/documentation/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf) —
   the currently-recommended module datasheet (RF characteristics, Section
   7.1, Tables 19-23).
2. **ESP32-WROOM-32 Datasheet** (classic), v3.7, marked "Not Recommended
   For New Designs" (NRND), Espressif Systems —
   [PDF](https://www.espressif.com/sites/default/files/documentation/esp32-wroom-32_datasheet_en.pdf) —
   cross-check for the specific module family NodeMCU-32S boards actually carry.
3. **ESP-IDF Programming Guide — Wi-Fi API Reference** (`esp_wifi_set_max_tx_power`),
   Espressif Systems —
   [docs.espressif.com](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/network/esp_wifi.html).

No blogs, forums, retailer pages, or AI-generated summaries were used for
any adopted RF constant.

## C. Every adopted RF constant, with provenance

See `config/nest_beacon_hardware_profile.json`'s `"sources"` array for the
complete, machine-readable record (parameter, value, unit, source
document, version, section/table, URL, classification). Summary:

| Parameter | Value | Classification |
| --- | --- | --- |
| Wi-Fi band | 2412–2484 MHz | DATASHEET |
| Protocols | 802.11b/g/n | DATASHEET |
| TX power, datasheet max | 19.5 dBm (802.11b, 1/11 Mbps) | DATASHEET |
| RX sensitivity (reference) | -97.0 dBm (802.11b, 1 Mbps) | DATASHEET |
| ESP-IDF TX-power unit | 0.25 dBm/step | ESP_IDF |
| ESP-IDF TX-power selected | raw unit 8 → 2.0 dBm | ESP_IDF |
| Wi-Fi channel | 6 (2437 MHz) | DEVELOPMENT_ASSUMPTION |
| TX/RX antenna gain | 0 dBi each | DEVELOPMENT_ASSUMPTION (neutral) |
| System loss | 0 dB | DEVELOPMENT_ASSUMPTION (neutral) |
| Home signal threshold | derived, dBm | PHYSICAL_MEASUREMENT_PENDING |

**No single "TX power, datasheet min" field is recorded.** Espressif's
Table 20 (Wi-Fi RF Characteristics) reports *typical* TX output power per
modulation/rate, not a single module-wide minimum: 802.11b 1 Mbps
19.5 dBm; 802.11g 54 Mbps 14.0 dBm; 802.11n HT20 MCS7 13.0 dBm; 802.11n
HT40 MCS7 13.0 dBm. Recording any one of these as "the minimum" would
misrepresent a per-rate typical value as a module-wide bound -- the
previously-recorded `-12.0 dBm` figure was worse than that: a
data-extraction error unrelated to this table entirely (Bluetooth RF
power-control information, not Wi-Fi). Only the unambiguous, consistently
published maximum (19.5 dBm, 802.11b 1/11 Mbps, agreeing between the
WROOM-32E and classic WROOM-32 datasheets) is kept as a machine-readable
field. This does not affect the adopted TX-power *reference* value used by
the propagation model (2.0 dBm, from the separately-sourced ESP-IDF API
table, never from this datasheet table at all).

## D. TX power selection

`esp_wifi_set_max_tx_power()` (ESP-IDF, classic ESP32): unit is 0.25 dBm;
raw range `[8, 84]`; the exact table of achievable steps includes
`{8:2, 20:5, 28:7, 34:8, 44:11, 52:13, 56:14, 60:15, 66:16, 72:18, 80:20}`
(raw units → dBm).

**2 dBm remains** (raw unit 8) — verified, not blindly copied: it is the
lowest step in the *official* ESP-IDF table, so it is guaranteed
achievable and reproducible on real classic-ESP32 hardware via
`esp_wifi_set_max_tx_power(8)`. It is intentionally the *lowest*
documented step, not the highest, because the Nest Beacon should only be
strongly confirmable at short range for a small (25×25 cm real) Nest —
a high-power Beacon would make RSSI-based confirmation meaningful over a
much larger, less physically-precise area than the Nest itself.

## E. Wi-Fi channel / frequency

`BEACON_WIFI_CHANNEL = 6` (2437 MHz) — a standard, non-edge, ESP32-supported
2.4 GHz channel, common in 802.11 deployments. Center frequency is always
*derived* from the channel via the IEEE 802.11 standard mapping
(`center_MHz = 2407 + 5 * channel`, `nest_beacon_hardware.wifi_channel_to_center_frequency_hz`)
— never hardcoded independently of the channel number. The channel remains
configurable (`NestBeaconHardwareProfile.wifi_channel`).

## F. RF propagation model

`DevelopmentFreeSpacePathLossModel` — free-space path loss (FSPL), applied
over the **real-equivalent** (sim-to-real-scaled) separation, never raw
enlarged simulation distance:

```
FSPL(dB) = 20 log10(4*pi*d_real / lambda),  lambda = c / f
Pr(dBm)  = Pt(dBm) + Gt(dBi) + Gr(dBi) - FSPL(dB) - Lsystem(dB)
```

Explicitly classified **DEVELOPMENT PROPAGATION BASELINE** — not claimed
accurate for an indoor maze. No random fading, Rayleigh, log-normal
shadowing, wall-attenuation constant, or orientation noise is added; the
model is deterministic until sourced physical measurement data justifies
adding one (see §H).

Real Wi-Fi may diffract around or penetrate maze walls — RSSI is
deliberately **not** made to obey ToF/light line-of-sight. The defense
against "Home through a wall" is the separate physical-region membership
check (`NestRegion`/`home_region_radius_m`), not RSSI itself — a Scout
outside the Nest region with strong RSSI is still `NOT HOME` (Test RF-8,
HOME-8/10/12).

## G. Sim-to-real distance scaling

```
SIM_TO_REAL_LINEAR_SCALE = simulation_robot_diameter / real_robot_diameter
                          = 0.50 m / 0.10 m
                          = 5.0
```

- Simulation robot radius: **0.25 m**, source: `config/robot_world.yaml`
  `robot.shape.radius` (the ACTIVE configuration).
- Real robot radius: **0.05 m**, source: `docs/sim_to_real_parameter_registry.json`
  (`robot_radius`, `CONFIRMED_PHYSICAL`, "user specification"), cross-checked
  in `docs/PHYSICAL_SCALE_AUDIT.md` ("Robot body diameter / radius: 0.100 m
  / 0.050 m — CONFIRMED_PHYSICAL").

This is **derived**, not assumed — it happens to equal the commonly-cited
"scale 5," but is computed here from the two independently-sourced radii,
not taken on faith.

Every RF distance computation converts simulation-scale distance to this
real-equivalent separation before evaluating the path-loss equation
(`received_power_dbm_at_sim_distance`); the model never receives raw
enlarged simulation distance directly (Test RF-3).

## H. 25×25 cm Nest mapping — and a discovered conflict

```
sim Nest width  = 0.25 m x 5.0 = 1.25 m
sim Nest height = 0.25 m x 5.0 = 1.25 m
```

`RectangularNestRegion.from_real_nest_spec(...)` implements this exactly
and is unit-tested (`.contains(x, y)`). **This is NOT wired into the live
`_environment_home_confirmed` gate** used by `.run()` in this task. Reason:

**Nest-size vs. Scout-layout conflict (discovered, not resolved).** The
currently configured Scout start layout (`_SCOUT_START_STATES` in
`swarm_baseline.py`, from `config/robot_world.yaml`) places up to 4 Scouts
in a row spanning `x: 1.00–3.35 m` (real-equivalent: 0.47 m). A correctly
real-scaled 1.25×1.25 m square Nest, centered on that layout's centroid,
contains **only 1 of the 3** currently-configured Scout starts (Scout1,
which sits exactly at the centroid) — Scout0 and Scout2 fall outside it.
Wiring the correctly-scaled rectangle into live Boot confirmation would
therefore raise `INVALID_INITIAL_HOME_STATE` for most currently-configured
Scouts, i.e. would break the simulation for every existing test and smoke
run, C1 and C2 alike.

This is a genuine, evidence-based contradiction between two independently
correct-looking specifications (the real 25×25 cm Nest size, and the
existing Scout spawn row), not a bug in either taken alone. Resolving it
requires a decision this document does not make: either (a) the real Nest
is larger than 25×25 cm to physically hold the intended number of ~10 cm
diameter robots with the currently configured spacing, or (b) the Scout
start layout needs to be redesigned to actually fit inside a 25×25 cm real
Nest (which, at 1:1, cannot comfortably fit even 3 robots of 10 cm
diameter side by side with margin — 3 x 0.10 m = 0.30 m already exceeds
0.25 m). See `tests/C2_CANONICAL_HOME_ARRIVAL_REPORT.md` for the full
finding and required next step.

The existing provisional circular Home region (`home_region_radius_m`,
derived from Scout spawn geometry, verified wall-safe for the current
maze — see `docs/COMMON_NEST_INITIALIZATION_DESIGN.md` §8) remains the
ACTIVE region for Boot/Return confirmation until this conflict is resolved.

## I. RSSI dBm propagation model — summary

`ESP32NestBeaconModel` (in `swarm_baseline.py`) wraps
`DevelopmentFreeSpacePathLossModel`. `.sample(pose)` / `.sample_at_distance(d)`
return dBm. Confirmation-only: never exposes beacon x/y, bearing, or
distance to any navigation method (Tests RF-9, HOME-4/13).

## J. Provisional Home threshold

`home_signal_threshold` is computed as the dBm reading at the (still
circular, provisional) `home_region_radius_m` boundary — a policy value,
not a datasheet fact. Classified `PHYSICAL_MEASUREMENT_PENDING`,
configurable, and explicitly documented as pending replacement once real
hardware measurements (§L) are available. It is not, and must never be
presented as, an Espressif datasheet value.

## K. Receiver sensitivity vs. Home threshold

Kept as two entirely separate values/concepts:
- **RX sensitivity** (`rx_sensitivity_dbm_reference`, -97.0 dBm, DATASHEET):
  "can the radio receive the signal at all?" — a hardware detectability floor.
- **Home threshold** (`home_signal_threshold`, PHYSICAL_MEASUREMENT_PENDING):
  "is the received Nest signal strong enough to support Home confirmation?" —
  a policy value, far above the detectability floor (Test RF-6, `>20 dB`
  headroom over RX sensitivity by construction).

## L. Future physical calibration plan

When the real NodeMCU Nest Beacon hardware is available, collect RSSI
(dBm) samples at, at minimum:

**Inside Nest:** center; 4 corners; 4 edge midpoints.
**Outside Nest:** immediately outside each side; 25 cm away; 50 cm away; 1 m away.
**Maze-relevant:** adjacent corridor; directly behind a maze wall; around a wall corner.
**Orientation:** Scout antenna facing Nest; 90°; 180°; 270°.

Collect repeated samples at each point. Recommended stored fields (not
fabricated here — no values recorded until physical measurement occurs):

```
position_class, distance_m, orientation_deg, wall_condition, sample_count,
mean_rssi_dbm, median_rssi_dbm, std_rssi_db, min_rssi_dbm, max_rssi_dbm
```
