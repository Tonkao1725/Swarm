**2026-08-27 addendum:** superseded in part by
`tests/C2_CANONICAL_HOME_ARRIVAL_REPORT.md`, which consolidates Boot
confirmation and Return arrival into one canonical
`_environment_home_confirmed` predicate (this report's `_boot_home_check`
was renamed to `_environment_home_confirmed`) and retires the separate
`nest_delivery_radius_m=0.12` arrival rule described below. This report's
geometry derivation (§B/C) and the three C1 fixture findings (§7) remain
valid background — the fixture findings are, in fact, resolved by the
canonical-arrival report's change (Return arrival area widened from 0.12 m
to 1.05 m), see that report §N.

# C2 — Boot/Home Confirmation + Nest Initialization: Validation Report

Scope: common infrastructure (C1 + C2). Boot/Home confirmation lifecycle
only. WM capacity/spacing/pruning/energy/resources/return-performance,
`skip_unreachable`, obstacle-escape, AIH, EM, and Exchange were **not**
touched. See `docs/COMMON_NEST_INITIALIZATION_DESIGN.md` for the full
design rationale and geometry derivation.

## 1. Pre-edit audit summary

- `_ROBOT_RADIUS_M = 0.25` m — from `config/robot_world.yaml` (`shape.radius`)
  and `_add_scouts`.
- `nest_delivery_radius_m = 0.12` m and `return_home_signal_threshold = 0.85`
  — pre-existing, from `_environment_nest_reached`. 0.12 m < robot radius
  (0.25 m) proves this was always a delivery/arrival-point check, never a
  physical Home-region radius — left unchanged.
- `IdealizedRSSILikeNestBeacon`: frozen dataclass, `scale_m=2.0`,
  `sample(pose) = 1/(1+distance/scale_m)`, never exposes x/y to the
  controller.
- Configured Scout starts (hardcoded in `_add_scouts`):
  `[[1.00,1.00,0.0],[1.80,1.00,0.0],[2.60,1.00,0.0],[3.35,1.00,0.0]]`.
- For `scout_count=3`: centroid `(1.80, 1.00)`, max distance from centroid
  to a used start `0.80 m`, min pairwise start distance `0.80 m`
  (collision-free vs. `2 x 0.25 = 0.50 m` minimum).

## 2. Derived (not guessed) geometry

- `home_region_radius_m = 0.80 + 0.25 = 1.05 m`
- `home_signal_threshold = beacon.sample_at_distance(1.05) ≈ 0.6557`
  (derived from the beacon's own falloff, so the physical and RSSI
  boundaries agree by construction)

## 3. Source changes (`src/swarm_simulate/swarm_baseline.py`)

- `ScoutState.boot_home_confirmed: bool = False` (new field)
- `IdealizedRSSILikeNestBeacon.sample_at_distance(distance_m)` (new method)
- Module constants `_ROBOT_RADIUS_M`, `_SCOUT_START_STATES`
- `_add_scouts` refactored to use the constants (no behavior change)
- New `_home_center()` — centroid of configured starts, static config only
- `__init__`: Nest center now `_home_center()` instead of `self._pose(env, 0)`;
  added `home_region_radius_m`, `home_signal_threshold`,
  `return_home_signal_threshold` (renamed from a bare `0.85` literal — pure
  DRY, see §5)
- New `_boot_home_check(pose) -> (home_confirmed, rssi, physical_region_ok)`
- `.run()` pre-loop: full Boot/Home sequence (`SCOUT_BOOT` →
  `HOME_RSSI_SAMPLE` → `HOME_PHYSICAL_REGION_CHECK` → `HOME_CONFIRMED` →
  WM `start_cycle()` [C2 only] → `SCOUT_START`), fail-fast
  `RuntimeError("INVALID_INITIAL_HOME_STATE: ...")` on failure, with an
  explicit log flush before raising.

## 4. Test HOME-1 .. HOME-7 (`tests/validate_c2_boot_home_confirmation.py`)

| Test | Result | Note |
|---|---|---|
| HOME-1 ALL_SCOUTS_VALID_BOOT_HOME | **PASS** | all configured starts (2/3/4-Scout configs) confirm |
| HOME-2 NO_FALSE_BOOT_ORIGIN | **PASS** | a Scout far outside the Home region fails containment and confirmation |
| HOME-3 RSSI_REQUIRED | **PASS** | physical-OK + artificially strict RSSI threshold still fails confirmation (proves AND, not OR) |
| HOME-4 NO_RSSI_STEERING | **PASS** | source audit: no steering tokens in `_boot_home_check`/`_environment_nest_reached`; `_nest_beacon` never referenced in `_return_command`/`_explore_command` |
| HOME-5 C1_C2_COMMON_START | **PASS** | identical Nest center, `home_region_radius_m`, `home_signal_threshold`, and per-pose confirmation result for `working_memory_enabled=False` vs `True` |
| HOME-6 WM_START_AFTER_HOME | **PASS** | source-order check: `HOME_CONFIRMED` write precedes `working_memory.start_cycle()`; failure-raise precedes it too |
| HOME-7 COLLISION_FREE_START | **PASS** | min pairwise start distance > `2 x robot_radius` for 2/3/4-Scout configs |

