# C2 Working Memory — F3/F4 Return Correction Report

Date: 2026-08-27. Scope: implementation correction for the two demonstrated
defects in `tests/C2_FAILED_RETURN_ROOT_CAUSE_ANALYSIS.md`. **No research
seed (R01-R20) was run. No commit was made. No freeze tag was created. C3
was not started.**

Prior evidence (`C2_FAILED_RETURN_ROOT_CAUSE_ANALYSIS.md`,
`C2_RETURN_EPISODE_TABLE.csv`) is preserved unmodified.

## A. Exact F4 correction

**File:** [src/swarm_simulate/swarm_baseline.py](../src/swarm_simulate/swarm_baseline.py), `_return_command`.

**Before:**
```python
target = memory.return_target(scout.cycle_id)
if target is not None and len(memory.entries) > 1:
    ...steer toward target...
```

**After:** the `len(memory.entries) > 1` guard is removed; the condition is
now `if target is not None:`. `pop_if_reached` (unchanged) still never
removes the last entry (`if len(self.entries) > 1: self.entries.pop()`),
so this cannot cause the origin to be popped or invented — it only lets
WM keep steering toward the origin instead of silently handing control to
the untargeted C1 fallback the instant only that one, still-valid entry
remains.

## B. Exact F3 correction

**Files:** [src/swarm_simulate/swarm_baseline.py](../src/swarm_simulate/swarm_baseline.py) (`ScoutState`, `_return_command`),
[src/swarm_simulate/c2_working_memory.py](../src/swarm_simulate/c2_working_memory.py) (`CycleWorkingMemory.skip_unreachable`).

- `ScoutState` gained five WM-correction-only fields: `wm_target_lock`,
  `wm_target_lock_x_m`, `wm_target_lock_y_m`, `wm_stuck_ticks`,
  `wm_route_reacquisition_count`.
- `CycleWorkingMemory` gained `skip_count` and a new method
  `skip_unreachable(cycle_id)` that pops the current top-of-stack entry
  using the **exact same guard** as `pop_if_reached`
  (`len(self.entries) > 1`) — it can never remove the final origin entry.
- In `_return_command`'s WM block: each tick, if the active retrace target
  (identity, i.e. its stored coordinate) is unchanged from the previous
  tick, local progress since the target was locked is compared against
  `memory.spacing_m` (0.25 m, unchanged). If `return_stationary_turn_limit`
  ticks pass with less than one spacing-quantum of net local progress
  toward the current target, `skip_unreachable` is called and the action
  `"WM_ROUTE_REACQUIRE"` is returned, dropping the stuck target and
  resuming WM guidance on the next-older breadcrumb on the following tick.
  `return_stationary_turn_limit` is the pre-existing constant already used
  for the (separate, reporting-only) stationary-rotation-deadlock report —
  reused, not duplicated.
- Logging: `working_memory_events.csv` gains a `WM_ROUTE_REACQUIRE`
  operation row whenever this fires; `swarm_summary.json` gains
  `working_memory_route_reacquisitions` per Scout.

## C. Files modified

- [src/swarm_simulate/swarm_baseline.py](../src/swarm_simulate/swarm_baseline.py) — `ScoutState` new fields; `_return_command` F4/F3 logic; WM event-logging action set; cycle-reset of the new F3 state; `swarm_summary.json` output field.
- [src/swarm_simulate/c2_working_memory.py](../src/swarm_simulate/c2_working_memory.py) — `skip_count`; `skip_unreachable` method.
- New test file: [tests/validate_c2_return_correction.py](../tests/validate_c2_return_correction.py) (Tests M-Q).

No other file was touched. No WM capacity, spacing, add rule, pruning
policy, energy, dt, speed, sensor range, maze, resource, Nest, RNG, EM,
Exchange, or AIH code was changed. Verified: `git diff` against baseline
commit `2cc0275` touches only the two `src/swarm_simulate/` files above
(plus the pre-existing, unrelated main.py/render_swarm_replay_video.py
diffs from the earlier headless-GUI-fix task).

## D-H. Regression test results

| Test | Result |
| --- | --- |
| D. Test M (final-origin retrace) | **PASS** |
| E. Test N (origin/Nest handoff gap) | **PASS** |
| F. Test O (oscillation detection) | **PASS** (reacquisition fires at the configured bound, deterministically) |
| G. Test P (route reacquisition resumes WM) | **PASS** (WM retrace resumes on the next-older breadcrumb; C1 fallback does not permanently replace it) |
| H. Test Q (no global navigation) | **PASS** (no ground truth, map, planner, shortest path, or RNG in the new code) |

## I. Acceptance A-L results

