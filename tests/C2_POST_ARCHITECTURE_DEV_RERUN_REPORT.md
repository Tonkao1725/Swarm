# C2 Working Memory — Post-Architecture DEV01–DEV03 Rerun & Diagnosis

Date: 2026-08-27. Scope: **measurement and diagnosis only**. No source file
was modified during this task (verified by SHA-256 before and after — see
§A). No commit was made. No canonical research seed (R01-R20) was run. C3
was not started.

## A. Source/provenance before run

- Branch: `c2-working-memory-dev-20260827`
- HEAD: `818c64f2729a38871447526d8b42090d867dad14`
- `git status` at start: matches the uncommitted state accumulated across
  this session's prior tasks (Boot/Home, Canonical Home Arrival, RF
  hardware alignment, Sim-to-Real architecture correction) — no unrelated
  changes.
- SHA-256 (identical before and after all three runs — **confirmed
  unchanged**):

| File | SHA-256 |
| --- | --- |
| `main.py` | `39279bdf...49afbd8` |
| `src/swarm_simulate/swarm_baseline.py` | `9dbd6729...f0bc47f` |
| `src/swarm_simulate/c2_working_memory.py` | `b9a25db8...f478b48d` |
| `src/swarm_simulate/home_observation.py` | `1aa9093d...cd20e4` |
| `src/swarm_simulate/nest_beacon_hardware.py` | `e40d9d65...628f4d920` |

Runner config (identical to the historical corrected-C2 runs, replicated
exactly from the preserved `scratchpad/f3f4/DEV0X_corrected_.../metadata`):
`mission_mode=research; nest_energy_target=6; scout_count=3; horizon_s=3600;
WM=True; EM=False; Exchange=False; AIH=False; FAST_HEADLESS_RESEARCH_MODE=1`.
Seeds: DEV01=2118334751, DEV02=920265301, DEV03=652974033 (development
seeds, not canonical R01-R20).

## B. DEV01 result (seed 2118334751)

`exit=0; engineering=COMPLETED; mission=TIME_LIMIT_REACHED;
experimental_validity=INVALID_CONTROLLER_CONTACT_FAILURE`

**INVALID — see §O.** Scout0 entered a 1717.7 s (28.6 min) stationary-turn
deadlock during EXPLORE (action `SOLAR_TURN_45`, not Return/WM) at
world (11.51, 7.87) from t=1882.3 to the 3600 s horizon, never escaping.
This is a **new, separately-reported finding (§K), not S4** — it occurred
entirely inside EXPLORE, outside C2 Return/WM's scope. Scout1 and Scout2's
Return attempts are unaffected by this (independent Scouts, independent
episodes) and are included in the behavioral analysis below.

Return funnel: 3 RETURN_HOME_START (S0×1, S1×1, S2×1) -> 1 NEST_REACHED/DELIVER
(Scout0) -> 2 failed (Scout1 depleted; Scout2 active at horizon).

## C. DEV02 result (seed 920265301)

`exit=0; engineering=COMPLETED; mission=TIME_LIMIT_REACHED;
experimental_validity=VALID`

Return funnel: 8 RETURN_HOME_START (S0×2, S1×2, S2×4) -> 5 NEST_REACHED/DELIVER
(S0×1, S1×1, S2×3) -> 3 failed.

## D. DEV03 result (seed 652974033)

`exit=0; engineering=COMPLETED; mission=TIME_LIMIT_REACHED;
experimental_validity=VALID`

Return funnel: 13 RETURN_HOME_START (S0×4, S1×2, S2×7) -> 10 NEST_REACHED/DELIVER
(S0×3, S1×1, S2×6) -> 3 failed.

## E. Aggregate Return funnel (DEV01–DEV03)

| Stage | Count |
| --- | --- |
| RETURN_HOME_START (Return attempts) | **24** |
| HOME_CONFIRMED events (Boot, 1 per Scout per run) | 9/9 |
| NEST_REACHED | **16** |
| DELIVER | **16** |
| Failed Return attempts | **8** |

Success rate: 16/24 = **66.7%**.

## F. Nest/Home confirmation counts

