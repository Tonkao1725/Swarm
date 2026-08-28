# Sim-to-Real Software Architecture Correction: Validation Report

Scope: architecture/portability refactor only. No source change to WM
capacity/spacing/pruning, F3/F4 logic, `skip_unreachable`, obstacle
escape, resource positions/rates, Robot Energy, AIH, EM, or Exchange.

## Canonical Sim-to-Real definition (corrected)

Sim-to-Real means: the same core controller/decision **code** (WM, Home
confirmation, state machine, energy policy) is reusable on real hardware.
It does **not** mean simulation geometry must be numerically scaled to
match the real robot/Nest. See `docs/SIM_TO_REAL_SOFTWARE_ARCHITECTURE.md`.

## Required dependency audit (performed before editing)

| # | Dependency | Where | Classification |
| --- | --- | --- | --- |
| 1 | IR-SIM world pose (`self._pose(self.env, id)`) | `.run()` boot sequence, `_command_for`'s RETURN_HOME check, `_depleted_scout_can_be_restored`, executed-odometry computation | ENVIRONMENT_ONLY / SIM_ADAPTER |
| 2 | Nest global coordinates (`_nest_beacon.nest_x_m/y_m`) | only inside the old `_environment_home_confirmed` | mixed -- SPLIT into SIM_ADAPTER (distance check) + PORTABLE_CORE (AND logic) |
| 3 | `SIM_TO_REAL_LINEAR_SCALE` | `__init__` (beacon construction), `RectangularNestRegion.from_real_nest_spec` (both from the prior task) | was ACTIVE_BEHAVIORAL_SIMULATION_CONSTRAINT -- now REMOVE_FROM_CORE (offline/metadata only) |
| 4 | RSSI (`_nest_beacon.sample`) | only inside Home confirmation | SIM_ADAPTER feeding PORTABLE_CORE; confirmed absent from `_return_command`/`_explore_command` |
| 5 | Simulation-specific geometry (`home_region_radius_m`, `_SCOUT_START_STATES`) | Home-region/threshold derivation only | ENVIRONMENT_ONLY / SIM_ADAPTER |
| 6 | WM operations (`CycleWorkingMemory`) | `c2_working_memory.py` | already PORTABLE_CORE (confirmed: stdlib-only imports, no world/Nest/Resource/RSSI reference) |
| 7 | Home logic (AND of presence + RSSI) | previously inline in `_environment_home_confirmed` | was mixed SIM_ADAPTER+PORTABLE_CORE in one method -- now split |

## Refactor performed

1. New `src/swarm_simulate/home_observation.py` -- `HomeObservation`,
   `HomeConfirmationPolicy` (PORTABLE_CORE, stdlib-only imports),
   `RealHomeAdapterStub` (documented, unimplemented real-backend contract;
   `REAL_NEST_PRESENCE_SENSOR = "TBD / HARDWARE DESIGN PENDING"`).
2. `nest_beacon_hardware.py`: new `SimulatedNestRSSIModel` (ACTIVE model,
   operates directly on simulation-scale distance, no scale field at all).
   `DevelopmentFreeSpacePathLossModel`, `sim_to_real_linear_scale()`,
   `RectangularNestRegion.from_real_nest_spec` reclassified OFFLINE/
   METADATA-only -- present, correct, tested, but not constructed by
   `BaselineSwarmRunner`.
3. `swarm_baseline.py`: `ESP32NestBeaconModel` now wraps
   `SimulatedNestRSSIModel`. `__init__` no longer constructs
   `sim_to_real_linear_scale` or `real_scaled_nest_region`.
   `_environment_home_confirmed` now builds a `HomeObservation` (SIM
   ADAPTER) and delegates the decision to `self._home_policy.evaluate(...)`
   (PORTABLE_CORE, `HomeConfirmationPolicy`).
4. `home_signal_threshold` reclassified `SIMULATION_DEVELOPMENT_THRESHOLD`
   in comments/docs -- never presented as a real NodeMCU hardware value.
5. Datasheet wording correction: removed the `tx_power_datasheet_min_dbm`
   field/claim entirely (a single scalar "TX min" oversimplifies a
   multi-row per-modulation/rate datasheet table; the two extracted
   figures for WROOM-32E vs classic WROOM-32 could not be reconciled with
   confidence). `tx_power_datasheet_max_dbm` (19.5 dBm, both datasheets
   agree) is kept. The active `tx_power_dbm_reference` (2.0 dBm) comes
   from the separately-verified ESP-IDF TX-power API table, not either
   datasheet's typical-output-power table.

## PORT-1 through PORT-12

All 12 PASS (`tests/validate_sim_to_real_portability.py`):

