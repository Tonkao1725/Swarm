# C1/C2 Research Freeze Manifest

**v2 metadata/provenance correction (2026-08-28)**: this manifest and
`config/c1_c2_research_freeze_manifest.json` are versioned as
`research-c1-c2-common-v2`. v2 corrects exactly two issues found in v1
(commit `4498bf4ac28dcc9553b3744598cab2d927826dde`, tag
`research-c1-c2-common-v1`, **left unmoved and unmodified -- see
`docs/C2_PRE_FREEZE_REVIEW.md` history**):
1. This manifest's own self-referential `freeze_commit_sha` placeholder
   (see "Freeze commit resolution" below for the corrected,
   non-self-referential scheme).
2. `config/nest_beacon_hardware_profile.json`'s stale
   `tx_power_datasheet_min_dbm = -12.0` field (removed, not replaced --
   see `docs/NEST_BEACON_HARDWARE_PROFILE.md`).

**Behavioral source is byte-identical between v1 and v2** -- confirmed by
SHA-256 (see table below). No controller/WM/Home/RSSI/Solar/S4 behavior
was changed by this correction.

**Freeze date**: 2026-08-28
**Branch**: `c2-working-memory-dev-20260827`
**Source parent freeze commit**: `4498bf4ac28dcc9553b3744598cab2d927826dde`
(`research-c1-c2-common-v1`)

## Freeze commit resolution (non-self-referential)

A commit's manifest cannot embed that same commit's own resulting SHA --
changing the file to add the hash changes the hash. This file therefore
never states its own commit SHA. The authoritative resolution is Git
itself:

```
git rev-parse research-c1-c2-common-v2
# or, for the annotated tag object's peeled ref:
git rev-parse research-c1-c2-common-v2^{commit}
```

**Tag**: `research-c1-c2-common-v2` (annotated, on the metadata-correction commit)

## Environment

- Python: 3.13.7
- IR-SIM: 2.10.1
- Platform: Windows (win32)

## Research mode semantics

- `mission_mode = research`
- `nest_energy_target = 6`
- Simulation horizon: `3600 s`
- Scout count: `3`
- `FAST_HEADLESS_RESEARCH_MODE=1` for research execution (presentation-only;
  proven zero behavioral effect vs. rendered mode)

## Active C1 definition (Baseline)

```
WM  = OFF
EM  = OFF
Exchange = OFF
AIH = OFF
```

Stateless local-reactive Return; Boot/Home confirmation and RSSI-confirmation
Nest arrival are COMMON infrastructure (shared with C2, see below) --
`SWARM_EXPERIMENT_MODE=baseline`.

## Active C2 definition (Working Memory)

```
WM  = ON  (cycle-local odometric breadcrumb Working Memory)
EM  = OFF
Exchange = OFF
AIH = OFF
```

Return navigation: WM breadcrumb retrace + local ToF obstacle safety +
bounded committed-escape (S4 correction) + bounded route reacquisition
(F3/F4 correction, `skip_unreachable`). Boot/Home confirmation and RSSI
confirmation are identical common infrastructure to C1 --
`SWARM_EXPERIMENT_MODE=working_memory`.

## Common infrastructure (shared by C1 and C2, frozen at this commit)

- Boot/Home confirmation lifecycle (`SCOUT_BOOT` -> `HOME_RSSI_SAMPLE` ->
  `HOME_PHYSICAL_REGION_CHECK` -> `HOME_CONFIRMED`)
- `home_observation.HomeObservation` / `HomeConfirmationPolicy` (portable
  Home-confirmation core)
- RSSI interface: dBm via `nest_beacon_hardware.SimulatedNestRSSIModel`
  (active simulation model, no geometric sim-to-real scale coupling) +
  `nest_beacon_hardware.NODEMCU_ESP32_WROOM32_PROFILE` (real-hardware
  reference, `PROVISIONAL_UNTIL_BOARD_MARKING_VERIFIED`)
- SOLAR_TURN_45 EXPLORE correction (`_explore_command`,
  `solar_turn_progress_pending`)
- Termination architecture, energy accounting, Nest withdrawal/restoration

RSSI is confirmation-only in both Conditions (`RSSI navigation use = 0`,
regression-guarded by HOME-4/13, RF-9, PORT-6/7, S4-7/8).

## Canonical final research seeds (R01-R20) — recorded, NOT run in this task