Every one of the 9 Scout-runs (3 Scouts x 3 DEV seeds) shows exactly one
`HOME_CONFIRMED` event (at Boot, t=0.0), matching the architecture's
"confirm once per Scout at Boot" design — Cycle 2+ transitions use
`NEST_REACHED`/`DELIVER` (16 total, §E), not a repeated `HOME_CONFIRMED`.
No `HOME_CONFIRMED` or `NEST_REACHED` event was found to have fired without
both physical-region membership and RSSI passing (confirmed by source
architecture — Test HOME-3/10/11/RF-8 already regression-guard this at the
unit level; no live-run anomaly observed).

## G. Delivery counts

16 DELIVER events, matching NEST_REACHED 1:1 (every Nest arrival converted
to a delivery — no case of reaching the region without the corresponding
delivery firing).

## H. Cycle-1 origin validation (S1 check)

For all 9 Scout-runs: `HOME_CONFIRMED` (Boot) occurs strictly before the
first `WM_RESET` (Cycle-1 `start_cycle`) in the event log, verified
directly from `swarm_events.csv`/`working_memory_events.csv` timestamps
and ordering.

**S1 (INVALID_CYCLE_ORIGIN) recurrence = 0/9. Eliminated**, exactly as the
architecture correction intended — no STOP-and-classify-as-regression
condition triggered.

## I. Failed Return episode table

See `tests/C2_POST_ARCHITECTURE_RETURN_EPISODES.csv` (24 rows, all
attempts; 8 failed). Summary of the 8 failures:

| DEV | Scout | Duration (s) | Skip count | Primary cause |
| --- | --- | ---: | ---: | --- |
| DEV01 | 1 | 2695.5 | 14 | B_LIMIT_CYCLE (+ A downstream) |
| DEV01 | 2 | 3481.6 | 10 | B_LIMIT_CYCLE (+ C) |
| DEV02 | 0 | 3193.3 | 0 | G_UNRESOLVED |
| DEV02 | 1 | 2684.7 | 14 | B_LIMIT_CYCLE (+ A near-depletion) |
| DEV02 | 2 | 2207.5 | 0 | A_ENERGY_DEPLETION |
| DEV03 | 0 | 2252.3 | 7 | B_LIMIT_CYCLE |
| DEV03 | 1 | 2608.6 | 10 | B_LIMIT_CYCLE |
| DEV03 | 2 | 28.6 | 0 | C_TIME_HORIZON (incidental) |

All 8 failures ended at the 3600 s horizon (`TIME_LIMIT_REACHED`) — none
terminated early for another reason. Per instruction, none is classified
as "failure" merely for not returning to its exact local origin; all 8 are
classified on the actual observed mechanism (energy trace, skip/reacquisition
trace, spatial trajectory).

## J. Energy-related failures

- **DEV02 Scout2** (0 skips, ended `DEPLETED`, `internal_energy_final=0.0`):
  primary cause **A — energy depletion**. No reacquisition-pattern
  evidence of a limit cycle; energy trace shows steady consumption to
  zero, consistent with ordinary Return travel cost against a long/complex
  route, not an obstacle pathology.
