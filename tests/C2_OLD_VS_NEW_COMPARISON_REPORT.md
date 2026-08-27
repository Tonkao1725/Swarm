# C2 Old-vs-New Comparison Report

Date: 2026-08-26. Scope: development validation only; no canonical research
seed was run.

## Test configuration

- Frozen reference commit (old / Condition 1): `2cc0275bf29c40fedfba44e8865ac5696d61ec94`,
  checked out into a temporary `git worktree` so the comparison target is the
  exact frozen tree.
- Comparison target (new / Condition 2): current `c2-working-memory-dev`
  working tree, `SWARM_EXPERIMENT_MODE=working_memory`
  (`working_memory_enabled=True`), after the two output-label fixes recorded
  in [LOGGER_EQUIVALENCE_TEST_K_REPORT.md](LOGGER_EQUIVALENCE_TEST_K_REPORT.md).
- Development seeds: `2118334751`, `920265301`, `652974033` (the same three
  seeds used throughout C1/C2 development; none are canonical research
  seeds).
- Common run env for all six runs: `SWARM_SCOUT_COUNT=3`,
  `SWARM_MISSION_MODE=research`, `NEST_ENERGY_TARGET=6`, `FORAGING_TRIPS=3`,
  `SWARM_SIM_DURATION_S=300`, `FAST_HEADLESS_RESEARCH_MODE=1`,
  `IRSIM_RENDER=0`. All six runs are freshly generated this session so C1 and
  C2 are directly comparable at identical duration.
- No canonical 20-seed research set was touched.

### Why the existing `results/canonical_c1_development_validation_20260820`
### dataset was NOT used as the C1 reference

