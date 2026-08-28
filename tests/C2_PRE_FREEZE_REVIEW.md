# C2 Pre-Freeze Architecture Review

Date: 2026-08-28. Scope: semantic decoupling of the S4 committed-escape
threshold, closure/classification of every currently-failing test in the
active suite, and a formal Freeze readiness recommendation. **No Research
Freeze tag was created. No commit was made. R01-R20 were not run. C3 was
not started.**

## Source safety

SHA-256 recorded before this task's edit:

| File | Before | After | Status |
| --- | --- | --- | --- |
| `main.py` | `39279bdf...49afbd8` | `39279bdf...49afbd8` | unchanged |
| `src/swarm_simulate/swarm_baseline.py` | `97fac7b2...098e469b` | (changed) | **this task's only edit** |
| `src/swarm_simulate/c2_working_memory.py` | `b9a25db8...f478b48d` | `b9a25db8...f478b48d` | unchanged |
| `src/swarm_simulate/home_observation.py` | `1aa9093d...cd20e4` | `1aa9093d...cd20e4` | unchanged |
| `src/swarm_simulate/nest_beacon_hardware.py` | `e40d9d65...628f4d920` | `e40d9d65...628f4d920` | unchanged |
| `src/swarm_simulate/energy_sensor.py` | `608befe4...43ea3d3e1` | `608befe4...43ea3d3e1` | unchanged |

Only `swarm_baseline.py` changed. `c2_working_memory.py` was not touched --
no new proven defect was found in it.

## A. Escape-bound dependency before review

`_return_command`'s S4 committed-escape completion check read
`memory.spacing_m` directly (`>= memory.spacing_m`) -- a `CycleWorkingMemory`
storage/breadcrumb-recording parameter, not a physical/body quantity.

## B. Whether `memory.spacing_m` coupling existed

**Yes, confirmed by direct source grep before this review's edit.**
Classified: **SEMANTIC COUPLING DEFECT** (not a behavioral performance
defect -- the numeric threshold, 0.25 m, was already correct; only its
*derivation* was wrong).

## C. Correct physical/controller derivation

`self.return_obstacle_escape_min_translation_m = _ROBOT_RADIUS_M`, set
once in `__init__` from the existing module-level `_ROBOT_RADIUS_M = 0.25`
constant (the same value `config/robot_world.yaml`'s `shape.radius`
supplies and `_add_scouts`/`home_region_radius_m` already use) -- a
physical body-geometry quantity, never read from any WM instance. The
escape-completion check now reads `self.return_obstacle_escape_min_translation_m`
instead of `memory.spacing_m`.

## D. Numeric behavior before/after

**Identical: 0.25 m in both cases** (`_ROBOT_RADIUS_M == memory.spacing_m
== 0.25`, verified directly). Deterministic equivalence was not merely
attempted but **proven**: DEV01-03 trajectories are **byte-identical**
before and after this refactor (`diff` exit code 0 on all three
`swarm_trajectory.csv` files, full 3600 s runs) -- confirming zero
behavioral change, only a semantic/architectural correction.

## E. FREEZE-1 result

**PASS** (`tests/validate_c2_s4_return_correction.py`,
`test_freeze1_wm_spacing_escape_decoupled`): proves (1) the runner-level
threshold is set from `_ROBOT_RADIUS_M`, never from any WM instance; (2)
the escape-completion source code contains no reference to
`memory.spacing_m` at all; (3) behaviorally, changing a WM instance's
`spacing_m` to 0.5 m (double the canonical value) has **zero effect** on
the escape threshold, which still resolves at exactly 0.25 m; (4) the
canonical spacing (0.25 m) still produces the identical 0.25 m physical
escape threshold as before the refactor.

## F. `validate_c1_rssi_boundaries.py` root cause

Investigated directly against current source (not merely re-labeled).
**Two independent stale assertions, both traced to exact code**:

1. `return_attrs & {'x_m','y_m'}` is non-empty. Enumerated every
   `.x_m`/`.y_m` access inside `_return_command`'s AST: **100% are
   `memory.x_m`/`memory.y_m`** (`CycleWorkingMemory`'s own local
   odometric frame, reset to `(0,0)` every cycle, proven
   backend-independent and non-global by Tests PORT-2/PORT-3, RF-9,
   HOME-4, S4-7/S4-8). **Zero** are a global/Nest/world coordinate. This
   assertion encodes an assumption from before the F3/F4 WM local-frame
   retrace existed in `_return_command` (an earlier architecture
   generation where the function legitimately touched no `.x_m`/`.y_m`
   attribute of any kind).