| Seed ID | Value |
| --- | ---: |
| R01 | 82784102 |
| R02 | 98386804 |
| R03 | 358777504 |
| R04 | 385197017 |
| R05 | 413997162 |
| R06 | 517647040 |
| R07 | 565425870 |
| R08 | 711213266 |
| R09 | 1055674384 |
| R10 | 1116278677 |
| R11 | 1173346196 |
| R12 | 1191607443 |
| R13 | 1308983833 |
| R14 | 1399633088 |
| R15 | 1672527435 |
| R16 | 1710654405 |
| R17 | 1729431144 |
| R18 | 1759674302 |
| R19 | 1763236383 |
| R20 | 1985724812 |

**Final C1 R01-R20 and final C2 R01-R20 must both be run from this exact
freeze commit/tag** so the two Conditions remain comparable. Neither was
run in this task.

## Source SHA-256 (at freeze)

| File | SHA-256 |
| --- | --- |
| `main.py` | `39279bdf10a65e08828a29cef3c3a81bf616d132a025356376dcd841249afbd8` |
| `src/swarm_simulate/swarm_baseline.py` | `4fe1f3d6a604909fae33b13dd3194738937602a797f15f9d297dc95ceb015b36` |
| `src/swarm_simulate/c2_working_memory.py` | `b9a25db85f387f005be2bdee81edf0eb7982c62ebb20be224fc5f47af478b48d` |
| `src/swarm_simulate/home_observation.py` | `1aa9093df63183afc18a9050c7b89b622c0c7eff39e9c9bfac3cc2f4e1cd20e4` |
| `src/swarm_simulate/nest_beacon_hardware.py` | `e40d9d65bdfb80d8e4ff4239d3c941aef5c4af50e0a3b4e662da775628f4d920` |
| `src/swarm_simulate/energy_sensor.py` | `608befe45fe77c7a3b9a9c23c6d9b373bf642158a8e458e032d072a43ea3d3e1` |
| `config/robot_world.yaml` | `8488b4425e939f9d1bc88716358265fc1e507d238789c078fa3c33ad5836ca0d` |
| `config/nest_beacon_hardware_profile.json` | `ee325474cabfb4cd5f5fe4822603723123e16074ba4d5eb58a15c77cfd9746a6` (v2 -- changed from v1's `01e4b4cf...df500577`, metadata correction only, see below) |

**All six behavioral source files (`main.py` through `energy_sensor.py`)
are byte-identical between v1 and v2** -- confirmed by direct SHA-256
comparison before and after this correction. Only
`config/nest_beacon_hardware_profile.json` (machine-readable RF provenance
metadata, not behavioral code) changed.

## RF provenance correction (v2)

`config/nest_beacon_hardware_profile.json` previously retained
`tx_power_datasheet_min_dbm = -12.0` (and a provenance entry for it) even
though `nest_beacon_hardware.py`'s Python source had already removed the
corresponding dataclass field. On review, that -12.0 dBm figure does not
correspond to the ESP32-WROOM-32E Wi-Fi 802.11n HT40 MCS7 typical-TX-power
row at all -- Espressif's official Table 20 reports 13.0 dBm for that row
(802.11b 1 Mbps: 19.5 dBm; 802.11g 54 Mbps: 14.0 dBm; 802.11n HT20 MCS7:
13.0 dBm; 802.11n HT40 MCS7: 13.0 dBm); -12 dBm instead belongs to
Bluetooth RF power-control information, not the Wi-Fi MCS7 row.

**Correction applied**: the field and its provenance entry were removed
entirely from the JSON, matching the Python source. **Not** replaced with
13.0 dBm, since that figure is itself a per-modulation/per-rate typical
value, not a universal Wi-Fi module minimum -- stating it as a "TX
minimum" would repeat the same category error. `tx_power_datasheet_max_dbm
= 19.5` is retained (802.11b 1/11 Mbps typical TX reference, consistent
between the WROOM-32E and classic WROOM-32 datasheets). The active
development TX-power setting (`tx_power_esp_idf_units = 8`,
`tx_power_dbm_reference = 2.0`) remains classified `ESP_IDF` (an
ESP-IDF-configurable development setting, reproducible via
`esp_wifi_set_max_tx_power(8)`), never conflated with a datasheet TX
minimum.

`geometry_basis` (real robot radius, `sim_to_real_linear_scale`, real/
sim-scaled Nest dimensions) is now explicitly tagged
`"classification": "OFFLINE_PHYSICAL_IMPLEMENTATION_REFERENCE"` in the
JSON -- not an active behavioral simulation constraint (unchanged
statement of fact from v1's prose, now machine-readable).

## Active Freeze regression gate (all PASS at freeze time)

| Suite | File | Result |
| --- | --- | --- |
| HOME-1..15 | `tests/validate_c2_boot_home_confirmation.py` | PASS |
| PORT-1..12 | `tests/validate_sim_to_real_portability.py` | PASS |
| RF-1..12 | `tests/validate_esp32_nest_beacon_rf.py` | PASS |
| SOLAR-1..10 | `tests/validate_solar_turn_explore_deadlock.py` | PASS |
| S4-1..14 + FREEZE-1 | `tests/validate_c2_s4_return_correction.py` | PASS |
| C2 Acceptance A-J | `tests/validate_c2_working_memory.py` | PASS |
| F3/F4 Tests M-Q | `tests/validate_c2_return_correction.py` | PASS |
| Condition isolation | `tests/validate_condition_isolation.py` | PASS |
| Baseline termination architecture | `tests/validate_baseline_termination_architecture.py` | PASS |
| C1 all-depleted termination | `tests/validate_c1_all_depleted_termination.py` | PASS |
| C1 energy accounting | `tests/validate_c1_energy_accounting.py` | PASS |
| RSSI monotonicity | `tests/validate_rssi_monotonicity.py` | PASS |
| RSSI state reset | `tests/validate_rssi_state_reset.py` | PASS |
| Persistent stationary-turn deadlock | `tests/validate_persistent_stationary_turn_deadlock.py` | PASS |

## Preserved, non-active tests (explicitly not deleted)

- `tests/validate_c1_rssi_boundaries.py` -- diagnosed **STALE_TEST** under
  the current architecture (see `tests/C2_PRE_FREEZE_REVIEW.md` §F/G):
  its static AST checks encode two obsolete assumptions (no `.x_m`/`.y_m`
  attribute at all in `_return_command`, predating F3/F4's WM local-frame
  retrace; and an exact-inline-text expectation for
  `_environment_nest_reached`, predating its consolidation into the single
  canonical `_environment_home_confirmed` predicate). Preserved unmodified;
  excluded from the active gate.
- `tests/validate_physical_scale_geometry.py`,
  `tests/validate_physical_scale_motion.py` -- classified
  **PHYSICAL_FIDELITY / FUTURE_HARDWARE_VALIDATION**: they assert against a
  different, smaller-scale world (1.8 m arena, 0.05 m robot radius) than
  the active research configuration (14x14 m arena, 0.25 m robot radius).
  Geometric Sim-to-Real scale equivalence is explicitly not required for
  the current behavioral study (`docs/SIM_TO_REAL_SOFTWARE_ARCHITECTURE.md`).
  Preserved unmodified; excluded from the active gate.

## Historical C1 reference (preserved, not overwritten)

`origin/main` = `2cc0275bf29c40fedfba44e8865ac5696d61ec94` -- the historical
frozen Condition 1 baseline commit. This Freeze does **not** touch, merge
into, or rewrite `main`. Historical C1 Advisor/development results
generated against `2cc0275` remain valid **historical development
evidence**; current C1 is common-infrastructure-corrected and is not
required or expected to reproduce those exact historical trajectories.

## Known limitations (explicitly not controller defects)

- Not every Return attempt succeeds; energy depletion, time-limit
  termination, and local stochastic/navigation complexity are all valid
  experimental outcomes (see `tests/C2_S4_RETURN_CORRECTION_REPORT.md` §R
  for the classified breakdown of DEV01-03 failures).
- RSSI real-hardware threshold calibration is pending (simulation uses a
  `SIMULATION_DEVELOPMENT_THRESHOLD`, not a calibrated real value --
  `docs/NEST_BEACON_HARDWARE_PROFILE.md`).
- Real Nest-presence hardware/mechanism is not decided
  (`home_observation.RealHomeAdapterStub`,
  `REAL_NEST_PRESENCE_SENSOR = "TBD / HARDWARE DESIGN PENDING"`).
- Geometric Sim-to-Real scale equivalence is explicitly **not** part of the
  current behavioral study (`docs/SIM_TO_REAL_SOFTWARE_ARCHITECTURE.md`).
- The NodeMCU ESP32 / ESP32-WROOM-32 hardware profile remains
  `PROVISIONAL_UNTIL_BOARD_MARKING_VERIFIED` -- the exact purchased Nest
  board's module has not been physically confirmed.
- A real 25x25 cm Nest, once correctly sim-to-real scaled, would conflict
  with the currently configured Scout start layout
  (`docs/NEST_BEACON_HARDWARE_PROFILE.md` "Nest-size vs Scout-layout
  conflict") -- disclosed, deferred, not wired into the active simulation.

## Statement

**Final C1 (R01-R20) and final C2 (R01-R20) research datasets must both be
generated from this exact freeze commit/tag** so the two Conditions remain
comparable under identical common infrastructure. Neither was run as part
of this Freeze task.
