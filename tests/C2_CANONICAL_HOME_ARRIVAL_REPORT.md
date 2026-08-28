**2026-08-27 addendum:** the RSSI scalar this report refers to (§G, §L,
Tests HOME-3/10/11/12) is now a dBm value from a NodeMCU ESP32 /
ESP32-WROOM-32 hardware-profile-driven model
(`ESP32NestBeaconModel`/`DevelopmentFreeSpacePathLossModel`), not the
0-1 unitless `IdealizedRSSILikeNestBeacon` referenced below. See
`docs/NEST_BEACON_HARDWARE_PROFILE.md`,
`docs/ESP32_WROOM32_RSSI_SIM_TO_REAL_MODEL.md`, and
`tests/validate_esp32_nest_beacon_rf.py` (Tests RF-1..RF-12). This
report's geometric/architectural findings (canonical predicate, per-Scout
origin, wall-safety verification method) are unaffected -- only the RSSI
value's units and source model changed.

# C2 — Canonical Home/Nest Arrival Semantics: Validation Report

Scope: common infrastructure (C1 + C2). Consolidates Boot confirmation and
Return arrival into one canonical predicate, clarifies per-Scout Home
Origin semantics, and audits the Nest region against real maze wall
geometry. Does **not** touch WM capacity/spacing/pruning, F3/F4 logic,
`skip_unreachable`, obstacle escape, Robot Energy, resource
locations/rates, `dt`, speed, ToF ranges, AIH, EM, or Exchange.

## A. Previous conflicting Home semantics

The prior Boot/Home Confirmation task (`tests/C2_BOOT_HOME_CONFIRMATION_REPORT.md`)
correctly separated NEST/HOME REGION, NEST BEACON, and DELIVERY/HOME
CONFIRMATION, but left two conflicts unresolved:

1. **Two different Home rules.** `_boot_home_check` used the wide
   `home_region_radius_m` (1.05 m); `_environment_nest_reached` (Return
   arrival) independently used a separate, much tighter
   `nest_delivery_radius_m` (0.12 m) and `return_home_signal_threshold`
   (0.85) — a duplicated, slightly different Home rule across two code
   paths, exactly what this task's instructions forbid.
2. **No formal proof the wide region was wall-safe.** `home_region_radius_m`
   was derived from Scout spawn geometry only, with no check against the
   actual maze wall layout in `config/robot_world.yaml`.

Per-Scout local origin semantics were **not** actually conflicting —
`CycleWorkingMemory.start_cycle()` has never taken a world-pose argument;
it always resets the local frame to `(0,0,0)`, so each Scout's own current
physical pose has always implicitly been its own local origin. This
report's job here was to verify and document that, not to change it.

## B. Canonical NestRegion definition

**Audit finding (§H below): no dedicated, walled Nest chamber exists in
`config/robot_world.yaml`.** The Scout start row (x: 1.00–3.35, y: 1.00)
sits in an alcove bounded by the arena's west wall (x=0), south wall
(y=0), and a wall segment at y≈2 spanning x:[0,4] — but that alcove is
**open** on its east side (no wall closes x≈4 for y∈[0,2]); it connects
directly into the regular maze grid like any other cell. There is no
documented physical Nest enclosure (walls, doorway, mat) anywhere in this
repository.

Per the Stop Rule's explicit allowance ("if not specified, represent the
current region explicitly as DEVELOPMENT/PROVISIONAL geometry; do not
silently freeze it as research-final"), the canonical NestRegion used here
remains the same **provisional circle** from the prior task —
`home_region_radius_m = 1.05 m` centered at the environment-owned centroid
`(1.80, 1.00)` for the 3-Scout layout — but is now:
- **verified** against the real wall geometry (§H), not merely asserted, and
- **explicitly documented as non-final** (`docs/COMMON_NEST_INITIALIZATION_DESIGN.md` §8).

This is not the "STOP and report a missing geometry parameter" case,
because a valid (wall-safe, for the current maze) provisional region *can*
be constructed and was verified — but it is also not a final research Nest
shape. A future physical Nest enclosure design (walls, doorway) would
require re-deriving this region and re-running the §H verification.

## C. Whether the 0.12 m delivery radius remains, and why