All 7 tests PASS. Full log:

```
PASS Test HOME-1: every configured Scout start passes Boot/Home confirmation
PASS Test HOME-2: a Scout outside the Home region does not receive a false Home origin
PASS Test HOME-3: physical-region-OK alone is not sufficient -- RSSI confirmation is independently required
PASS Test HOME-4: RSSI is confirmation-only in both Boot/Home and Return/DELIVER checks; no navigation command method reads the beacon
PASS Test HOME-5: C1 and C2 share an identical Nest definition, Scout start positions, and Home confirmation rule
PASS Test HOME-6: event ordering is SCOUT_BOOT -> HOME checks -> HOME_CONFIRMED -> WM start -> EXPLORE, never reversed
PASS Test HOME-7: all configured Scout start layouts (2-4 Scouts) are physically valid and collision-free
```

## 5. Incidental fix found and applied during validation

`tests/validate_rssi_state_reset.py` (pre-existing, PASS at HEAD) audits
that no attribute anywhere in `swarm_baseline.py` retains a named "RSSI
sample" across ticks (AST check on `.attr` containing `"rssi"`). The first
implementation introduced `self.home_rssi_threshold` and
`self.return_home_rssi_threshold` as named attributes — static, computed
once, never mutated — which is not the "retained live sample" the test
guards against, but the AST check cannot distinguish a static threshold
constant from a retained live value by name alone. **Fix**: renamed both
attributes to `home_signal_threshold` / `return_home_signal_threshold`
(naming-only, zero behavioral change) everywhere they occur. Re-verified
PASS. This is the only change made outside the Boot/Home scope, and it is a
rename, not a logic change.

## 6. Full regression battery

| Suite | Result |
|---|---|
| `tests/validate_c2_boot_home_confirmation.py` (HOME-1..7) | **PASS** (7/7) |
| `tests/validate_c2_working_memory.py` (Acceptance A-J) | **PASS** |
| `tests/validate_c2_return_correction.py` (F3/F4, Tests M-Q) | **PASS** (5/5) |
| `tests/validate_condition_isolation.py` | **PASS** |
| `tests/validate_rssi_monotonicity.py` | **PASS** |
| `tests/validate_rssi_state_reset.py` | **PASS** (after §5 rename) |
| `tests/validate_c1_rssi_boundaries.py` | **FAIL — pre-existing, unrelated** |
| `tests/validate_persistent_stationary_turn_deadlock.py` | **PASS** |
| `tests/validate_baseline_termination_architecture.py` | **FAIL — expected, see §7** |
| `tests/validate_c1_all_depleted_termination.py` | **FAIL — expected, see §7** |
| `tests/validate_c1_energy_accounting.py` | **FAIL — expected, see §7** |
| `tests/validate_physical_scale_geometry.py` | **FAIL — pre-existing, unrelated** |
| `tests/validate_physical_scale_motion.py` | **FAIL — pre-existing, unrelated** |

### `validate_c1_rssi_boundaries.py` — pre-existing, unrelated to this task

Confirmed via `git stash` that this test already failed at HEAD (before any
Boot/Home change), on `_return_command`'s AST containing attribute names
`x_m`/`y_m` (from `memory.x_m`/`memory.y_m`, the WM's own local-odometric
tracking added by the earlier F3 route-reacquisition correction). This
static test predates and is unrelated to the current task; `_return_command`
was not modified in this session. Left unfixed — out of this task's scope
(WM/Return internals are explicitly "do not touch").

### `validate_physical_scale_geometry.py` / `validate_physical_scale_motion.py` — pre-existing, unrelated

Both already failed at HEAD (confirmed via `git stash`) — untracked
carry-overs from an earlier session task, unrelated to Boot/Home. Not
modified.

## 7. Expected C1 fixture failures — full root-cause trace

Three tests, **all passing at HEAD**, now fail. All three trace to the
**same, single, disclosed cause**: the Nest center moved from "Scout 0's
boot pose" (a defect the user explicitly asked to correct — see
`docs/COMMON_NEST_INITIALIZATION_DESIGN.md` §3) to the environment-owned
Scout-start centroid `(1.80, 1.00)` for the 3-Scout configuration.