- **DEV01 Scout1** and **DEV02 Scout1**: energy depletion/near-depletion
  is present at episode end, but is downstream of an extensive
  limit-cycle churn period (§K) that consumed the time/energy budget
  first — classified primary **B**, not A, per the task's explicit rule
  ("do not blame energy merely because the Scout eventually depleted;
  determine what consumed the preceding Return time").

## K. Obstacle/WM conflict recurrence (S4 check)

**S4 is clearly and repeatedly reproducible under the corrected
architecture.** Clearest example — **DEV02 Scout1**: after one legitimate
early advance (t=1199.0, bounding box 13.93 m -> 0.11 m, genuine progress),
the Scout enters a **2076.7 s (34.6 min)** stretch, t=1353.6 to t=3430.3,
confined to a **0.02–0.13 m** physical pocket, triggering **12 consecutive
`WM_ROUTE_REACQUIRE` events roughly every ~177 s**, every one classified
`NO_EFFECT` (Scout physically confined to the same tiny pocket both before
and after each skip) — 13 WM entries consumed with zero net spatial
progress. This is mechanistically identical to the pre-architecture S4
finding (`tests/C2_SECONDARY_RETURN_DIAGNOSIS.md` Part I): route
reacquisition correctly advances *which breadcrumb is targeted* but does
not resolve the underlying local obstacle-avoidance/WM-retrace conflict at
that physical location.

5 of 8 failed episodes (DEV01 S1, DEV01 S2, DEV02 S1, DEV03 S0, DEV03 S1)
have primary cause B_LIMIT_CYCLE.

## L. Limit-cycle episodes

See `tests/C2_POST_ARCHITECTURE_LIMIT_CYCLES.csv`. Two qualifying episodes:

1. **DEV02 Scout1** (S4_REPRODUCED, §K above) — 12x `WM_ROUTE_REACQUIRE`,
   all `NO_EFFECT`, 2076.7 s, never escaped, Return still active/near-depleted
   at horizon.
2. **DEV01 Scout0** (NEW_DEFECT_NOT_S4) — 17,177 consecutive turning-without-moving
   ticks (1717.7 s), action `SOLAR_TURN_45`, phase `EXPLORE` — **not** a
   Return/WM limit cycle; caused the DEV01 run's `INVALID_CONTROLLER_CONTACT_FAILURE`
   classification (§O). Reported separately per the Stop Rule's explicit
   instruction not to misclassify a new defect as S4.

A stricter "144+ *consecutive* zero-net-motion ticks while actively
turning" detector (matching the production
`_record_physical_stationary_rotation` logic exactly, including the
turning-vs-stationary distinction) was run over all 9 Scout trajectories;
only these 2 episodes qualified. (An earlier, cruder pass of this
detector — checking net motion only, without the "was actually turning"
condition — produced 7 additional false positives, all normal
`HARVEST_ACTIVE` dwell time at a resource; these were identified and
discarded before reporting, not included above.)

## M. Reacquisition effectiveness

65 `WM_ROUTE_REACQUIRE` events across all 9 Scout-runs, classified by
pre-/post-skip physical bounding box (full trace:
`tests/C2_POST_ARCHITECTURE_REACQUISITION_TRACE.csv`):

| Classification | Count | % |
| --- | ---: | ---: |
| NO_EFFECT | 36 | 55% |
| LEGITIMATE_ROUTE_ADVANCE | 15 | 23% |
| EFFECTIVE_ESCAPE | 7 | 11% |
| UNKNOWN (no post-skip window available) | 7 | 11% |

`NO_EFFECT` remains the plurality outcome (down from 71% in the
pre-architecture diagnosis, but still the single largest category) —
consistent with §K: route reacquisition itself functions correctly
(advances the target), but frequently does not resolve the underlying
physical conflict.

## N. PREMATURE_SKIP count

**0.** No traced event showed a target abandoned while the Scout was still
making genuine net progress toward it — every reacquisition in this rerun
followed the same bounded, deterministic 144-tick no-progress rule as
before. This matches the pre-architecture finding exactly (`PREMATURE_SKIP = 0`
there too) — `skip_unreachable`'s own trigger condition is not implicated;
consistent with the Stop Rule (not modified in this task regardless).

## O. Engineering validity

| Run | exit | engineering | validity |
| --- | --- | --- | --- |
| DEV01 | 0 | COMPLETED | **INVALID_CONTROLLER_CONTACT_FAILURE** |
| DEV02 | 0 | COMPLETED | VALID |
| DEV03 | 0 | COMPLETED | VALID |

No crash, no NaN, no invalid sensor state, no `CONTACT_STALLED` failure in
any run. DEV01 is flagged invalid solely by the pre-existing
`persistent_stationary_turn_deadlock` safety reporter (Scout0, §K/§B) —
kept **separate** from the behavioral funnel/root-cause analysis per
instruction: Scout0's own single (successful) Return episode is unaffected
and included in §E/§I; only its *subsequent* EXPLORE-phase freeze is
excluded from Return-behavior conclusions, since it is not a Return event
at all.

