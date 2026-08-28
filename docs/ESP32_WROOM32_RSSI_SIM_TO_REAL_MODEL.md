# ESP32-WROOM-32 RSSI Sim-to-Real Model

**2026-08-27 architecture-correction addendum:** "Sim-to-Real" in this
project's canonical sense means shared controller CODE, not matched
geometry -- see `docs/SIM_TO_REAL_SOFTWARE_ARCHITECTURE.md`. The
step-by-step model below (using `SIM_TO_REAL_LINEAR_SCALE`) describes the
OFFLINE/METADATA-only `DevelopmentFreeSpacePathLossModel`, kept available
for optional future physical-fidelity analysis. The ACTIVE simulation
model actually driving C1/C2 behavior is `SimulatedNestRSSIModel`
(`nest_beacon_hardware.py`), which applies the same FSPL shape directly to
simulation-scale distance, with **no** scale conversion in its causal
path. See `tests/SIM_TO_REAL_PORTABILITY_REPORT.md` for the live
before/after trajectory comparison proving this change altered only the
RSSI/threshold dBm magnitude, not any Boot/Return/WM behavior.

Status: DEVELOPMENT PROPAGATION BASELINE. For hardware provenance and the
full parameter table, see `docs/NEST_BEACON_HARDWARE_PROFILE.md`. This
document focuses on how simulated RSSI (dBm) is computed from simulation
geometry, and how it maps to the real ESP32-WROOM-32 Beacon.

## Architecture

Three separated layers (`src/swarm_simulate/nest_beacon_hardware.py` +
`ESP32NestBeaconModel` in `swarm_baseline.py`):

```
NestBeaconHardwareProfile   (datasheet + ESP-IDF facts, no math)
        |
DevelopmentFreeSpacePathLossModel  (analytical dBm estimate, DEV BASELINE)
        |
ESP32NestBeaconModel.sample(pose) -> dBm   (environment-owned; controller
                                             receives only this scalar)
```

`HomeConfirmationPolicy` (the AND of physical-region membership and RSSI
threshold) stays in `swarm_baseline.py`'s `_environment_home_confirmed` --
this model never makes a Home/no-Home decision itself.

## Canonical description

> The Nest uses a NodeMCU ESP32-class board based on the classic
> ESP32-WROOM-32 radio profile to provide a 2.4 GHz Wi-Fi Beacon. Scouts
> use received Beacon RSSI only to confirm Home membership. Working Memory
> remains responsible for Return navigation.

The exact board/module is **not** stated as final hardware fact until the
purchased Nest board's marking is physically verified
(`hardware_profile_status = PROVISIONAL_UNTIL_BOARD_MARKING_VERIFIED`).

## RSSI computation, step by step

1. Simulation computes Euclidean distance `d_sim` (simulation-scale
   meters) between a Scout's pose and the Nest beacon position.
2. `d_real = d_sim / SIM_TO_REAL_LINEAR_SCALE` (= 5.0, derived — see
   `docs/NEST_BEACON_HARDWARE_PROFILE.md` §G) converts to the
   real-equivalent separation. **The link-budget equation never receives
   `d_sim` directly** (Test RF-3).
3. `FSPL(dB) = 20*log10(4*pi*d_real / lambda)`, `lambda = c / f_center`.
4. `Pr(dBm) = Pt(dBm) + Gt(dBi) + Gr(dBi) - FSPL(dB) - Lsystem(dB)`, with
   `Pt = 2.0 dBm` (ESP-IDF `esp_wifi_set_max_tx_power(8)`), `Gt = Gr = 0
   dBi`, `Lsystem = 0 dB` (all DEVELOPMENT_ASSUMPTION, neutral pending
   calibration).

Worked example (3-Scout layout, `home_region_radius_m = 1.05` m sim =
0.21 m real):

| d_sim (m) | d_real (m) | Pr (dBm) |
| ---: | ---: | ---: |
| 0.0 | 0.0 | 1.82 (near-field floor, min_distance_m=0.01) |
| 0.5 | 0.10 | -18.18 |
| 0.8 | 0.16 | -22.27 |
| 1.05 | 0.21 | -24.63 (current provisional `home_signal_threshold`) |
| 2.0 | 0.40 | -30.23 |
| 5.0 | 1.00 | -38.18 |

All values comfortably above the -97 dBm RX-sensitivity floor (Test RF-6)
-- detectability was never in question at these ranges; the Home threshold
is a policy choice, not a detectability limit.

## Simulation vs. real hardware

| | Simulation | Real hardware |
| --- | --- | --- |
| Signal source | `DevelopmentFreeSpacePathLossModel` -- deterministic analytical FSPL | ESP32-WROOM-32 real RF, subject to multipath/fading/attenuation |
| Output unit | dBm | dBm (real RSSI) |
| Wall behavior | RSSI computed from raw Euclidean distance only -- **not** gated by line-of-sight/walls (real Wi-Fi may diffract/penetrate) | same expected real-world behavior |
| "Home through a wall" defense | The separate `NestRegion`/physical-membership check, not RSSI (Test RF-8, HOME-12) | same |
| Noise/fading | None added (deterministic) | present; not modeled here |
| Used for | Boolean confirmation only | same intended role |

## What is NOT modeled (by design, pending calibration)

Gaussian noise, Rayleigh fading, log-normal shadowing variance, a wall
attenuation constant, and antenna-orientation noise are all deliberately
absent. None will be added without sourced measurement data or a clearly
cited standard model (see the calibration plan in
`docs/NEST_BEACON_HARDWARE_PROFILE.md` §L).

## Known open item

The correctly real-scaled 1.25×1.25 m Nest rectangle (from the real
25×25 cm spec) conflicts with the currently configured Scout start layout
-- see `docs/NEST_BEACON_HARDWARE_PROFILE.md` §H and
`tests/C2_CANONICAL_HOME_ARRIVAL_REPORT.md`. This document's RSSI/dBm
model is independent of that conflict and is unaffected by how it is
eventually resolved.
