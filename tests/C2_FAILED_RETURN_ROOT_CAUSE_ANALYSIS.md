# C2 Working Memory — Failed RETURN_HOME Root-Cause Analysis

Date: 2026-08-27. Scope: forensic analysis only. **No source file was
modified. No WM parameter was changed. No research seed (R01-R20) was run.
C3 was not started.** Data source: the existing DEV01-03 3600s development
runs already in `results/C2_WORKING_MEMORY_PREFREEZE/` — no rerun was
required; every field below is reconstructed from `swarm_events.csv`,
`working_memory_events.csv`, `state_transitions.csv`,
`robot_energy_timeline.csv`, `swarm_trajectory.csv`, and `swarm_summary.json`
already on disk. Ground-truth world coordinates from `swarm_trajectory.csv`
were used for this offline analysis only — never exposed to the controller.

## A. Total Return episodes

**16** `RETURN_HOME_START` episodes across DEV01 (4), DEV02 (3), DEV03 (9).
One return per episode (`return_id` suffix `_Return1` throughout — no
scout attempted a second `RETURN_HOME_START` within the same
`HARVEST_COMPLETE`, since a scout that fails a return either depletes or
runs out of simulation time, both terminal).

## B. Successful vs failed

**8 successful (`NEST_REACHED` confirmed), 8 failed.** Matches the given
totals exactly (DEV01 2/4, DEV02 0/3, DEV03 6/9).

## C. Failed Return table

Full 16-row table (8 success + 8 failed) with every requested field is in
[tests/C2_RETURN_EPISODE_TABLE.csv](C2_RETURN_EPISODE_TABLE.csv). Summary of
the 8 failures:

| Return ID | Outcome at end | Return-start energy | Return-end energy | Duration (s) | Primary cause |
| --- | --- | ---: | ---: | ---: | --- |
| DEV01_Scout2_Trip1_Return1 | TIME_LIMIT_REACHED, still RETURN_HOME | 2.877 | 0.604 | 3481.6 | **F3** |
| DEV01_Scout1_Trip1_Return1 | ROBOT_DEPLETED | 1.105 | 0.000 | 1671.3 | **F3** |
| DEV02_Scout2_Trip1_Return1 | ROBOT_DEPLETED | 2.939 | 0.000 | 1599.2 | **F4** |
| DEV02_Scout1_Trip1_Return1 | TIME_LIMIT_REACHED, still RETURN_HOME | 2.818 | 0.487 | 3454.2 | **F3** |
| DEV02_Scout0_Trip1_Return1 | TIME_LIMIT_REACHED, still RETURN_HOME | 2.810 | 0.532 | 3421.7 | **F3** |
| DEV03_Scout2_Trip1_Return1 | ROBOT_DEPLETED | 2.827 | 0.000 | 1630.1 | **F4** |
| DEV03_Scout0_Trip4_Return1 | TIME_LIMIT_REACHED, still RETURN_HOME | 1.284 | 0.230 | 951.3 | **F7** (secondary F2) |
| DEV03_Scout1_Trip4_Return1 | TIME_LIMIT_REACHED, still RETURN_HOME | 2.492 | 1.950 | 802.1 | **F3** |

**Zero of the 8 failures reached zero energy while still making valid
progress toward the Nest.** Every energy-depletion failure (3 of 8:
DEV01_Scout1, DEV02_Scout2, DEV03_Scout2) had already lost effective
navigation (oscillation deadlock or lost WM guidance) well before energy
ran out.

## D. DEV01 failed-return analysis

- **DEV01_Scout2_Trip1** (F3): Return started at t=118.4s only 2.09m from
  its own cycle origin. Instead of a quick return, the Scout entered a
  **periodic deadlock**: positions at t=400.0s and t=414.8s (and again at
  429.6s — an exact 14.8s period) are bit-for-bit identical
  (`(5.476, 2.132)`, heading 79.7°), with `action` alternating
  `WM_RETRACE_TURN_45 → RETURN_LOCAL_ESCAPE_45/OBSTACLE_ESCAPE_TURN_45 →
  WM_RETRACE_TURN_45 → ...` forever. Net distance travelled over the whole
  3481.6s episode was only 20.4m (18509 avoidance/fallback actions
  recorded). The run ended at `TIME_LIMIT_REACHED` with 0.60 energy still
  available — the Scout never got the chance to run out of energy; it was
  simply stuck.