## P. Comparison to historical DEV results

| | Historical (pre-architecture) | Post-architecture (this rerun) |
| --- | ---: | ---: |
| DEV01 attempts / reaches | 4 / 1 | 3 / 1 |
| DEV02 attempts / reaches | 3 / 0 | 8 / 5 |
| DEV03 attempts / reaches | 4 / 1 | 13 / 10 |
| Total attempts / reaches | 11 / 2 (18%) | 24 / 16 (67%) |

**Mechanistic explanation (not a claim of "improvement"):** the dominant
driver is almost certainly the Canonical Home Arrival correction (a
separate, earlier task in this session) widening the Nest confirmation
region from `nest_delivery_radius_m=0.12 m` to `home_region_radius_m=1.05 m`
— an ~8.75x linear (and much larger areal) increase in the region a
returning Scout must merely enter, independent of WM/Return quality
itself. More Scouts also reached later cycles at all (higher attempt
counts in DEV02/DEV03) simply because earlier cycles now succeed instead
of stalling. This comparison is explicitly **not** used to claim the
Return controller itself improved — per the Historical Caveat, old and new
runs used different Home/origin semantics and are not a valid controlled
comparison. What *is* comparable, and does recur unchanged: the S4
mechanism itself (§K), still present and still the leading failure cause
among the failures that do occur.

## Q. Current root-cause distribution

| Cause | Count (of 8 failures) |
| --- | ---: |
| B_LIMIT_CYCLE (S4) | 5 |
| A_ENERGY_DEPLETION | 1 |
| C_TIME_HORIZON (incidental) | 1 |
| G_UNRESOLVED | 1 |
| D_INVALID_WM_ORIGIN (S1) | **0** |

## R. Whether S1 is eliminated

**Yes — confirmed eliminated.** 0/9 recurrence (§H). No STOP condition triggered.

## S. Whether S4 remains reproducible

**Yes — confirmed, clearly and repeatedly reproducible.** 5/8 (62.5%) of
current failures have S4 as primary cause; the clearest single example
(DEV02 Scout1) is a 34.6-minute, 12-event `NO_EFFECT` churn — comparable
in severity to the most extreme pre-architecture example. Route
reacquisition (`skip_unreachable`) itself is not shown to be defective
(0 `PREMATURE_SKIP`, §N) — the unresolved issue is the underlying local
obstacle-avoidance/WM-retrace conflict recurring at successive breadcrumbs,
exactly as previously diagnosed.

## T. Whether a controller correction is still justified

**Yes, per the Decision Rule** ("If a clear repeated pathological S4 limit
cycle remains: recommend a focused correction"). S1 is gone; S4 is not.
This task does **not** implement any correction (Stop Rule).

## U. Exact next recommendation

1. Treat this rerun as the new, valid development baseline for C2 Return
   behavior going forward (S1 eliminated; Nest-arrival semantics
   corrected and confirmed working end-to-end).
2. Pursue a **focused S4 correction** as a separate, explicitly-scoped
   task — the same candidates already identified in
   `tests/C2_SECONDARY_RETURN_DIAGNOSIS.md` Part P remain the most
   directly evidenced starting points (turn-vs-avoid hysteresis at the
   conflict heading; bounded ability to retry a previously-skipped
   breadcrumb) — re-evaluate them against this rerun's fresh trace data
   before choosing.
3. **Separately**, investigate the new DEV01 Scout0 EXPLORE-phase
   `SOLAR_TURN_45` stationary-turn deadlock (§B/§K/§O) as its own,
   distinct task — it is common infrastructure (EXPLORE-phase, shared
   with C1), unrelated to WM/Return, and caused an engineering-invalid
   run; it was not investigated further here beyond localizing it (single
   occurrence, 1717.7 s, world position (11.51, 7.87)) since it is out of
   this task's Return/WM scope.
4. Do not run R01-R20, Freeze, or start C3 until at least the S4
   correction (item 2) is addressed and re-validated.

---

**C2 POST-ARCHITECTURE DEV RERUN: READY FOR RETURN CORRECTION REVIEW**