2. `"physical_entry" in arrival_span` and `".sample(" in arrival_span`
   are both `False` for `_environment_nest_reached`. Confirmed directly:
   that method now reads `home_confirmed, _rssi, _physical_region_ok =
   self._environment_home_confirmed(pose)` -- it delegates to the single
   canonical Home predicate (the Canonical Home Arrival task's explicit,
   required consolidation: "do not duplicate slightly different Home
   rules across code paths") instead of inlining the literal text this
   assertion expects.

## G. Final classification/disposition

**Classification: A -- STALE_TEST** (both sub-defects). Not
`GENUINE_ACTIVE_DEFECT`: every property this test attempts to verify (no
RSSI navigation steering, no global Nest-coordinate leak into Return,
physical-entry-plus-RSSI arrival confirmation) is independently,
currently, and more precisely re-verified by tests that already pass on
this exact source: HOME-3/4/9/10/11/13/14, RF-8/9, S4-7/8, PORT-2/3/4.

**Disposition**: preserved unmodified (not edited, not deleted -- no
authorization was given to alter a test in C1's boundary-audit suite, and
C1's frozen-control status warrants caution even for test files).
**Excluded from the ACTIVE Freeze regression gate** (§I) as a documented,
explained exclusion -- not an unexplained red test. Recommended, not
performed: a future, explicitly-authorized task to update this test's
assertions (attribute-name specificity, `_environment_nest_reached`'s
exact-text expectation) to match the current, correct architecture.

## H. Physical-scale tests classification

`tests/validate_physical_scale_geometry.py` /
`validate_physical_scale_motion.py`: both assert against a **different,
smaller-scale** world (`ARENA=1.8 m`, `ROBOT_RADIUS=0.05 m`) than the
currently active research configuration (`config/robot_world.yaml`:
14x14 m arena, `robot_radius=0.25 m`). These files are untracked
leftovers from an earlier, separate "1:1 physical scale" exploration task
that was never adopted as the active config (confirmed via `git stash` at
the very start of this session's C2 work -- both already failed at HEAD,
unrelated to any subsequent task).

**Reclassified: PHYSICAL_FIDELITY / FUTURE_HARDWARE_VALIDATION**, not
active C1/C2 behavioral Freeze tests. Not deleted, not modified, not used
to justify any change to the active behavioral simulation (per the
canonical Sim-to-Real architecture: geometric scale equivalence is
explicitly not required for behavioral experiments --
`docs/SIM_TO_REAL_SOFTWARE_ARCHITECTURE.md`).

## I. Active Freeze regression test suite (explicit definition)

| Suite | File |
| --- | --- |
| HOME-1..15 | `tests/validate_c2_boot_home_confirmation.py` |
| PORT-1..12 | `tests/validate_sim_to_real_portability.py` |
| RF-1..12 | `tests/validate_esp32_nest_beacon_rf.py` |
| SOLAR-1..10 | `tests/validate_solar_turn_explore_deadlock.py` |
| S4-1..14 + FREEZE-1 | `tests/validate_c2_s4_return_correction.py` |
| C2 Acceptance A-J | `tests/validate_c2_working_memory.py` |
| F3/F4 Tests M-Q | `tests/validate_c2_return_correction.py` |
| Condition isolation | `tests/validate_condition_isolation.py` |
| Baseline termination architecture | `tests/validate_baseline_termination_architecture.py` |
| C1 all-depleted termination | `tests/validate_c1_all_depleted_termination.py` |
| C1 energy accounting | `tests/validate_c1_energy_accounting.py` |
| RSSI monotonicity | `tests/validate_rssi_monotonicity.py` |
| RSSI state reset | `tests/validate_rssi_state_reset.py` |
| Persistent stationary-turn deadlock | `tests/validate_persistent_stationary_turn_deadlock.py` |

**Explicitly excluded, with documented reason (§F-H)**:
`tests/validate_c1_rssi_boundaries.py` (STALE_TEST),
`tests/validate_physical_scale_geometry.py` /
`validate_physical_scale_motion.py` (PHYSICAL_FIDELITY, different config).

## J. Active regression result

**All 14 active suites PASS.** No unexplained red test in the active
Freeze gate.

## K. C1 isolation

Verified across every task this session that touched common
infrastructure (Boot/Home, Canonical Home Arrival, RF hardware,
Sim-to-Real portability, Solar correction, S4 correction): C1
(`working_memory_enabled=False`) still completes the full Boot/Home
sequence and stateless local-reactive Return, creates no WM object, and
the S4/Solar corrections are structurally gated so C1 cannot reach them
(Tests S4-9, and the Solar correction's branch has no WM dependency at
all). `validate_condition_isolation.py` (active gate) confirms no
motor-command replay/cross-condition leakage.

## L. C2 S4 isolation

**Confirmed (Test S4-9, re-verified this task)**: the entire
committed-escape mechanism (fields and logic) lives inside
`if self.working_memory_enabled and memory is not None:` in
`_return_command`. With WM disabled, this code is unreachable in
principle -- C1 gains no breadcrumb Return, WM target state, route
reacquisition, or S4 committed-escape state.

## M. DEV01-03 validation (rerun required -- source changed)

Rerun exactly as specified (seeds 2118334751 / 920265301 / 652974033; C2;
3600 s; 3 Scouts; research mode; Nest target 6):

| Run | `experimental_validity` | Deliveries (S0/S1/S2) | S1 recurrence | Solar pathology | S4 pathology |
| --- | --- | --- | --- | --- | --- |
| DEV01 | **VALID** | 0/0/2 | 0 | 0 | 0 |
| DEV02 | **VALID** | 4/4/1 | 0 | 0 | 0 |
| DEV03 | **VALID** | 2/1/0 | 0 | 0 | 0 |

**Trajectories are byte-identical to the pre-decoupling S4-correction
run** (§D) -- this rerun exists to satisfy the "source changed, must
rerun" rule, not because different behavior was expected or found.
Aggregate funnel: 20 Return attempts, 14 NEST_REACHED (unchanged from the
prior stage, exactly as the byte-identical trajectories predict).

Per the acceptance criteria explicitly given (not higher success rate):
all engineering VALID -- met; S1 recurrence 0 -- met; Solar pathology
recurrence 0 -- met; S4 pathological recurrence 0 -- met; no new
controller pathology -- met.

## N. Remaining known limitations

- 6 of 20 Return attempts still fail, classified (per
  `tests/C2_S4_RETURN_CORRECTION_REPORT.md` §R, unchanged by this task
  since trajectories are identical): 4x `A_ENERGY_DEPLETION`, 1x
  `C_TIME_HORIZON`, 1x `F_LEGITIMATE_LOCAL_OBSTACLE_COMPLEXITY`. These are
  explicitly **not** controller defects per this task's own acceptance
  rule ("energy depletion, time-horizon ending, local
  stochastic/navigation difficulty ... are experimental outcomes").
- `validate_c1_rssi_boundaries.py` remains stale (§F/G) -- flagged, not
  fixed, pending explicit authorization for a test-only update.
- The real 25x25 cm Nest vs. the current Scout start layout conflict
  (`docs/NEST_BEACON_HARDWARE_PROFILE.md` "Nest-size vs Scout-layout
  conflict") remains an open, disclosed, deferred item -- irrelevant to
  the active simulation (never wired in) but relevant to a future real
  hardware layout.
- `docs/CURRENT_REPO_AUDIT.md`, `docs/PHYSICAL_SCALE_AUDIT.md`,
  `docs/sim_to_real_parameter_registry.json`,
  `validate_physical_scale_geometry.py`/`_motion.py` remain as
  pre-existing, untracked, out-of-scope artifacts from an earlier session
  task -- not addressed here, not blocking.

## O. Common C1 implications

Home/Boot architecture, RSSI interface changes (dBm model,
`HomeConfirmationPolicy` decoupling), and the SOLAR Explore correction are
**common infrastructure** and may legitimately alter C1 relative to the
historical frozen commit `2cc0275` and tag `baseline-condition1-v1`. Per
this session's explicit, repeated instruction: current C1 is **not**
required to reproduce old historical trajectories, and the historical C1
Advisor/frozen results remain valid **historical development evidence**,
not something to be silently preserved by reverting the corrected common
infrastructure. The final research C1 and C2 datasets (R01-R20, not run
in this task) must be generated together under this same current common
infrastructure so they remain comparable to each other.

## P. Source files intended for Freeze

**Source**: `src/swarm_simulate/swarm_baseline.py`,
`src/swarm_simulate/c2_working_memory.py` (unchanged, still frozen at its
pre-Boot/Home-era content), `src/swarm_simulate/home_observation.py`,
`src/swarm_simulate/nest_beacon_hardware.py`, `main.py` (unchanged this
session's edits).

**Tests (active gate)**: the 14 files in §I.

**Documentation**: `docs/COMMON_NEST_INITIALIZATION_DESIGN.md`,
`docs/C2_WORKING_MEMORY_DESIGN.md`,
`docs/NEST_BEACON_HARDWARE_PROFILE.md`,
`docs/ESP32_WROOM32_RSSI_SIM_TO_REAL_MODEL.md`,
`docs/SIM_TO_REAL_SOFTWARE_ARCHITECTURE.md`,
`config/nest_beacon_hardware_profile.json`.

**Development-result reports (historical evidence, preserved, not code)**:
every `tests/*_REPORT.md`, `*_DIAGNOSIS.md`, and `*.csv` produced across
this session's Boot/Home, Canonical Home Arrival, RF hardware,
Sim-to-Real portability, Solar, and S4 tasks.

**Not intended for Freeze / excluded**:
`tests/validate_c1_rssi_boundaries.py` (stale, preserved),
`tests/validate_physical_scale_geometry.py`,
`tests/validate_physical_scale_motion.py` (physical-fidelity, different
config), `docs/CURRENT_REPO_AUDIT.md`, `docs/PHYSICAL_SCALE_AUDIT.md`,
`docs/sim_to_real_parameter_registry.json` (pre-existing, unrelated,
untouched).

## Pre-Freeze source cleanliness (`git status` audit)

| Category | Files |
| --- | --- |
| SOURCE (modified/new) | `swarm_baseline.py` (M), `home_observation.py`, `nest_beacon_hardware.py` |
| TEST (active, new/modified) | `validate_rssi_monotonicity.py` (M), `validate_c2_boot_home_confirmation.py`, `validate_c2_s4_return_correction.py`, `validate_esp32_nest_beacon_rf.py`, `validate_sim_to_real_portability.py`, `validate_solar_turn_explore_deadlock.py` |
| TEST (historical, excluded) | `validate_physical_scale_geometry.py`, `validate_physical_scale_motion.py` |
| DOCUMENTATION (this session's tasks) | `C2_WORKING_MEMORY_DESIGN.md` (M), `COMMON_NEST_INITIALIZATION_DESIGN.md`, `ESP32_WROOM32_RSSI_SIM_TO_REAL_MODEL.md`, `NEST_BEACON_HARDWARE_PROFILE.md`, `SIM_TO_REAL_SOFTWARE_ARCHITECTURE.md`, `nest_beacon_hardware_profile.json` |
| DOCUMENTATION (pre-existing, unrelated) | `CURRENT_REPO_AUDIT.md`, `PHYSICAL_SCALE_AUDIT.md`, `sim_to_real_parameter_registry.json` |
| DEVELOPMENT RESULT (historical evidence) | 13 `tests/*_REPORT.md`/`*_DIAGNOSIS.md`/`*.csv` files from this session's tasks |
| RUNTIME SCRATCH | `config/robot_world_runtime.yaml` (M) -- auto-regenerated by every `main.py` run; diff is pure YAML re-serialization format (flow- vs block-style), reconfirmed this task, zero semantic change |
| UNRELATED | none found |

No file was staged. No commit was made, per instruction.

## Q. C2 controller development status

**C2 CONTROLLER DEVELOPMENT CLOSED.** Per this task's explicit rule: no
further search for ways to improve remaining Return success was performed
or is recommended. S1 eliminated, Solar pathology corrected, S4 corrected
and semantically decoupled -- all three proven architecture defects this
session identified are resolved and validated. Remaining Return failures
are classified as legitimate experimental outcomes (energy, time horizon,
local obstacle complexity), not controller defects.

## R. Freeze recommendation

No active regression failure. No unexplained engineering-invalid run. No
known pathological controller limit cycle. WM/obstacle semantic coupling
removed and proven (FREEZE-1, byte-identical trajectories). C1/C2 feature
isolation intact and verified. Home/RSSI architecture intact (RSSI
navigation use = 0, confirmed across HOME/RF/PORT/S4 suites). All source
provenance documented (§P, hash table above).

---

**C2 PRE-FREEZE REVIEW: READY FOR FREEZE**