- **DEV01_Scout1_Trip1** (F3): Same signature — turn:forward action ratio
  30.3, a 1.92m bounding box over the whole 1671.3s episode. WM had
  reached full 300-entry capacity (with 247 prunes) by the time the return
  started, but the failure mode during the return itself is the same
  oscillation deadlock, not an exhausted or discontinuous breadcrumb chain
  (291 of 300 entries were still unpopped when energy reached zero).
  `ROBOT_DEPLETED` here is a downstream consequence of the deadlock, not an
  independent energy limitation.

## E. DEV02 failed-return analysis

See Part 9 below for the full forensic timeline (DEV02 is the priority
case). Summary: **Scout2 = F4 (WM guidance silently switched off 0.51m
from origin, at wm_size=1, 1547s before depletion), Scout1 = F3
(oscillation deadlock at a frozen 7.20-7.21m from origin for ~3200s, after
having already been within 0.043m), Scout0 = F3 (oscillation deadlock,
essentially zero net progress for the full 3421.7s episode).**

## F. DEV03 failed-return analysis

- **DEV03_Scout2_Trip1** (F4): Same mechanism as DEV02_Scout2 — WM guidance
  stopped at wm_size=1, 0.49m from origin (t=329.4s), then 12075 untargeted
  `RETURN_LOCAL_*` fallback actions carried the Scout 254.0m and drifted it
  out to 6.27m from origin (despite having been as close as 0.17m at one
  point) before `ROBOT_DEPLETED`. A `CONTACT_RECOVERY` episode (back-off,
  turn, complete) occurred immediately before depletion — consistent with
  the untargeted fallback eventually driving the Scout into a physical
  contact event it would not have encountered on a WM-guided direct path.
- **DEV03_Scout0_Trip4** (F7, secondary F2): Distinct signature from every
  other failure — this Scout was **not** stuck. Distance to its cycle
  origin *grew* steadily from 3.8m to a peak of 13.2m, then oscillated
  9-13m for the rest of the run, with `WM_RETRACE_*` actions dominant
  throughout (no frozen-position deadlock). The outbound leg for this
  cycle pruned 259 of 299 added breadcrumbs (87%, WM at full 300-entry
  capacity) before the return began. The retained breadcrumb chain is
  consistent with the most-direct portion of the outbound route having
  been discarded by pruning, forcing a longer/indirect retrace. The Scout
  was still actively navigating with 0.23 energy left when
  `TIME_LIMIT_REACHED` — this looks primarily like "ran out of time on a
  long trip," with the pruning-linked route inefficiency flagged as a
  **plausible but not confirmed** contributing factor (see Part 6).
- **DEV03_Scout1_Trip4** (F3): turn:forward ratio 23.3, 2.46m bounding box
  over 802.1s, distance to origin never improved (3.07m → 3.07m minimum →
  4.74m final). This episode has the **highest remaining energy of any
  failure (1.95, essentially two-thirds of full capacity)** — the clearest
  single data point in the whole dataset that energy is not the limiting
  factor for this failure class.

## G. Breadcrumb continuity findings

- **CONTINUOUS** for all 8 successful returns and for 5 of the 8 failures
  (the F3 oscillation-deadlock cases) — in all of these, WM still held
  valid, ordered, usable entries; the chain itself was never the problem.
