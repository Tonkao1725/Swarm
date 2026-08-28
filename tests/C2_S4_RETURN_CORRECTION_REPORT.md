# C2 S4 Return Limit-Cycle — Minimal Controller Correction Report

Date: 2026-08-28. Root cause:
`tests/C2_S4_RETURN_LIMIT_CYCLE_DIAGNOSIS.md`. Scope: `_return_command`'s
obstacle-escape/WM re-arbitration boundary only. No change to
`skip_unreachable`, WM storage semantics (`maximum_entries`, `spacing_m`,
origin protection, LIFO retrace, pruning, cycle reset), Home/RSSI
architecture, or `_explore_command`/Solar behavior.

## Source safety

| File | Before this task | After | Status |
| --- | --- | --- | --- |
| `src/swarm_simulate/swarm_baseline.py` | `2bfbfc05...4032ad0f` | `97fac7b2...098e469b` | **changed (this task's only edit)** |
| `src/swarm_simulate/c2_working_memory.py` | `b9a25db8...f478b48d` | `b9a25db8...f478b48d` | **unchanged, verified** |
| `src/swarm_simulate/home_observation.py` | `1aa9093d...cd20e4` | `1aa9093d...cd20e4` | **unchanged, verified** |
| `src/swarm_simulate/energy_sensor.py` | `608befe4...43ea3d3e1` | `608befe4...43ea3d3e1` | **unchanged, verified** |

## Minimal correction

New `ScoutState` fields (current-actuator-maneuver state, same kind as
existing `escape_direction`/`wm_target_lock_x_m`):

```python
return_obstacle_escape_active: bool = False
return_obstacle_escape_start_x_m: float = 0.0
return_obstacle_escape_start_y_m: float = 0.0
return_obstacle_escape_attempts: int = 0
```

`_return_command`, inside the `working_memory_enabled` block:

1. **Entry** (replacing the old fall-through to generic C1 branches):
   when the WM target's heading is already correct but
   `_forward_body_clearance_safe` fails, mark
   `return_obstacle_escape_active = True`, record the local-frame start
   position (`memory.x_m, memory.y_m`), and launch the escape via the
   **existing, unmodified** `_begin_clear_side_turn` (same mechanism the
   generic C1 branches already used).
2. **While active**: before WM heading is read at all, check accumulated
   displacement from the recorded start position. If `< memory.spacing_m`
   (0.25 m -- the same constant already used elsewhere as "meaningful WM
   progress," reused symmetrically here as "meaningful escape progress"),
   re-launch another bounded escape attempt via
   `_begin_clear_side_turn` and increment `return_obstacle_escape_attempts`
   -- WM heading is **not** re-arbitrated this tick.
3. **Exit**: once displacement reaches `memory.spacing_m`, **or**
   `return_obstacle_escape_attempts` reaches `self.escape_turn_limit`
   (8 -- the same existing constant `_obstacle_escape_command` already
   uses for its own bounded-retry ceiling) without enough displacement,
   clear the escape state and resume normal WM arbitration on the **same**
   target (never skipped by this mechanism).

**Physical derivation of the bound (§F)**: no new constant was invented.
`memory.spacing_m` (0.25 m) is the existing WM breadcrumb-spacing
constant, already the system's own definition of "one unit of meaningful
local movement" (used identically for outbound breadcrumb recording and
for the pre-existing F3 stuck-tick progress check). Requiring the same
distance to exit a committed escape is a direct, symmetric reuse, not a
new tuned value. `escape_turn_limit` (8) is the existing bound already
governing `_obstacle_escape_command`'s own internal turn-retry ceiling
before it falls back to the existing back-off/recovery sequence -- reusing
it here bounds "how many separate escape attempts before giving up and
letting the existing 144-tick `wm_stuck_ticks`/`skip_unreachable` bound
operate" without inventing a second timeout.

## Temporary state introduced (§G)

Exactly four scalar fields, all cleared on exit (escape success, WM pop,
or bound exhaustion): a boolean flag, one local-frame `(x, y)` start
position, and an attempt counter. None stores an obstacle identity, a
map cell, a route, or cross-cycle/cross-trip information -- identical in
kind to the pre-existing `escape_direction`/`wm_target_lock_x_m` fields.

## Same-target retry behavior (§H)

Confirmed structurally and by test (S4-4): the committed-escape mechanism
never calls `memory.skip_unreachable` or `memory.pop_if_reached` itself --
it only gates *when* the existing heading/forward-arbitration code below
it may run. The active target (`memory.entries[-1]`) is therefore
mechanically unchanged across an escape episode; once the escape resolves
(success or bound exhaustion), the very next WM read returns the same
target it was already pursuing.

## WM stuck/progress accounting behavior (§I)

**Principled distinction implemented**: `wm_stuck_ticks` is only
incremented inside the pre-existing `wm_target_lock`/no-progress block,
which is only reached when `return_obstacle_escape_active` is `False`.
While a committed escape is active, ticks never reach that block at all
(mirroring exactly how `turn_remaining_rad`/`escape_direction` already
bypass it) -- so escape ticks are structurally never counted as "WM
attempted this target and made no progress." This is not an arbitrary
pause/reset of the counter; it is the same bypass pattern the codebase
already used for every other in-flight actuator maneuver. The outer
144-tick `wm_stuck_ticks`/`skip_unreachable` bound remains fully intact
and reachable as the ultimate fallback (Test S4-5) once the escape's own
bounded retry (`escape_turn_limit`) is exhausted without success.

## J. Tests S4-1 through S4-14

All 14 PASS (`tests/validate_c2_s4_return_correction.py`, which also
embeds and reruns SOLAR-1..10 as Test S4-10):

```
PASS Test S4-1: the original blocked-forward-toward-WM-target condition is reproduced deterministically and now enters the committed escape gate
PASS Test S4-2: an in-progress committed escape is not overwritten by fresh WM heading arbitration
PASS Test S4-3: escape completion requires an actual measured displacement of at least one breadcrumb-spacing, not merely command-tick expiration
PASS Test S4-4: after a successful escape, the same WM breadcrumb is retried first -- never auto-deleted
PASS Test S4-5: existing skip_unreachable fallback logic is untouched and reachable
PASS Test S4-6: the final current-cycle origin remains protected exactly as before (unchanged c2_working_memory.py)
PASS Test S4-7: no map, A*, Dijkstra, Nest vector, world waypoint, or resource coordinate was introduced
PASS Test S4-8: RSSI navigation use count remains zero in _return_command
PASS Test S4-9: the S4 correction is gated inside working_memory_enabled -- C1 gains no WM/Return-route state
PASS Test S4-10: the previously corrected SOLAR_TURN Explore behavior remains valid (SOLAR-1..10 all pass)
PASS Test S4-11: replaying the adversarial blocked-then-clearing geometry, the Scout accumulates real displacement (no permanent same-pocket lock)
PASS Test S4-12: committed escape suppresses route-reacquisition/stuck-tick accounting until it resolves
PASS Test S4-13: with no obstacle conflict, normal WM_RETRACE_FORWARD behavior is unchanged
PASS Test S4-14: no forward movement is authorized through unsafe ToF geometry
```

## K. SOLAR regression

10/10 pass, both standalone (`tests/validate_solar_turn_explore_deadlock.py`)
and embedded (Test S4-10) -- `_explore_command` was not touched by this task.

## L. HOME/PORT/RF regression

| Suite | Result |
| --- | --- |
| HOME-1..15 | **PASS** (15/15) |
| PORT-1..12 | **PASS** (12/12) |
| RF-1..12 | **PASS** (12/12) |
| C2 Acceptance A-J | **PASS** |
| F3/F4 Tests M-Q | **PASS** |
| Condition isolation | **PASS** |
| RSSI monotonicity / state reset | **PASS** |
| Persistent stationary-turn deadlock | **PASS** |
| Baseline termination architecture | **PASS** |
| C1 all-depleted termination | **PASS** |
| C1 energy accounting | **PASS** |
| `validate_c1_rssi_boundaries.py` | **FAIL -- pre-existing, unrelated** (same single cause reported in every prior task this session) |

## M. C1 isolation

Verified structurally (Test S4-9): the entire committed-escape mechanism
lives inside `if self.working_memory_enabled and memory is not None:` --
with WM disabled, this code is unreachable, and no new field is ever read
or written outside that guard. C1 gains no WM or Return-route state.

## N-P. DEV01 / DEV02 / DEV03 results (3600 s, identical config to prior stages)

All three: `exit=0; engineering=COMPLETED; mission=TIME_LIMIT_REACHED`.

| Run | `experimental_validity` | Deliveries (S0/S1/S2) | `persistent_stationary_turn_deadlock` (any Scout) |
| --- | --- | --- | --- |
| DEV01 | **VALID** | 0 / 0 / 2 | False (all) |
| DEV02 | **VALID** | 4 / 4 / 1 | False (all) |
| DEV03 | **VALID** | 2 / 1 / 0 | False (all) |

No new engineering-invalid behavior appeared (per the Stop Rule -- no STOP
condition triggered).

## Q. Aggregate Return funnel

| | Attempts | NEST_REACHED |
| --- | ---: | ---: |
| DEV01 | 4 | 2 |
| DEV02 | 10 | 9 |
| DEV03 | 6 | 3 |
| **Total** | **20** | **14 (70%)** |

S1 (`INVALID_CYCLE_ORIGIN`) recurrence: **0/9** Scout-runs (unchanged,
unaffected by this task).

## R. Remaining failed Returns (6 of 20)

Full table: `tests/C2_S4_RETURN_EPISODES.csv`.

| DEV | Scout | Duration (s) | Skip count | Primary cause |
| --- | --- | ---: | ---: | --- |
| DEV01 | 0 | 2586.8 | 0 | A_ENERGY_DEPLETION |
| DEV01 | 1 | 2208.3 | 2 (both LEGITIMATE/UNKNOWN) | A_ENERGY_DEPLETION |
| DEV02 | 2 | 2782.0 | 0 | A_ENERGY_DEPLETION |
| DEV03 | 0 | 2692.4 | 2 (both LEGITIMATE/UNKNOWN) | C_TIME_HORIZON |
| DEV03 | 1 | 2060.7 | 5 (1 NO_EFFECT, rest LEGITIMATE/EFFECTIVE) | F_LEGITIMATE_LOCAL_OBSTACLE_COMPLEXITY (+ C_TIME_HORIZON) |
| DEV03 | 2 | 2898.6 | 0 | A_ENERGY_DEPLETION |

**Root-cause distribution: A_ENERGY_DEPLETION=4, C_TIME_HORIZON=1,
F_LEGITIMATE_LOCAL_OBSTACLE_COMPLEXITY=1. CONTROLLER_LIMIT_CYCLE = 0.
ENGINEERING_FAILURE = 0. UNRESOLVED = 0.**

Per instruction, `F_LEGITIMATE_LOCAL_OBSTACLE_COMPLEXITY` was assigned
only where the trace shows real spatial variation across distinct
physical situations (DEV03 Scout1: pre-skip bounding boxes of 15.9, 0.59,
0.26, 0.30 m -- clearly different local geometries, not a repeating fixed
pocket), not merely because a Return happened to fail.

## S. Limit-cycle recurrence

**Zero.** No episode among the 6 failures resembles the DEV02-Scout1
mechanism (2076.7 s / 0.02-0.13 m / 12x consecutive `NO_EFFECT`). The
independent turning-without-moving detector (identical methodology to
`tests/C2_POST_ARCHITECTURE_LIMIT_CYCLES.csv`, >=144 consecutive ticks of
`angular_velocity != 0` with `moved_m < 1e-7`) found **0 qualifying
windows** across all 9 Scout-runs (was 1, DEV01 Scout0's SOLAR pathology,
already separately corrected; the S4-specific DEV02-Scout1-style pattern
was never based on this exact detector to begin with -- see the
reacquisition-classification comparison below, which is the direct
measure).

## T. Reacquisition effectiveness

| Classification | Stage 2 (pre-S4) | Stage 3 (post-S4) |
| --- | ---: | ---: |
| Total reacquisition events | 65 | **14** |
| NO_EFFECT | 36 (55%) | **1 (7%)** |
| LEGITIMATE_ROUTE_ADVANCE | 15 (23%) | 6 (43%) |
| EFFECTIVE_ESCAPE | 7 (11%) | 2 (14%) |
| UNKNOWN (no post-skip window) | 7 (11%) | 5 (36%) |

The mechanism changed as intended: far fewer reacquisitions occur at all
(most obstacle conflicts are now resolved by the committed escape *before*
the 144-tick stuck bound is ever reached), and among the reacquisitions
that still occur, `NO_EFFECT` collapsed from the dominant outcome (55%) to
a rare one (7%, a single event). No target percentage was required or
targeted -- this is the observed, unforced outcome.

## U. PREMATURE_SKIP result

**0** (all 14 current-run skip events checked; every one either shows a
large pre-skip bounding box collapsing to a small one -- consistent with
genuine approach followed by a bound stuck-tick expiration -- or is
`UNKNOWN` for lack of a post-skip window). Unchanged from Stage 2's `0`,
confirming `skip_unreachable`'s own trigger logic remains correctly
calibrated and was correctly left unmodified.

## V. Engineering validity

All three reruns: `exit=0`, `engineering=COMPLETED`,
`experimental_validity=VALID`. No crash, NaN, invalid sensor state,
`CONTACT_STALLED`, or persistent-stationary-turn-deadlock flag anywhere.
The previously fixed Explore Solar pathology did not recur (confirmed
directly: `persistent_stationary_turn_deadlock=False` for all 9
Scout-runs).

## W. Files modified

- `src/swarm_simulate/swarm_baseline.py`: added 4 `ScoutState` fields;
  modified `_return_command`'s WM block (entry point when forward-blocked,
  and a new committed-escape check at the top of the `target is not
  None` branch) and the `pop_if_reached` success path (resets the new
  fields). No other function touched.