**All PASS**, re-run after the correction (not copied from prior labels):
`tests/validate_c2_working_memory.py` (A-J) — PASS;
`tests/validate_condition_isolation.py` — PASS;
`tests/validate_baseline_termination_architecture.py` (K/L-adjacent) — PASS;
`tests/validate_c1_all_depleted_termination.py` (L) — PASS.

## J. C1 regression result

**C1 behavioral mismatch = 0.** Fresh 300 s run (seed `2118334751`,
`SWARM_EXPERIMENT_MODE=baseline`, i.e. `working_memory_enabled=False`)
compared against the frozen `2cc0275` reference: `swarm_trajectory.csv`
(9000 rows) and `swarm_events.csv` (408 rows) identical on every column;
`swarm_summary.json` differs only by the addition of the new, always-zero
`working_memory_route_reacquisitions` field (additive schema, not a
behavioral change — same treatment as the other `working_memory_*` fields
already accepted in `tests/LOGGER_EQUIVALENCE_TEST_K_REPORT.md`). The F3/F4
correction is confirmed gated to `working_memory_enabled=True`; it does not
silently alter C1.

## K. DEV01 corrected result

Seed `2118334751`, 3600 s, `EXIT:0`, `TIME_LIMIT_REACHED`, VALID.
**Return attempts = 4, Nest reaches = 1** (was 2), failed = 3.

- Scout0/Trip1: **SUCCESS** (1186.4 s, was 626.0 s — slower but still
  succeeds).
- Scout0/Trip2: **FAILED** (was SUCCESS at 650.8 s). Now runs the full
  1781.4 s to TIME_LIMIT. Cycle-origin is 0.028 m from the true Nest
  (i.e. essentially exact), but the Scout's closest approach during the
  whole episode was 2.257 m from that origin — a **new, non-convergent
  wandering pattern** (9 route-reacquisitions fired, bounding box 7.15 m,
  0 depletion). This is a regression from success to failure.
- Scout1/Trip1: **FAILED** (`ROBOT_DEPLETED` at 2645.9 s, was 1671.3 s).
  14 route-reacquisitions fired; closest approach to own origin 1.849 m
  (never converged). No frozen-position deadlock signature (bbox 6.14 m).
- Scout2/Trip1: **FAILED** (`TIME_LIMIT_REACHED`, was also
  `TIME_LIMIT_REACHED`). 10 route-reacquisitions fired; this Scout's own
  cycle-origin is 1.499 m from the true Nest (see Part L); closest
  approach to its own origin was 2.094 m (never converged either).

## L. DEV02 corrected result

Seed `920265301`, 3600 s, `EXIT:0`, `TIME_LIMIT_REACHED`, VALID.
**Return attempts = 3, Nest reaches = 0** (unchanged) — **but the three
failures are no longer the same failure mode as before.**