**It does not remain as an arrival rule.** Audit of every use of
`nest_delivery_radius_m` in `src/swarm_simulate/swarm_baseline.py` found
exactly one call site (`_environment_nest_reached`) and no separate
physical operation elsewhere (no docking arm, no charging contact
simulation, nothing else reads this constant). Per the user's explicit
confirmation ("There is NO requirement that every Scout return to one tiny
docking point"), Return arrival now uses the same canonical
`_environment_home_confirmed` predicate as Boot (region radius 1.05 m).
`self.nest_delivery_radius_m = 0.12` is kept **defined but unused** in
`__init__`, clearly commented as historical, solely so any external
reference to the attribute name does not break.

## D. Boot confirmation rule

Unchanged from the prior task, now implemented via the renamed canonical
method `_environment_home_confirmed(pose)`:
`SCOUT_BOOT → HOME_RSSI_SAMPLE → HOME_PHYSICAL_REGION_CHECK → HOME_CONFIRMED`,
fail-fast `RuntimeError("INVALID_INITIAL_HOME_STATE: ...")` if either
check fails. WM `start_cycle()` (C2 only) fires strictly after
`HOME_CONFIRMED` (Test HOME-6, re-verified).

## E. Scout-local origin semantics

`CycleWorkingMemory.start_cycle(cycle_id)` takes **only** a `cycle_id` —
never a world pose. It unconditionally resets the local frame to
`(0, 0, 0)`. Therefore, by construction:
- Each Scout's own current physical pose at `start_cycle()` time becomes
  its own local origin.
- Different Scouts' local origins are never transformed onto one shared
  global coordinate.
- A Scout's origin can (and, for Scout0/Scout2 in the 3-Scout layout,
  does) differ from another Scout's origin, and from the Nest beacon
  center — this is correct, intended behavior (Test HOME-8).

No source change was needed for this — it was already correct; this
report formalizes and regression-tests it.

## F. Return navigation authority

Unchanged and re-verified (Test HOME-13): `_command_for`'s `RETURN_HOME`
branch has exactly one exit condition (`_environment_nest_reached`, i.e.
the canonical predicate) and exactly one movement fallback
(`_return_command`, WM retrace + local ToF safety). Neither `_return_command`
nor `_explore_command` references `_nest_beacon` (Test HOME-4). RSSI never
replaces WM navigation; it only ends the `RETURN_HOME` phase once it (and
physical containment) both pass.

## G. Final Home arrival predicate

```
HOME_CONFIRMED = PHYSICALLY_INSIDE_HOME_REGION AND RSSI >= HOME_SIGNAL_THRESHOLD
```