- New: `tests/validate_c2_s4_return_correction.py` (Tests S4-1..14),
  `tests/C2_S4_RETURN_LIMIT_CYCLE_DIAGNOSIS.md`,
  `tests/C2_S4_RETURN_CORRECTION_REPORT.md` (this file),
  `tests/C2_S4_RETURN_EPISODES.csv`, `tests/C2_S4_REACQUISITION_TRACE.csv`.
- No existing report was overwritten.

## X. Whether `c2_working_memory.py` changed

**No.** SHA-256 confirmed identical before and after (§ Source safety
table, Test S4-6/hash test). `home_observation.py` and `energy_sensor.py`
are likewise unchanged.

## Y. Whether a further C2 controller correction is justified

No evidence currently supports one. The proven S4 mechanism (§Diagnosis)
no longer recurs in any of the 6 remaining failures; all 6 are
attributable to energy depletion, the time horizon, or legitimate varying
local obstacle complexity -- exactly the "legitimate Return failure may
remain" outcome the task's own acceptance criterion anticipates, not a
controller defect.

## Z. Freeze recommendation

**Not yet, per the Stop Rule.** This report documents a diagnosis-plus-
minimal-correction task, not a freeze review. R01-R20 have not been run,
C3 has not started, and the Stop Rule explicitly reserves that decision
for a separate step.

---

## Comparison across the three development stages (diagnostic only)

| | Stage 1 (historical, pre-Home) | Stage 2 (post-architecture, pre-S4) | Stage 3 (post-S4) |
| --- | ---: | ---: | ---: |
| Return attempts | 11 | 24 | 20 |
| NEST_REACHED | 2 (18%) | 16 (67%) | 14 (70%) |
| Dominant failure cause | S1 (invalid origin) + S4 | S4 (5/8, 62.5%) | none dominant; energy (4/6) |
| Reacquisition NO_EFFECT rate | 71% | 55% | 7% |
| S1 recurrence | present | 0 | 0 |

**This is diagnostic context only -- not a claim of a measured
experimental C2 effect size.** Each stage used different, cumulatively
corrected architecture (Home semantics, then RF/portability, then Solar,
then S4); the comparison explains *why* the numbers moved, it does not
establish a controlled effect.

---

**C2 S4 RETURN LIMIT-CYCLE: CORRECTED — READY FOR C2 FREEZE REVIEW**