- **BROKEN_BY_PRUNING (tentative, not confirmed)** for DEV03_Scout0_Trip4 —
  87% of this cycle's breadcrumbs were pruned before return began, and the
  post-prune chain does not lead the Scout on a monotonically-improving
  path back to origin. This is the one case in the dataset where pruning
  volume is high enough, and the observed path deviation large enough,
  that a genuine capacity-related discontinuity is plausible — but Part 6
  below stops short of confirming it, per the instruction not to blame
  pruning merely because it occurred.
- **EXHAUSTED-BUT-STILL-VALID** for DEV02_Scout2 and DEV03_Scout2 (F4): the
  chain was never actually broken or discontinuous — it correctly reduced
  to exactly one entry, the cycle origin, which is the intended final
  state. The defect is not in the chain's continuity but in **the
  navigation code's decision to stop using that final, still-valid entry**
  (Part 7 / Part 11).
- No case showed `INVALID_ORDER` — `WM_POP` events are strictly
  newest-first in every episode inspected, consistent with the design.

## H. WM capacity/pruning findings

Verified from source (`src/swarm_simulate/c2_working_memory.py`, **not
modified**): `maximum_entries=300` (`CycleWorkingMemory.__init__`, called
with defaults from `swarm_baseline.py`'s `CycleWorkingMemory(enabled=...)`),
`spacing_m=0.25`, `pop_if_reached(..., tolerance_m=0.28)`.

Capacity was reached (300 entries) in 3 of 16 episodes: DEV01_Scout1_Trip1
(prune=247, failed), DEV03_Scout1_Trip1 (prune=122, **succeeded**),
DEV03_Scout0_Trip4 (prune=259, failed). The same capacity limit produced
one success and two failures — capacity alone does not predict outcome.
**Only DEV03_Scout0_Trip4 shows a plausible link between pruning volume and
the failure mode** (steadily growing distance-to-origin, not a deadlock);
the other capacity-reaching episodes' failure/success was governed by the
F3/F4 mechanisms below, independent of whether pruning had occurred.
**No recommendation to raise capacity is made** — per the task's own rule,
a higher success rate alone is not sufficient justification, and 13 of 16
episodes never approached capacity at all.

## I. Local avoidance findings

This is the dominant finding of the whole analysis. **5 of 8 failures
(DEV01_Scout2, DEV01_Scout1, DEV02_Scout1, DEV02_Scout0,
DEV03_Scout1_Trip4) show the same reproducible signature: a long-duration
(802-3482s), near-zero-net-displacement (1.9-3.8m bounding box) period
where `action` alternates repeatedly between `WM_RETRACE_TURN_45` and
`OBSTACLE_ESCAPE_TURN_45` / `RETURN_LOCAL_ESCAPE_45` / `RETURN_LOCAL_TURN_45`,
with a turn:forward action ratio of 23-30:1.** In the clearest instance
(DEV01_Scout2, t=400-440s), the exact same sequence of positions, headings,
and sensor readings repeats with an **exact 14.8-second period**, proving
this is a genuine closed-loop deadlock, not merely slow progress: the WM
branch requests a turn toward its target; once oriented, the local
obstacle-clearance check (`swarm_baseline.py`'s `_return_command`, the
branches below the WM block, and `_begin_clear_side_turn` /
`_obstacle_escape_command`) detects an obstacle and forces a turn away;
once turned away, WM's `abs(heading_error) > math.radians(22.5)` condition
re-triggers a turn back toward the target; repeat indefinitely. **There is
no mechanism anywhere in `_return_command` that detects this condition and
attempts an alternative escape or route reacquisition** — the C1-side
local-safety branches and the WM-side retrace branch simply keep
overriding each other. Classification: **`OVERRIDE_CAUSED_ROUTE_LOSS` /
`REPEATED_AVOIDANCE_OSCILLATION`.**

For DEV02_Scout1 specifically, this deadlock occurred **after** the Scout
had already gotten to within 0.043m of its origin — i.e., the Scout
found and nearly completed the correct route, then got trapped in this
oscillation on a subsequent breadcrumb, illustrating that the mechanism is
not tied to a "hard" outbound path; it can trigger anywhere along an
otherwise-successful retrace.

No evidence of `CROSS_SCOUT_INTERACTION` was found as the primary driver
in any of the 5 oscillation cases (each Scout's deadlock persists for
minutes, far longer than any plausible transient cross-Scout encounter);
wall/corridor geometry at each frozen position (`front_m` values
repeatedly at or near `safe_front_m=0.72` / `turn_side_clearance_m=0.42`
during the deadlock ticks) is the more consistent explanation.

## J. Energy findings

Recomputed per the classification rule in the task:

- **`ENERGY_DEPLETION_WHILE_VALIDLY_RETRACING`: 0 episodes.** No failure
  fits this category — in every case that ended in `ROBOT_DEPLETED`
  (DEV01_Scout1, DEV02_Scout2, DEV03_Scout2), navigation had already
  broken down (oscillation or lost-WM-guidance wandering) well before
  energy reached zero.
- **`ENERGY_DEPLETION_AFTER_ROUTE_LOSS`: 3 episodes** (DEV01_Scout1 —
  oscillation-deadlock route loss; DEV02_Scout2, DEV03_Scout2 — F4
  guidance-loss route loss / untargeted wandering).
- **`NAVIGATION_FAILURE_WITH_ENERGY_REMAINING`: 4 episodes**
  (DEV01_Scout2, DEV02_Scout1, DEV02_Scout0, DEV03_Scout1_Trip4 — all
  oscillation deadlocks, all ended `TIME_LIMIT_REACHED` with 0.49-1.95
  energy still available).
- **`TIME_LIMIT_WITH_ENERGY_REMAINING`: 1 episode** (DEV03_Scout0_Trip4 —
  the one case that was genuinely still navigating, not deadlocked, and
  simply needed more simulated time).

This directly answers the task's central energy question: **failure is not
attributable to energy limitation in any of the 8 cases.** Every failure
has an identifiable navigation-side factor, and in 5 of 8 cases the Scout
had substantial energy remaining (0.49-1.95) when the simulation horizon
ended.

## K. Retrace-target findings

Two distinct target-behavior defects were identified and are treated
separately because they have different mechanisms and different fixes:

1. **`TARGET_OSCILLATION`** (5 episodes, see Part I): the *target itself*
   does not misbehave — WM correctly and consistently points at the next
   breadcrumb — but the *combination* of the WM turn-toward-target branch
   and the local obstacle-avoidance branch never converges.
2. **A genuine target-selection defect** (2 episodes, DEV02_Scout2,
   DEV03_Scout2): `src/swarm_simulate/swarm_baseline.py:566` —
   ```python
   target = memory.return_target(scout.cycle_id)
   if target is not None and len(memory.entries) > 1:
       ...use target for WM-guided turning/forward motion...
   ```
   `return_target()` returns a valid, precise `(x, y)` origin coordinate
   even when only one entry remains (`c2_working_memory.py`'s
   `return_target`: `if not self.enabled or self.cycle_id != int(cycle_id)
   or not self.entries: return None` — a single remaining entry does not
   trigger this `None` path). But the **caller** additionally requires
   `len(memory.entries) > 1` before it will actually steer toward that
   target. When exactly one entry (the origin) remains, `target` is valid
   and non-`None`, yet the condition is `False`, so **the WM branch is
   skipped entirely** and control falls through to the C1 stateless
   fallback (`RETURN_LOCAL_*`), which has no positional target at all.
   Verified precisely in `DEV02_Scout2`: the last `WM_POP` /
   `working_memory_events.csv` row for that episode is at `t=125.0,
   wm_size=1`; the very next relevant trajectory action, `t=126.3`, is
   `RETURN_LOCAL_FORWARD` (a pure C1 action, not a WM one), and the Scout
   was still 0.51m from its origin at that moment — well outside the
   `nest_delivery_radius_m=0.12` that would have let `NEST_REACHED` fire
   first and made the gap moot. Classification: **`TARGET_UNREACHABLE_AFTER_AVOIDANCE`**
   is not quite right (nothing made it unreachable — the code simply stopped
   trying); the closest fit is **`TARGET_SEQUENCE_BROKEN`** in the sense
   that the *last* element of the intended sequence is silently dropped
   from use.

Cross-checking against **successful** episodes confirms this is a real,
reproducible behavior rather than something inferred from failures alone:
`DEV03_Scout1_Trip1`, `DEV03_Scout0_Trip3`, and `DEV03_Scout1_Trip3` all
also hit `wm_size=1` before `NEST_REACHED` (at 4.81m, 0.48m, and 0.29m from
origin respectively) — in all three, the untargeted C1 fallback happened,
by chance, to still carry the Scout to the Nest (in 153s, 206s, and 0.7s
respectively). **The same code path produced 2 failures and 3 lucky
recoveries out of 5 occurrences** — strong evidence this is a reliability
defect in the mechanism itself, not something that only shows up when
something else has already gone wrong.

## L. Nest final-approach findings

No episode showed `REACHED_ORIGIN_NOT_NEST` as a distinct failure mode
in the sense of a geometric gap between the recorded cycle origin and the
Nest confirmation zone — the recorded per-Scout cycle origins are all
within about 0.1-0.2m of the physical Nest (as expected, since a cycle's
local origin is set at the position where the previous
`DELIVER`/mission-start occurred, which is at the Nest). The actual final-
approach issue is the target-logic gap in Part K (F4) combined with the
`0.28m` WM pop tolerance being wider than the `0.12m` Nest confirmation
radius — i.e., **the numeric relationship between these two constants,
not a spatial origin/Nest mismatch, is what creates the risk window** in
which a Scout can lose precise WM guidance before it is close enough for
`NEST_REACHED` to fire. Classification for all 16 episodes:
**`NORMAL_NEST_CONFIRMATION`** for the 8 successes (once
`_environment_nest_reached` returns `True`, `DELIVER` follows
immediately and correctly every time); no episode reached the origin
region without ever attempting Nest confirmation.

## M. Successful-vs-failed comparison

Full data in `C2_RETURN_EPISODE_TABLE.csv`. Key patterns, using evidence
only:

- **Energy at return start is not a discriminator.** Successes ranged
  1.66-2.91; failures ranged 1.11-2.94 (DEV02's three failures each started
  with 2.81-2.94, near-full capacity — among the *highest* starting
  energy in the whole dataset).
- **Outbound route length/complexity is not a clean discriminator either.**
  `wm_start_size` (a proxy for outbound path length) for failures spans
  21-300; for successes it spans 29-300. The longest successful return
  (DEV03_Scout1_Trip1, `wm_start_size=300`, capacity reached) succeeded
  despite hitting the same F4 code path that caused two failures.
- **What does discriminate: whether the episode entered an oscillation
  deadlock (F3) or lost WM guidance far from the Nest confirmation radius
  (F4) at all.** None of the 8 successful episodes show the
  turn:forward-ratio/frozen-bounding-box deadlock signature; 5 of 8
  failures do. Among the 5 episodes that hit the F4 "`wm_size` reaches 1"
  code path, outcome correlates almost entirely with how far from the
  0.12m Nest radius the Scout happened to be at that instant (0.29-0.51m:
  1 failure — DEV03_Scout1_Trip3 barely escaped; 4.81m and 0.48m: lucky
  successes; 0.51m and 0.49m: 2 failures) — this is essentially a coin
  flip governed by geometry, not a controlled design margin.

## N. Root-cause distribution

| Primary cause | Count | Episodes |
| --- | ---: | --- |
| F1 — ENERGY_LIMITATION | **0** | — |
| F2 — WM_PRUNING_ROUTE_LOSS | 0 (1 secondary) | secondary on DEV03_Scout0_Trip4 |
| F3 — LOCAL_AVOIDANCE_ROUTE_LOSS | **5** | DEV01_Scout2, DEV01_Scout1, DEV02_Scout1, DEV02_Scout0, DEV03_Scout1_Trip4 |
| F4 — RETRACE_TARGET_LOGIC | **2** | DEV02_Scout2, DEV03_Scout2 |
| F5 — NEST_FINAL_APPROACH | 0 | — |
| F6 — CROSS_SCOUT_DYNAMIC_INTERACTION | 0 | — |
| F7 — TIME_LIMIT | **1** | DEV03_Scout0_Trip4 |
| F8 / F9 | 0 | — |

## O. Whether current C2 should remain frozen as-is

**No — not without acknowledging two identified, reproducible navigation
defects.** The Working Memory *bookkeeping* (add/prune/pop/reset, capacity,
spacing, cycle-scoping, no ground truth, determinism) is confirmed correct
by every acceptance test (A-L, all still PASS) and by this analysis (every
successful return used it correctly, and the breadcrumb chain itself was
never discontinuous or out-of-order in any episode). The defects are
specifically in the **decision logic that consumes WM's output during
`_return_command`** — one that silently stops using a still-valid final
target, and one where WM and local-safety avoidance can override each
other indefinitely with no escape.

## P. Whether a WM correction is justified before research freeze

**Yes, for two narrowly-scoped items — see the proposals below.** Both meet
the task's own bar for justification ("local avoidance has no route
reacquisition mechanism"; "breadcrumb target logic can deadlock" /
silently disables itself) rather than "success rate should be higher."