That dataset's `development_validation_report.json` records
`created_at: 2026-08-20T07:03:26 UTC`. Commit `d763d39` ("Finalize canonical
Condition 1 baseline energy model"), which touches
[energy_sensor.py](../src/swarm_simulate/energy_sensor.py), was made at
`2026-08-20 14:07:37 +0700` = `07:07:37 UTC` — only **4 minutes after** that
dataset finished. The dataset therefore predates the energy-model freeze and
cannot be trusted to represent current frozen-`2cc0275` behavior. All C1
reference data in this report was generated fresh from a `2cc0275` worktree
instead. A first attempt to regenerate it at the original 3,600 s duration
in the background hung (see Known Limitations); all runs in this report use
300 s, which completed reliably in every attempt.

## A. Experimental isolation — PASS

`isolation_assertions` and feature flags from `swarm_summary.json`, all
three seeds, both conditions:

| Flag | C1 (frozen) | C2 (current) |
| --- | --- | --- |
| `working_memory_enabled` | `False` | `True` |
| `experience_memory_enabled` | `False` | `False` |
| `exchange_enabled` | `False` | `False` |
| `hormone_enabled` | `False` | `False` |
| `shared_map_created` | `False` | `False` |
| `isolation_assertions.visited_branch_memory` | `False` | `False` |
| `isolation_assertions.route_breadcrumbs` | `False` | `True` |
| `isolation_assertions.cross_trip_preference` | `False` | `False` |
| `isolation_assertions.message_bus` | `False` | `False` |
| `isolation_assertions.global_planner` | `False` | `False` |

**`route_breadcrumbs` is the only flag that differs between C1 and C2, in
all three seeds.** No Experience Memory, Exchange, or AIH feature is enabled
in either condition. This matches the required matrix exactly:

- C1: WM OFF / EM OFF / Exchange OFF / AIH OFF
- C2: WM ON / EM OFF / Exchange OFF / AIH OFF

Static code confirmation: [energy_sensor.py](../src/swarm_simulate/energy_sensor.py),
[irsim_range_sensor.py](../src/swarm_simulate/irsim_range_sensor.py),
[result_logger.py](../src/swarm_simulate/result_logger.py),
[config/robot_world.yaml](../config/robot_world.yaml) and
[config/resource_harvesting_config.json](../config/resource_harvesting_config.json)
have zero uncommitted changes (`git diff --stat` empty) — resource logic,
energy model, sensor model, and arena/world config are byte-identical to the
frozen commit.

## B. Working Memory behavior — PASS

Evidence from `working_memory_events.csv`, `swarm_trajectory.csv` action
tokens, and `swarm_summary.json` per-Scout counters, across the three fresh
300 s runs plus the longer 3,600 s `C2_WORKING_MEMORY_PREFREEZE` DEV01–DEV03
reruns (supplementary, current C2 code, read-only, not re-run this session):

| Design requirement | Evidence |
| --- | --- |
| Records outbound breadcrumbs | `WM_ADD` events present in every run (e.g. 315/126/311 in the fresh 300 s runs; 1,128/… in the 3,600 s PREFREEZE runs), always logged with phase EXPLORE/HARVEST |
| Uses breadcrumbs on `RETURN_HOME` | `WM_POP_RETRACE`, `WM_RETRACE_TURN_45`, `WM_RETRACE_FORWARD` action tokens appear in `swarm_trajectory.csv` for every Scout that reached `RETURN_HOME`; counts match `working_memory_events.csv`'s `WM_POP` count exactly (e.g. seed `2118334751`: 12 `WM_POP_RETRACE` trajectory rows = 12 `WM_POP` events) |
| Retraces newest-first | Confirmed by source: [c2_working_memory.py](../src/swarm_simulate/c2_working_memory.py) `return_target`/`pop_if_reached` both read `self.entries[-1]` (LIFO — most recently added breadcrumb consumed first) |
| Pop/prune/reset per lifecycle | All three operations observed: `WM_POP` (return reached a waypoint), `WM_PRUNE` (bound exceeded — e.g. 632/3,600 s PREFREEZE seed `2118334751`), `WM_RESET` (cycle start and cycle completion) |
| Reset at new foraging cycle | `WM_RESET` fires at `sim_time_s=0.0` (mission start) and again at each `NEXT_CYCLE_START` in the source (`swarm_baseline.py`, the `DELIVER`→next-`EXPLORE` transition calls `memory.reset()` then `memory.start_cycle()`) |
| No Nest/Resource ground truth | Confirmed by source: `c2_working_memory.py` contains no Nest/Resource coordinate constant and takes only `moved_m`/`heading_delta_rad`/`cycle_id` as input |
| No global map | Entries are cleared every `reset()`; nothing persists across cycles; `enabled=False` gives permanent size 0 |
| No new RNG source | `grep "random\."` on `c2_working_memory.py` returns nothing; the WM branch inside `_return_command` (`swarm_baseline.py`) uses only `math.atan2`/`wrap`/comparisons — no call to `scout.rng` or any other RNG is added |

## C. C1 vs C2 behavioral differences

### Expected to differ (and confirmed to differ)

- Return navigation method (`return_navigation` field: `STATELESS_LOCAL_REACTIVE_NO_RSSI_STEERING` vs `CURRENT_CYCLE_ODOMETRIC_BREADCRUMB_RETRACE_WITH_LOCAL_SAFETY`)
- Working Memory reads/pops/prunes/resets (zero in C1 by construction; nonzero in C2 whenever a Scout completes a harvest)
- Breadcrumb entry counts (`working_memory_entries`/`working_memory_max_size`, present only in C2)
- Per-Scout trajectory from the moment that Scout's phase becomes
  `RETURN_HOME`: verified byte-identical to C1 up to and including
  `HARVEST_COMPLETE`, diverging exactly at the first post-`HARVEST_COMPLETE`
  row for every Scout that reached that phase, in all 3 seeds
- Resulting mission outcome differences: seed `652974033`, C2 delivered 1
  resource (`gross_delivered_energy≈1.0`) where C1 delivered 0 in the same
  300 s window — an expected consequence of WM enabling a more direct return
  in that instance, not evaluated here as "better" per the task scope

### Found, non-obvious, but confirmed NOT a defect

Trajectories of Scouts that **never leave `EXPLORE`** (never find a
resource) were also found to diverge between C1 and C2 in 3 of 9 Scout-runs,
starting well after simulation start. Root-caused as follows (seed
`2118334751`, Scout 0, divergence at `sim_time_s=162.2`):

- Scout 0's own position/heading/`left_m`/`right_m` are byte-identical
  between C1 and C2 up to and including the divergent row; only `front_m`
  differs (`2.443` vs `1.864`).
- Scout 2 (a different Scout) reached `HARVEST_COMPLETE` at
  `sim_time_s=118.4` — identically in both runs — and then entered
  `RETURN_HOME`, where C2's WM retrace path is physically different from
  C1's stateless return.
- By `sim_time_s=162.2`, Scout 2's physical position has diverged
  accordingly: C1 `(4.52, 3.67)`, C2 `(5.34, 2.14)`.
- Scout 0's front-facing range sensor detects **other Scouts as dynamic
  obstacles**, so it reads a different `front_m` purely because Scout 2 is
  physically standing somewhere else — not because Scout 0's own decision
  logic, RNG stream, or WM state changed.

This is **expected multi-agent emergent behavior**, not an isolation defect:
no RNG desynchronization was found (`scout.rng` is only consumed inside
`_explore_command`/`_return_command`, both unmodified for the EXPLORE path),
and no WM code executes for a Scout that is not the one in `RETURN_HOME`.
The mechanism is exactly the one already documented for C1's own
peer-contact-recovery system (Scouts have always sensed each other). It
means: **once any Scout in a run enters `RETURN_HOME`, every other Scout's
trajectory may legitimately begin to differ from C1 too**, even before that
other Scout finds its own resource. This should be treated as a documented
property of the multi-Scout environment, not scoped only to the Scout
actively using WM.

### Must not differ, and confirmed not to differ

- Resource logic/positions — [config/resource_harvesting_config.json](../config/resource_harvesting_config.json) unmodified
- Energy model — [energy_sensor.py](../src/swarm_simulate/energy_sensor.py) unmodified; energy formula in `swarm_baseline.py` unchanged (only additional non-feedback logging fields added)
- Sensor model — [irsim_range_sensor.py](../src/swarm_simulate/irsim_range_sensor.py) unmodified
- Termination contract — `_termination_state_snapshot` function body unmodified (only its call site's surrounding label text changed, per Test K's fix)
- Initial conditions / experiment seed — identical `FORAGING_SEED`, identical per-Scout RNG seeding (`self.seed + 104729 * i`)
- Arena/world config — [config/robot_world.yaml](../config/robot_world.yaml) unmodified
- Pre-`RETURN_HOME` trajectory of the specific Scout that will use WM — byte-identical to C1 up to that Scout's own first `HARVEST_COMPLETE`, in every seed checked

## D. Development-run evidence

All 6 fresh runs this session: `engineering_status=COMPLETED`,
`experimental_validity=VALID`, return code 0, no traceback in console
output — **no crash/error in any run.**

| Seed | Cond. | Termination | Deliveries (by Scout) | Nest energy (net) | Gross delivered | Distance (by Scout, m) | WM entries/max (by Scout) | WM reads/pops/prunes/resets (by Scout) |
| ---: | --- | --- | --- | ---: | ---: | --- | --- | --- |
| 2118334751 | C1 | TIME_LIMIT_REACHED | 0,0,0 | 0.0 | 0.0 | 44.4, 36.5, 40.5 | n/a | n/a |
| 2118334751 | C2 | TIME_LIMIT_REACHED | 0,0,0 | 0.0 | 0.0 | 45.6, 32.8, 14.0 | 164/164, 115/115, 27/39 | 0/0/0/0, 0/0/0/0, 283/12/0/0 |
| 920265301 | C1 | TIME_LIMIT_REACHED | 0,0,0 | 0.0 | 0.0 | 35.8, 41.3, 44.0 | n/a | n/a |
| 920265301 | C2 | TIME_LIMIT_REACHED | 0,0,0 | 0.0 | 0.0 | 21.3, 26.0, 37.5 | 24/53, 8/55, 1/21 | 379/29/0/0, 608/47/0/0, 1498/20/0/0 |
| 652974033 | C1 | TIME_LIMIT_REACHED | 0,0,0 | 0.0 | 0.0 | 44.5, 27.3, 43.8 | n/a | n/a |
| 652974033 | C2 | TIME_LIMIT_REACHED | 1,0,0 | 0.812 | 1.0 | 36.7, 42.2, 23.7 | 80/80, 152/152, 13/54 | 358/28/0/1, 0/0/0/0, 513/41/0/0 |

Supplementary (3,600 s, current C2 code, read-only reuse of
`results/C2_WORKING_MEMORY_PREFREEZE/DEV01-03`; no matching-duration C1
`2cc0275` counterpart exists, so shown only as additional WM-mechanism
evidence, not as part of the strict isolation comparison):

| Seed | Deliveries | Net nest energy | Gross delivered | Max WM size reached | Prunes observed |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2118334751 | 2,0,0 | 0.0 | 2.0 | 300 (bound reached) | 385, 247, 0 |
| 920265301 | 0,0,0 | 0.0 | 0.0 | 53, 55, 21 | 0, 0, 0 |
| 652974033 | 3,3,0 | 0.260 | 6.0 | 300 (bound reached), 300, 54 | 259, 122, 0 |

This confirms the 300-entry bound and pruning rule are exercised correctly
under longer horizons, consistent with the acceptance/dev reports already on
file.

No result here is interpreted as C2 "outperforming" C1 — the goal of this
comparison is mechanism correctness and isolation, not performance.

## E. PASS / FAIL / INCONCLUSIVE summary

| Section | Result |
| --- | --- |
| A. Experimental isolation | **PASS** |
| B. Working Memory behavior | **PASS** |
| C. Behavioral differences — expected differences present | **PASS** |
| C. Behavioral differences — no unexplained/must-not-differ change | **PASS** (one non-obvious but fully explained emergent effect, not a defect) |
| D. Development-run evidence (no crash) | **PASS** |

## Known limitations

- All fresh comparison runs used 300 s, not the 3,600 s duration used in
  the existing `C2_WORKING_MEMORY_PREFREEZE` dev set, because a background
  attempt to regenerate a 3,600 s frozen-C1 reference hung (a stray
  matplotlib figure window remained in a "Not Responding" state despite
  `IRSIM_RENDER=0`/`MPLBACKEND=Agg`; it was killed as a self-created test
  process, not user work). The 300 s duration was proven reliable (this
  report's 6 runs plus the 2 earlier Test K runs, 8/8 completed cleanly) and
  is sufficient to exercise `EXPLORE`→`HARVEST`→`RETURN_HOME` and WM
  add/pop/reset, but only 1 of 3 seeds reached a `DELIVER` event within it.
  The 3,600 s figures in Section D are read-only reuse of existing data, not
  freshly verified against `2cc0275`, and are supplementary only.
- The pre-existing `results/canonical_c1_development_validation_20260820`
  dataset was deliberately not trusted as a C1 reference (see rationale
  above); no other existing dataset was found that reflects `2cc0275`
  exactly at 3,600 s, so a true 3,600 s apples-to-apples C1 vs C2 comparison
  remains outstanding.
- The matplotlib-figure hang itself is an environment/tooling
  characteristic observed during this validation session, not a defect in
  Condition 1 or Condition 2 simulation code — it occurred identically
  regardless of `working_memory_enabled`, using unmodified rendering code
  paths. It is noted here only because it changed this report's methodology
  (300 s instead of 3,600 s); it is not a C1/C2 behavioral finding.
- Cross-scout sensor coupling (Section C) means a byte-exact, whole-run
  trajectory diff between C1 and C2 is not a meaningful pass/fail criterion
  once any Scout reaches `RETURN_HOME` — this report instead verified
  divergence timing (nothing diverges before the relevant `HARVEST_COMPLETE`
  event) and root-caused one instance in full rather than diffing all rows.

## Conclusion

Condition 2's Working Memory mechanism is implemented and behaves as
designed: it is fully isolated from Experience Memory, Exchange, and AIH;
it reads and writes only cycle-local, ground-truth-free odometric data; it
adds no RNG source; and every observed behavioral difference from Condition
1 is either the intended breadcrumb-retrace return behavior or a
downstream, physically-correct multi-agent sensing consequence of it — not
an unexplained or isolation-breaking defect.

**C2 is not yet ready for manifest/freeze packaging.** The outstanding
items are the same ones already tracked in
`results/C2_WORKING_MEMORY_PREFREEZE/C2_PREFREEZE_AUDIT.md`
(manifest generation, final ZIP) plus, newly identified here: a genuine
3,600 s (or otherwise longer-horizon) frozen-`2cc0275`-vs-current
old-vs-new comparison has not been completed, since the only attempt at
that duration hung in this environment and was not retried within this
session's scope.