One method, `_environment_home_confirmed(pose) -> (home_confirmed, rssi, physical_region_ok)`,
implements this and is reused verbatim by:
- Boot confirmation (`.run()`'s pre-loop sequence)
- Return arrival (`_environment_nest_reached`, which now simply returns
  `_environment_home_confirmed(pose)[0]`)
- Depleted-at-Nest restoration (`_depleted_scout_can_be_restored`, via its
  existing call to `_environment_nest_reached`)

Both conditions are independently required — proven directly (not merely
by construction) in Tests HOME-3, HOME-10, HOME-11.

## H. Wall/adjacent-corridor safety result

Rigorous check: for every free (non-wall, non-arena-boundary) point within
`home_region_radius_m` (1.05 m) of the Nest center `(1.80, 1.00)`, sample
200 points along the straight line back to the Nest center and check each
against every wall rectangle in `config/robot_world.yaml` (expanded by
`_ROBOT_RADIUS_M` for robot-body clearance, matching the actual collision
geometry).

- Points checked: 1,045 (0.05 m grid over the circle's bounding box)
- Line-of-sight-blocked (genuine wall-separation) points found: **0**

**Result: for the current maze and current provisional radius, no
reachable point requires crossing a wall to reach the Nest center in a
straight line.** This is empirical evidence for this specific maze, not a
general proof (documented as such in
`docs/COMMON_NEST_INITIALIZATION_DESIGN.md` §8).

Because the idealized beacon's RSSI is a strictly monotonic function of
Euclidean distance and `home_signal_threshold` was derived exactly at the
1.05 m boundary, "RSSI >= threshold" is mathematically equivalent to
"distance <= 1.05 m" for this beacon model — so no point within the current
maze can naturally exhibit "high RSSI but wall-separated." **Test HOME-12**
therefore uses a real, verified wall-separated position (in the corridor
immediately north of the wall segment at `(2.00, 2.00)` in
`config/robot_world.yaml`) together with an artificially generous beacon
that forces a passing RSSI reading there — directly proving the code's
`AND` enforcement defends against "Home through a wall" even though the
attack does not currently occur naturally in this maze. Both the natural
(§H) and adversarial (HOME-12) checks were performed; both confirm no
false Home confirmation is possible.

*(Investigation note: an initial flood-fill reachability script produced
82 apparent "false positives"; direct re-verification via straight
line-of-sight sampling — reported above — showed these were a
floating-point grid-alignment bug in that script, not a real finding. The
line-of-sight method is simpler, has no such bug class, and is reported
here as the trusted result.)*

## I. Different-Scout-origin validation

Test HOME-8, PASS: for `scout_count` ∈ {2, 3, 4}, every configured Scout's
`CycleWorkingMemory.start_cycle(1)` produces local `(0,0,0)`, while the
Scouts' world start positions are pairwise distinct.

## J. Return-at-different-Nest-point validation

Test HOME-9, PASS: a Scout with cycle origin at Scout1's world position
`(1.8, 1.0)` reaching the Home region instead at a different point
`(2.2, 1.3)` (≠ origin, still inside `home_region_radius_m`, RSSI passing)
is confirmed `NEST_REACHED = True`.

## K. Cycle 2+ origin behavior

Test HOME-15, PASS: the Cycle 2+ call site
(`memory.start_cycle(scout.cycle_id)` inside the `DELIVER` block) passes
only `cycle_id`, never a world coordinate. Behaviorally: a WM that
accumulated real Cycle-1 motion resets its local frame to a fresh
`(0,0,0)` at Cycle 2, independent of where Cycle 1 ended, the boot origin,
the Nest centroid, or any other Scout's origin.

## L. RSSI source audit

Every read of `_nest_beacon`, `.sample(`, `home_signal_threshold`,
`nest_delivery_radius_m`, Nest center/region in
`src/swarm_simulate/swarm_baseline.py`, classified:

| Location | Classification |
| --- | --- |
| `IdealizedRSSILikeNestBeacon` construction (`__init__`) | ENVIRONMENT_VALIDATION |
| `home_region_radius_m` / `home_signal_threshold` derivation (`__init__`) | ENVIRONMENT_VALIDATION |
| `_environment_home_confirmed` definition | ENVIRONMENT_VALIDATION (canonical predicate) |
| `_environment_home_confirmed` call in `.run()` pre-loop | BOOT_CONFIRMATION |
| `_environment_home_confirmed` call in `_environment_nest_reached` | RETURN_CONFIRMATION |
| `_environment_nest_reached` call in `_depleted_scout_can_be_restored` | RETURN_CONFIRMATION (restoration reuses arrival rule) |
| Event-writer f-strings (`rssi=...`, `threshold=...`, `home_region_radius_m=...`) | LOGGING |
| `nest_delivery_radius_m = 0.12` (defined, unused) | LOGGING/historical only (not read by any confirmation or navigation path) |

**NAVIGATION uses of RSSI: 0** — confirmed exhaustively; no occurrence of
`_nest_beacon` or `.sample(` exists inside `_return_command`,
`_explore_command`, `_continue_turn`, `_obstacle_escape_command`, or any
other movement-command method (Tests HOME-4, HOME-13).

## M. Test HOME-1 through HOME-15

All 15 PASS (`tests/validate_c2_boot_home_confirmation.py`):

```
PASS Test HOME-1: every configured Scout start passes Boot/Home confirmation
PASS Test HOME-2: a Scout outside the Home region does not receive a false Home origin
PASS Test HOME-3: physical-region-OK alone is not sufficient -- RSSI confirmation is independently required
PASS Test HOME-4: RSSI is confirmation-only in both Boot/Home and Return/DELIVER checks; no navigation command method reads the beacon
PASS Test HOME-5: C1 and C2 share an identical Nest definition, Scout start positions, and Home confirmation rule
PASS Test HOME-6: event ordering is SCOUT_BOOT -> HOME checks -> HOME_CONFIRMED -> WM start -> EXPLORE, never reversed
PASS Test HOME-7: all configured Scout start layouts (2-4 Scouts) are physically valid and collision-free
PASS Test HOME-8: every Scout's local Home origin is its own (0,0,0); world positions legitimately differ
PASS Test HOME-9: NEST_REACHED does not require returning to the exact cycle-origin point
PASS Test HOME-10: RSSI passing alone (physical region failing) never yields HOME_CONFIRMED
PASS Test HOME-11: physical Home-region membership alone (RSSI failing) never yields HOME_CONFIRMED
PASS Test HOME-12: a wall-separated pose with a forced strong RSSI reading is still rejected (no 'Home through a wall')
PASS Test HOME-13: during RETURN_HOME, movement comes only from WM retrace/local-safety; the phase transition happens only through the canonical Home/Nest arrival check, never RSSI directly
PASS Test HOME-14: Boot confirmation and Return arrival use the identical canonical Home predicate
PASS Test HOME-15: each new cycle's local origin is freshly (0,0,0) at the Scout's current position, independent of prior-cycle, boot, centroid, or other-Scout origins
```

## N. Acceptance/regression results

| Suite | Result |
| --- | --- |
| `tests/validate_c2_boot_home_confirmation.py` (HOME-1..15) | **PASS** (15/15) |
| `tests/validate_c2_working_memory.py` (Acceptance A-J) | **PASS** |
| `tests/validate_c2_return_correction.py` (F3/F4, Tests M-Q) | **PASS** (5/5) |
| `tests/validate_condition_isolation.py` | **PASS** |
| `tests/validate_rssi_monotonicity.py` | **PASS** |
| `tests/validate_rssi_state_reset.py` | **PASS** |
| `tests/validate_persistent_stationary_turn_deadlock.py` | **PASS** |
| `tests/validate_baseline_termination_architecture.py` | **PASS (was FAIL before this task — see §O)** |
| `tests/validate_c1_all_depleted_termination.py` | **PASS (was FAIL before this task — see §O)** |
| `tests/validate_c1_energy_accounting.py` | **PASS (was FAIL before this task — see §O)** |
| `tests/validate_c1_rssi_boundaries.py` | **FAIL — see §O (two independent causes)** |
| `tests/validate_physical_scale_geometry.py` | **FAIL — pre-existing, unrelated (confirmed via `git stash` at prior task)** |
| `tests/validate_physical_scale_motion.py` | **FAIL — pre-existing, unrelated (confirmed via `git stash` at prior task)** |

60 s deterministic C1/C2 smoke comparison (seed `2118334751`,
`FAST_HEADLESS_RESEARCH_MODE=1`): both `EXIT:0`. Event sequence identical
for both modes through `SCOUT_START`: `SCOUT_BOOT → HOME_RSSI_SAMPLE
(rssi=0.714286/1.000000; threshold=0.655738) → HOME_PHYSICAL_REGION_CHECK
(home_region_radius_m=1.050000) → HOME_CONFIRMED → SCOUT_START`. C2's
`working_memory_events.csv` shows `WM_RESET` at `sim_time_s=0.0`,
`cycle_id=1`, strictly after `HOME_CONFIRMED` in the C2 log. No
`NEST_REACHED` occurred in either 60 s run (resource too far for this
short horizon) — arrival behavior is instead verified end-to-end by the
now-passing termination/energy-accounting fixtures (§O).

## O. C1 historical fixture disposition

Three fixtures — **all now PASS**, having FAILED after the prior Boot/Home
task and before this one:

- `tests/validate_baseline_termination_architecture.py`
- `tests/validate_c1_all_depleted_termination.py`
- `tests/validate_c1_energy_accounting.py`

**Classification: A — stale fixture assumption, now resolved by the
corrected architecture itself (no fixture edit was needed).** All three
place a resource endpoint or rely on Nest-adjacency at world `(1.0, 1.0)`,
0.8 m from the environment-owned Nest centroid `(1.8, 1.0)`. Under the
prior task's tight `nest_delivery_radius_m=0.12` arrival rule, that 0.8 m
gap made these fixtures fail (their short time/energy budgets assumed
near-zero Nest-to-resource distance). This task's canonical arrival rule
widens the confirmation region to `home_region_radius_m=1.05 m`, which
comfortably contains that 0.8 m gap again — so these fixtures now PASS
**without modification**, and without reverting the corrected Nest-center
geometry. Their scientific intent (mission termination architecture,
all-depleted/recharge semantics, delivery/withdrawal accounting) is
unchanged and unaffected.

One fixture remains failing, for **two distinct reasons**, one pre-existing
and one newly introduced by this task's consolidation:

- `tests/validate_c1_rssi_boundaries.py` — **Classification: A, not yet
  updated (out of this task's scope).**
  1. **Pre-existing (confirmed via `git stash` at HEAD before this
     session's Boot/Home work began):** its AST check forbids the
     attribute names `x_m`/`y_m` anywhere in `_return_command`; the F3
     route-reacquisition correction (an earlier, separate task) added
     `memory.x_m`/`memory.y_m` (local-odometric progress tracking) there.
     Unrelated to Boot/Home or canonical-arrival work; `_return_command`
     was not touched by either task.
  2. **New, caused by this task's consolidation:** the same test also
     asserts the literal strings `"physical_entry"` and `".sample("`
     appear inside `_environment_nest_reached`'s source. Consolidating
     Boot and Return onto one canonical `_environment_home_confirmed`
     helper (exactly what this task's instructions required — "do not
     duplicate slightly different Home rules across code paths") means
     `_environment_nest_reached` now delegates instead of containing
     those literals inline. This is the intended, disclosed shape of the
     refactor, not a behavioral regression: `_environment_nest_reached`
     still performs the identical physical-entry-and-RSSI check, just via
     one shared method instead of a private reimplementation.

  Neither cause was fixed in this session (`_return_command` and this
  static fixture are both out of this task's explicit scope); both are
  flagged here for the user's decision, consistent with C1's frozen-control
  status.

No new failures were introduced in any other previously-passing test.

## P. Files modified

- `src/swarm_simulate/swarm_baseline.py`: renamed `_boot_home_check` →
  `_environment_home_confirmed`; `_environment_nest_reached` now delegates
  to it instead of an independent `nest_delivery_radius_m`/
  `return_home_signal_threshold` check; `nest_delivery_radius_m` kept
  defined but unused, clearly commented historical;
  `return_home_signal_threshold` attribute removed (fully superseded by
  `home_signal_threshold`, used identically for both Boot and Return);
  updated `NEST_REACHED` event detail string; updated docstrings/comments.
- `tests/validate_c2_boot_home_confirmation.py`: renamed method references;
  added `_code_only()` helper (strips docstrings before forbidden-token
  audits, fixing a false-positive from HOME-4's own new docstring text);
  added Tests HOME-8 through HOME-15.
- New: `tests/C2_CANONICAL_HOME_ARRIVAL_REPORT.md` (this file).
- Updated: `docs/COMMON_NEST_INITIALIZATION_DESIGN.md` (§8, provisional
  status + wall-safety verification), `docs/C2_WORKING_MEMORY_DESIGN.md`
  (canonical wording block, Boot/Home section), `tests/C2_BOOT_HOME_CONFIRMATION_REPORT.md`
  (addendum pointing to this report).
- No changes to `c2_working_memory.py`, `_return_command`,
  `_explore_command`, WM capacity/spacing/pruning, energy, resources, ToF,
  AIH, EM, or Exchange.

## Q. Remaining obstacle-return issue

Unchanged, not investigated or touched in this task (explicitly out of
scope): the recurring local obstacle-avoidance/WM-retrace conflict
documented in `tests/C2_SECONDARY_RETURN_DIAGNOSIS.md` (6 of 9
corrected-run failures, `NO_EFFECT` in 71% of traced route-reacquisition
events) remains open. The Return-arrival widening in this task (§C/§O)
changes how *easily* a Scout that reaches the Home region is confirmed
`NEST_REACHED`; it does not change whether a Scout stuck at a physical
choke point can reach the Home region at all. A fresh DEV01-03-style rerun
(not performed here, per the Stop Rule) would be needed to know whether the
combination of the F3/F4 correction, the corrected Nest geometry, and this
widened arrival rule together change the Nest-reach rate reported in
`tests/C2_SECONDARY_RETURN_DIAGNOSIS.md` (2/16) — plausible, given how much
larger the confirmation region now is, but not yet measured.

## R. Freeze recommendation

**Do not Freeze.** This task's own deliverable (canonical Home/Nest
arrival semantics) is complete, tested (15/15 new tests, full regression
battery passing except two disclosed, pre-existing/out-of-scope fixture
issues), and resolved three previously-disclosed C1 fixture regressions as
a side effect. However, per the task's Stop Rule and this report's own
scope: R01-R20 have not been run, C3 has not started, and the separate,
still-open obstacle-return issue (§Q) has not been re-measured under the
new geometry — a freeze decision should wait for that remeasurement at
minimum.

---

**C2 CANONICAL HOME SEMANTICS: READY FOR NEXT REVIEW**