### Proposal 1 — F4: WM stops guiding when exactly one entry (the origin) remains

- **Problem:** `swarm_baseline.py:566`'s `len(memory.entries) > 1` guard
  causes the WM branch to be skipped once only the origin entry is left,
  even though `return_target()` still returns a valid, precise coordinate.
- **Evidence:** `working_memory_events.csv` + `swarm_trajectory.csv`
  correlation in DEV02_Scout2 (WM stops at `wm_size=1`, 0.51m from origin,
  t=125.0; C1 fallback action begins 1.3s later) and DEV03_Scout2
  (identical mechanism, 0.49m, t=329.4); the same code path also occurred
  in 3 successful episodes purely by chance (DEV03_Scout1_Trip1,
  DEV03_Scout0_Trip3, DEV03_Scout1_Trip3).
- **Affected Return IDs:** DEV02_Scout2_Trip1_Return1,
  DEV03_Scout2_Trip1_Return1 (failures); DEV03_Scout1_Trip1_Return1,
  DEV03_Scout0_Trip3_Return1, DEV03_Scout1_Trip3_Return1 (successes that
  exercised the same gap by luck).
- **Proposed change (not implemented):** allow the WM branch to steer
  toward the origin using the single remaining entry, instead of falling
  through to the C1 fallback once `len(memory.entries) == 1`.