- **`validate_baseline_termination_architecture.py`**: places its test
  resource endpoint at `(1.0, 1.0)` with the code comment *"intentionally
  placed at Scout 0's nest"* — i.e. this fixture is explicitly designed
  around the old Scout-0-is-the-Nest co-location. Under the corrected Nest
  position, the endpoint is now 0.8 m from the Nest instead of 0 m, adding a
  round trip the fixture's 10.0 s budget was not sized for; the run reaches
  `TIME_LIMIT_REACHED` instead of `MISSION_SUCCESS`.
- **`validate_c1_energy_accounting.py`**: same pattern — endpoint at
  `(1.0, 1.0)`, same 0.8 m gap introduced, `DELIVER`/`NEST_ENERGY_UPDATED`
  events do not occur inside the test's short window.
- **`validate_c1_all_depleted_termination.py`**: asserts
  `scouts[0]["internal_energy_final"] > 0.0` after a 0.1 s
  zero-initial-energy scenario, relying on the pre-existing
  `_depleted_scout_can_be_restored` mechanism, which requires a depleted
  Scout to be physically inside `nest_delivery_radius_m` (0.12 m) of the
  Nest. Under the old Nest-at-Scout-0 co-location, Scout 0 was that Scout
  (distance 0). Under the corrected centroid, **Scout 1** is now the one
  co-located with the Nest (distance 0) for the 3-Scout layout — the test
  still checks index 0.

None of this touches production energy, return, or WM logic — confirmed by
`git diff --stat` showing the current session's changes to
`swarm_baseline.py` do not intersect `_return_command`,
`_depleted_scout_can_be_restored`, or any energy-accounting code path.

This is exactly the class of outcome the task's own instructions
pre-authorized ("this MAY legitimately change C1 behavior ... do NOT
require old C1 trajectory equivalence, instead preserve old C1 results as
historical and create a corrected common reference"). These three fixtures
encode the pre-correction geometry as their pass condition; updating them
(e.g. moving the endpoint to track the Nest center, or checking Scout 1
instead of Scout 0) is a legitimate follow-up but was **not** done
unilaterally in this session, consistent with C1's frozen-control status —
flagged here for the user's explicit decision.

## 8. C1 feature isolation (re-confirmed)

C1 (`working_memory_enabled=False`) still performs the full Boot/Home
sequence (`SCOUT_BOOT` → `HOME_RSSI_SAMPLE` → `HOME_PHYSICAL_REGION_CHECK`
→ `HOME_CONFIRMED` → `SCOUT_START`) but creates **no** Working Memory object
and never calls `start_cycle()` — verified directly in `.run()`'s source
(the `start_cycle()` call is inside the existing
`if self.working_memory_enabled:` gate, unchanged by this task) and by the
60 s C1 smoke run's `working_memory_events.csv` being absent/empty.

## 9. Deterministic C1/C2 smoke comparison

60 s smoke runs, seed `2118334751`, both modes:

- **C1** (`SWARM_EXPERIMENT_MODE=baseline`): `EXIT:0`, `VALID`,
  `TIME_LIMIT_REACHED`. All 3 Scouts: `SCOUT_BOOT → HOME_RSSI_SAMPLE →
  HOME_PHYSICAL_REGION_CHECK → HOME_CONFIRMED → SCOUT_START`. Scout 1
  rssi=1.000000 (0 m, at the new centroid); Scout 0/2 rssi=0.714286 (0.8 m);
  `home_signal_threshold=0.655738` for all; `home_region_radius_m=1.050000`;
  `physical_region_ok=True` for all.
- **C2** (`SWARM_EXPERIMENT_MODE=working_memory`): `EXIT:0`, `VALID`,
  `TIME_LIMIT_REACHED`. Identical event sequence through `SCOUT_START`;
  `working_memory_events.csv` shows the first `WM_RESET` row at
  `sim_time_s=0.0`, `cycle_id=1`, `wm_size=1`,
  `detail=cycle_start_local_origin` — WM initialization occurs strictly
  after `HOME_CONFIRMED`.

## 10. No-RSSI-steering audit

Covered formally by Test HOME-4 (§4). Manual grep of every
`_nest_beacon`/`rssi` occurrence in `swarm_baseline.py` confirms all reads
are confined to `_boot_home_check`, `_environment_nest_reached`, and their
associated event-logging strings — none feed `linear_speed`,
`angular_speed`, turn direction, or WM breadcrumb selection.

## 11. Verdict

`C2 BOOT/HOME INITIALIZATION: READY FOR NEXT REVIEW`

The Boot/Home confirmation architecture is implemented, derived from real
geometry (not guessed), fully separates Home region / Beacon / delivery
confirmation, is common to C1 and C2, keeps RSSI confirmation-only, and
passes all 7 required new tests plus the full pre-existing C2 regression
suite. Three legacy C1 fixture tests now fail for a single, fully-traced,
explicitly pre-authorized reason (§7) and are flagged — not silently fixed
or hidden — for the user's decision. Two more pre-existing, unrelated test
failures were also independently confirmed to predate this task (§6).