- **Scout2/Trip1** (previously the clearest F4 case: wandered 271.8 m,
  ended 9.06 m from origin, `ROBOT_DEPLETED`): now reaches **0.004 m** from
  its own cycle-origin (essentially perfect WM-guided final approach; 0
  route-reacquisitions needed) and **no longer depletes** (energy 0.60
  remaining at TIME_LIMIT). It fails only because that origin — this
  Scout's own mission-start position — is itself **1.499 m from the true
  Nest** (verified against the Nest position recorded at two independent
  `NEST_REACHED` events across DEV01/DEV03: canonical Nest ≈ `(1.101,
  1.027)`; Scout2's mission-start position is `(2.6, 1.0)`). This is a
  **pre-existing geometric fact about the fixed Scout start layout**
  (Scout0 starts 0.105 m from Nest, Scout1 0.699 m, Scout2 1.499 m — a
  0.8 m row spacing), not something F3/F4 created. It was invisible before
  because the F4 defect always intervened first.
- **Scout1/Trip1**: still fails, but with only 1 route-reacquisition
  (much less thrashing than most other failures) and closest approach to
  its own origin of 1.279 m — the origin itself is 0.699 m from Nest, so
  even a fully-converged retrace would not have reached the 0.12 m Nest
  radius on its own.
- **Scout0/Trip1**: still fails, 18 route-reacquisitions (the most in the
  dataset), closest approach to its own origin 2.224 m — despite this
  Scout's own origin being only 0.105 m from Nest. This is the clearest
  case of the new non-convergent-wandering pattern with no origin-gap
  confound.

**DEV02 0/3 is explained by two distinct, already-diagnosed-separately
causes — not by a recurrence of F3 or F4:** Scout2 = pure origin-not-Nest
geometry (not a WM defect); Scout0 and Scout1 = the new non-convergent
route-reacquisition-heavy wandering pattern (see Part N).

## M. DEV03 corrected result

Seed `652974033`, 3600 s, `EXIT:0`, `TIME_LIMIT_REACHED`, VALID.
**Return attempts = 4** (was 9 — far fewer cycles completed because each
return now takes much longer), **Nest reaches = 1** (was 6), failed = 3.

- Scout0/Trip1: **SUCCESS** (75.6 s, materially unchanged from before).
- Scout2/Trip1: **FAILED** — same pattern as DEV02's Scout2: reaches
  **0.006 m** from its own origin (0 route-reacquisitions needed), no
  longer depletes (energy 0.48 remaining), fails purely because its own
  origin is 1.499 m from the true Nest (same geometric fact as Part L).
- Scout1/Trip1: **FAILED** (was SUCCESS at 1088.8 s). 6 route-
  reacquisitions; closest approach to own origin 1.430 m (origin itself
  0.699 m from Nest — a mix of non-convergence and origin-gap).
- Scout0/Trip2: **FAILED** (was SUCCESS at 297.2 s). Origin is 0.028 m
  from true Nest (essentially exact), but closest approach was 2.739 m —
  another clean example of the new non-convergent-wandering pattern with
  no origin-gap confound.

## N. Failed Return root-cause distribution after correction

9 failed episodes across DEV01-03. Re-classified with the same rigor as
the original analysis, cross-checking distance to each Scout's *own*
recorded cycle-origin against distance to the *true* Nest position:

| Category | Count | Episodes |
| --- | ---: | --- |
| **F3 (original definition: frozen-position periodic deadlock)** | **0** | none — no episode shows a static bounding box or a repeating position/action cycle anymore |
| **F4 (original definition: WM permanently abandons a still-valid target)** | **0** | none — `WM_ROUTE_REACQUIRE`/WM-guided actions are present through to the end of every episode; no episode shows a permanent, unrecovered switch to untargeted `RETURN_LOCAL_*` |
| **F5 — origin-not-Nest geometry (pre-existing, not a WM defect)** | 2 | DEV02_Scout2 (WM converges to 0.004 m of its own origin; origin is 1.499 m from Nest), DEV03_Scout2 (0.006 m; 1.499 m) |
| **New pattern — non-convergent route-reacquisition wandering** (not yet root-caused to a specific code defect; see Part O) | 7 | DEV01_Scout2, DEV01_Scout1, DEV01_Scout0_Trip2, DEV02_Scout1, DEV02_Scout0, DEV03_Scout1, DEV03_Scout0_Trip2 |

## O. F3 recurrence count

**0.** The precise, evidenced defect from the root-cause analysis — a
bit-for-bit repeating position/heading/sensor state with a measurable
period (14.8 s in the clearest original case) and near-zero bounding box
— does not appear in any of the 9 corrected-run failures. Bounding boxes
for all 9 range 3.2-9.5 m (vs. 1.9-3.8 m for the *original* F3 cases),
and `WM_ROUTE_REACQUIRE` fires and visibly changes the active target in
7 of 9 cases. **However**, a *different*, not-yet-root-caused pattern is
now visible in those same 7 cases: the Scout repeatedly reacquires a new
target (1-18 times per episode) without ever converging to within even a
few meters of its own recorded origin. This is reported in Part N/Q as a
distinct, open finding — **it is not a recurrence of the specific F3
mechanism that was fixed**, and per the Stop Rule it has not been patched.

## P. F4 recurrence count

**0.** No episode shows WM silently and permanently switching to the
untargeted C1 stateless branch while a valid single-entry target still
exists. The two cases that most closely resemble the original F4 scenario
(DEV02_Scout2, DEV03_Scout2) now demonstrate the corrected behavior
working essentially perfectly: WM converges to within 0.004-0.006 m of the
origin with 0 route-reacquisitions needed. Their remaining failure is Part
L's origin-not-Nest geometry, not a recurrence of F4.

## Q. Old-vs-corrected DEV comparison

Full table: [tests/C2_RETURN_CORRECTION_DEV_COMPARISON.csv](C2_RETURN_CORRECTION_DEV_COMPARISON.csv).
Summary:

| | Old | Corrected |
| --- | ---: | ---: |
| Total Return episodes (3 DEVs) | 16 | 11 |
| Nest reaches | 8 | 2 |
| `ROBOT_DEPLETED` failures | 3 | 1 |
| Scouts previously stuck in frozen-position deadlock | 5 episodes | 0 |
| Scouts previously showing permanent WM abandonment (F4) | 2 episodes | 0 |
| `working_memory_prunes` (aggregate, all 9 scouts) | 1043 | 32 |
| Total distance travelled (aggregate, all 9 scouts) | 2183.3 m | 672.7 m |

**Interpretation, using evidence only (no invented causality):** the
correction did what it was scoped to do — it eliminated the frozen-
position deadlock and the silent-abandonment-of-a-valid-target defect,
and in the process both reduced total distance travelled by ~69% in
aggregate and stopped 2 of 3 depletion failures entirely. It did **not**
increase the Nest-reach count; in fact the raw count fell, primarily
because (a) two failures are now explained by a pre-existing geometric
fact (origin ≠ Nest for two of three Scouts' first cycle) that was
previously masked by F4 always triggering first, and (b) a newly-visible
non-convergent wandering pattern now accounts for 7 of 9 remaining
failures, extending several individual Return durations well beyond what
they took (successfully or not) before the correction. Fewer total cycles
were completed in the fixed 3600 s horizon as a direct consequence.

## R. 3600 s validity

**Confirmed for all three corrected DEV runs**: `EXIT:0`,
`engineering_status: COMPLETED`, `experimental_validity: VALID`,
`mission_outcome: TIME_LIMIT_REACHED` for all three, full output files
present (`swarm_summary.json`, `metadata.json`, `state_transitions.csv`,
`working_memory_events.csv`, `swarm_trajectory.csv`, `swarm_events.csv`,
`robot_energy_timeline.csv`, `nest_energy_timeline.csv`). No hang, no
crash, no NaN. This satisfies Step 8 (DEV01-03 already covers the
required single 3600 s corrected-C2 long-run check).

## S. Known remaining limitations

1. **Origin-not-Nest geometry** (Part L): for a Scout's first cycle,
   `CycleWorkingMemory`'s local origin is the Scout's own mission-start
   position, which is only exactly the Nest for Scout0 (0.105 m offset);
   Scout1 starts 0.699 m away and Scout2 1.499 m away. A WM retrace that
   converges perfectly to that origin cannot, by itself, reach the 0.12 m
   Nest confirmation radius for Scout1/Scout2's first cycle. This is a
   pre-existing property of the fixed Scout start layout and the
   cycle-origin design, not something this correction introduced or is
   scoped to fix — it was simply invisible before because F4 always
   intervened first.
2. **Non-convergent route-reacquisition wandering** (Parts N/O/Q): 7 of 9
   remaining failures show the Scout repeatedly reacquiring new targets
   without net convergence toward origin, even when the origin is
   genuinely close to the true Nest (e.g. DEV01_Scout0_Trip2 and
   DEV03_Scout0_Trip2, both 0.028 m origin-Nest offset, neither
   converging). This is evidenced but **not root-caused to a specific
   line of code** — candidate explanations not yet distinguished by
   evidence include: the bounded stuck-detector threshold
   (`return_stationary_turn_limit`, reused from a rotation-only C1
   heuristic) firing on breadcrumbs that are difficult-but-eventually-
   reachable rather than genuinely unreachable; repeated reacquisition
   selecting a sequence of breadcrumbs whose recorded outbound path was
   itself long/indirect; or a combination. Per the Stop Rule, this has
   been reported, not patched, and no further tuning was attempted.
3. **Overall Return throughput decreased** within the fixed 3600 s
   horizon (fewer completed cycles, fewer Nest reaches) even though
   per-episode distance travelled and depletion both improved in
   aggregate — a direct, expected consequence of WM now holding
   navigation authority for longer per episode instead of yielding early
   to the untargeted (but occasionally luckier) C1 fallback.
4. Only the 3 canonical development seeds were tested (as instructed);
   no statement is made about behavior at other seeds.

## T. Recommendation

**Further diagnosis required before a freeze decision** — not because the
two requested defects are unfixed (they are conclusively fixed, with
direct before/after evidence: 0/9 frozen-position deadlocks, 0/9 silent
target abandonments), but because this correction has **exposed two new,
evidenced-but-not-yet-root-caused phenomena** (origin-not-Nest geometry;
non-convergent route reacquisition) that materially reduce overall Return
reliability within the research horizon, and neither was in scope for this
task to resolve. Per the Stop Rule, no further automatic tuning was
attempted. A deliberate decision is needed on: (a) whether the
origin-not-Nest gap for Scout1/Scout2's first cycle is an acceptable,
documented property of the C2 design or needs its own targeted correction;
and (b) whether the non-convergent wandering pattern needs a dedicated
root-cause investigation (analogous to the original F3/F4 analysis)
before Research Freeze.

---

**C2 RETURN CORRECTION: FURTHER DIAGNOSIS REQUIRED**