- **Why this remains "Working Memory":** it does not add any new
  information, ground truth, or capability to WM — the origin coordinate
  is already stored and already returned by `return_target()`; the change
  only lets the existing final-approach retrace behavior continue to the
  end of the sequence it already computed, instead of discarding it one
  step early.
- **Risk to experimental semantics:** low but not zero — it changes C2's
  terminal-approach trajectory shape in the (currently mis-handled) last
  0.12-0.28m of return, which is a real behavioral change to C2 (not C1;
  `working_memory_enabled=False` never reaches this branch) and would need
  re-validation against the existing DEV01-03 baselines and a fresh
  determinism check.
- **Tests required afterward:** re-run `tests/validate_c2_working_memory.py`
  (criteria D/I/J), a fresh 3-seed development batch to confirm the two
  DEV02/DEV03 depletion failures are resolved without introducing new
  ones, and an isolation re-check (`tests/validate_condition_isolation.py`)
  since the change touches the WM/C1 boundary condition directly.

### Proposal 2 — F3: no route-reacquisition when WM retrace and local avoidance repeatedly override each other

- **Problem:** `_return_command` has no mechanism to detect that the
  WM-turn branch and the local-safety-avoidance branches have been
  overriding each other for an extended period without net progress, and
  no fallback/recovery behavior analogous to C1's existing bounded
  contact-recovery retry.