```
PASS Test PORT-1: no C1/C2/WM/Return/Home decision depends on geometric sim-to-real scale conversion
PASS Test PORT-2: CycleWorkingMemory imports nothing from IR-SIM, Nest/Resource geometry, or the ESP32 API
PASS Test PORT-3: Home confirmation policy operates from an abstract observation + threshold only, with zero world-pose dependency
PASS Test PORT-4: the simulation adapter transforms environment Nest membership + simulated RSSI into a HomeObservation and delegates the decision to the portable policy
PASS Test PORT-5: RealHomeAdapterStub defines a clear, simulation-independent real-backend contract (read() -> HomeObservation) without inventing real Home-presence hardware
PASS Test PORT-6: RSSI influences only Home confirmation/logging; navigation uses = 0
PASS Test PORT-7: nest_presence influences only Home confirmation/lifecycle; navigation uses = 0
PASS Test PORT-8: identical-valued sim-style and real-style HomeObservations produce identical HOME_CONFIRMED decisions through the same policy code
PASS Test PORT-9: CycleWorkingMemory consumes synthetic executed odometry (moved_m, heading_delta_rad, cycle_id) with no IR-SIM involvement
PASS Test PORT-10: NodeMCU/ESP32-WROOM-32 hardware profile remains available for real-backend configuration; changing it requires no WM/controller/navigation code change
PASS Test PORT-11: physical-dimension metadata (real robot diameter, real Nest size) is absent from swarm_baseline.py entirely -- it cannot alter active behavioral simulation
PASS Test PORT-12 (structural check): Home confirmation pass/fail boundary (home_region_radius_m=1.05 m) is unchanged
```

## PORT-12: live C1/C2 before/after trajectory comparison

60 s smoke runs, seed `2118334751`, `FAST_HEADLESS_RESEARCH_MODE=1`,
comparing the immediately-prior task's live output (RF hardware alignment,
still using scale-coupled dBm) against this task's live output (scale
decoupled), same seed, both C1 and C2:

- **`swarm_trajectory.csv`**: `diff` exit code 0 -- **byte-identical** for
  both C1 and C2. Every position, heading, and physics tick is unchanged.
- **`swarm_events.csv`**: the *only* differing lines are the
  `HOME_RSSI_SAMPLE`/`HOME_CONFIRMED` `rssi=`/`threshold=` numeric detail
  strings (e.g. Scout0: `rssi=-22.267293; threshold=-24.629280` →
  `rssi=-36.246694; threshold=-38.608680`) -- a direct, expected, and
  justified consequence of removing the /5.0 scale division from the RSSI
  model's distance input (Scout1, at distance 0 from the Nest center,
  reads identically in both: `1.815106`, since the near-field
  `minimum_distance_m=0.01` clamp is scale-independent). `physical_region_ok`,
  `HOME_CONFIRMED` (both `True`), event ordering, and every non-RSSI event
  are identical.
- **`working_memory_events.csv`**: `diff` exit code 0 -- identical.

A second, wider comparison against the even-earlier Boot/Home-task run
(the original unitless 0-1 RSSI scalar, three architecture generations
back) also showed byte-identical trajectories -- the RSSI representation
has changed twice across this session's tasks (0-1 scalar → scaled dBm →
unscaled dBm) and physics/actions never moved at all, confirming RSSI has
never been part of the causal motion path.

**No unjustified behavioral mismatch found.** The one changed quantity
(RSSI/threshold dBm magnitude) is fully explained by this task's explicit,
required removal of scale coupling, and does not change any pass/fail
decision boundary, phase transition, or trajectory.

## Regression battery

| Suite | Result |
| --- | --- |
| HOME-1..15 | **PASS** (15/15) |
| RF-1..12 (reclassified RF-3/RF-5, see file header) | **PASS** (12/12) |
| PORT-1..12 | **PASS** (12/12) |
| C2 Acceptance A-J | **PASS** |
| F3/F4 Tests M-Q | **PASS** |
| Condition isolation | **PASS** |
| RSSI monotonicity (updated to `SimulatedNestRSSIModel`) | **PASS** |
| RSSI state reset | **PASS** |
| Persistent stationary-turn deadlock | **PASS** |
| Baseline termination architecture | **PASS** |
| C1 all-depleted termination | **PASS** |
| C1 energy accounting | **PASS** |
| `validate_c1_rssi_boundaries.py` | **FAIL -- pre-existing, unrelated** (same single cause as every prior report: F3's `memory.x_m`/`memory.y_m` in `_return_command`, untouched by this or the prior two tasks) |

## Verdict

`SIM-TO-REAL SOFTWARE ARCHITECTURE: READY FOR DEV RERUN`