- **Evidence:** 5 of 8 failed episodes show an exact or near-exact
  periodic deadlock (turn:forward ratio 23-30:1, bounding box 1.9-3.8m,
  duration 802-3482s), most strikingly DEV01_Scout2's bit-for-bit
  14.8-second repeating cycle.
- **Affected Return IDs:** DEV01_Scout2_Trip1_Return1,
  DEV01_Scout1_Trip1_Return1, DEV02_Scout1_Trip1_Return1,
  DEV02_Scout0_Trip1_Return1, DEV03_Scout1_Trip4_Return1.
- **Proposed change (not implemented):** some form of stuck-detection
  bounded to the existing local-safety framework (e.g., detect
  no-net-displacement over a bounded window during WM retrace and trigger
  one bounded reorientation/escape maneuver, structurally similar to the
  existing `CONTACT_RECOVERY_*` bounded retry already used for physical
  contact) so the Scout can break the WM<->avoidance cycle rather than
  repeat it indefinitely.
- **Why this remains "Working Memory":** it does not change what WM
  stores or how breadcrumbs are added/pruned/popped — it only changes how
  the *existing* local-safety-override mechanism (already part of C2's
  approved design: "local safety override only") interacts with a stuck
  WM-retrace attempt, using the same "current-cycle, no ground truth"
  information the Scout already has.
- **Risk to experimental semantics:** moderate — this is the more
  behaviorally significant of the two proposals, since it introduces new
  decision logic (a stuck-detector) rather than just removing an
  overly-strict guard. It would need careful scoping to avoid
  accidentally masking genuinely difficult (but legitimate) return
  geometry.
- **Tests required afterward:** the full acceptance suite (A-L),
  determinism re-check, a fresh 3-seed development batch specifically
  re-examining these 5 scout/seed combinations, and a dedicated new
  diagnostic (analogous to this one) confirming the deadlock signature no
  longer appears while the RNG/energy/physics equivalence to the current
  design is preserved outside of the deadlock scenario.

## Answers to Part 12

- **A. Is Working Memory fundamentally functioning as designed?**
  Partially. The storage/bookkeeping half (add, prune, pop, reset,
  bound, cycle-scoping, determinism) is fully correct per this analysis
  and the acceptance suite. The consumption half (`_return_command`'s use
  of WM's output) has two confirmed defects.
- **B. Are failed Returns mostly caused by legitimate physical/energy
  limitations?** **NO.** 0 of 8 failures fit `ENERGY_DEPLETION_WHILE_VALIDLY_RETRACING`.
- **C. Is there a systematic WM implementation limitation causing avoidable
  failures?** **YES** — two distinct, reproducible mechanisms (F3, F4),
  together accounting for 7 of 8 failures.
- **D. Is there evidence that breadcrumb capacity/pruning breaks intended
  current-cycle retrace?** Weak, single-case evidence only
  (DEV03_Scout0_Trip4) — flagged as plausible, not confirmed.
- **E. Is there evidence that local avoidance can permanently lose the WM
  route?** **YES**, strongly — 5 of 8 failures.
- **F. Is there evidence of retrace target logic defect?** **YES** —
  confirmed via source inspection + event-log correlation in 2 failures
  and 3 lucky successes (5 total occurrences of the same code path).
- **G. Is DEV02 0/3 explained by legitimate conditions, or by a systematic
  algorithm limitation?** **Systematic algorithm limitation.** All three
  DEV02 returns started with near-full energy (2.81-2.94) — there is no
  seed-specific "hard" physical difficulty visible in the starting
  conditions. Scout2 = F4, Scout1 = F3, Scout0 = F3 — both of the two
  confirmed defect mechanisms are present in this one seed's 3 failures.

## Final decision

**C2 FAILED RETURN ANALYSIS: WM CORRECTION JUSTIFIED**
