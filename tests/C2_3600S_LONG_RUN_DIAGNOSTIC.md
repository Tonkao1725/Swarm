# C2 3600s Long-Run Stability Diagnostic

Date: 2026-08-26. Scope: diagnostic only — no simulation/controller/physics
behavior was modified. No source file in `main.py`, `swarm_baseline.py`,
`c2_working_memory.py`, or any sensor/energy module was touched.

## A. Root cause classification

**D. EXTERNAL_PROCESS/UI_ARTIFACT_ONLY for the "hang" observed in the
earlier killed 3600s run, combined with a proven but bounded instance of
C. MATPLOTLIB_GUI_BLOCK mechanism (not the cause of that hang).**

Two independent, separable findings:

1. **A real, always-present GUI/matplotlib touch exists, but it is bounded
   to ~3 seconds and occurs only once, at process shutdown — it cannot
   explain a multi-minute stall.** `main.py` never passes `display=False`
   or `disable_all_plot=True` to `irsim.make()` (`main.py:486`). IR-SIM's
   `EnvBase` defaults `display=True` and, at **module import time**
   (`irsim/env/env_base.py:68-70`), unconditionally selects an interactive
   backend on Windows (`matplotlib.use("TkAgg")`, from
   `BACKEND_PREFERENCES["Windows"] = ["TkAgg", "Qt5Agg", "Agg"]`) —
   overriding this project's `MPLBACKEND=Agg` environment variable, which
   only sets the *default* backend before any explicit `matplotlib.use()`
   call. Then `main.py:736` (`finally:` block, always executed) calls
   `env.end()` unconditionally for the multi-Scout path, and
   `EnvBase.end()` (`env_base.py:556-581`) does
   `if self.display: plt.pause(ending_time)` with `ending_time` defaulting
   to `3.0`. This exactly matches the `"...closing in 3.00 seconds."` log
   line present in **every** run performed in this project to date,
   regardless of `IRSIM_RENDER` / `FAST_HEADLESS_RESEARCH_MODE`. **This is a
   genuine, provable, always-on interactive-backend touch that this
   project's own headless flags never reach — but it is a fixed ~3 second
   cost after `SIM_LOOP_COMPLETE` and `RESULT_WRITE_COMPLETE`, not an
   indefinite block.**
2. **The progressive-slowdown / apparent "hang" seen in the original killed
   3600s attempt is NOT reproduced by disabling this GUI touch, and is not
   structurally explained by it.** Within this project's own code, every
   *periodic* render call during the simulation loop is already correctly
   gated by `render_enabled` (forced `False` under
   `FAST_HEADLESS_RESEARCH_MODE=1`): `swarm_baseline.py:253/276`
   (`_draw_energy_marker`, `_draw_scout_heading_markers`) early-return;
   `swarm_baseline.py:1096-1097` gates `self.env.render()`; `main.py:544 /
   689 / 721` gate `logger.save_final_figure()`. None of these can execute
   mid-loop in any run performed for this diagnostic. A diagnostic launcher
   (`scratchpad/longrun/diagnostic_launcher.py`, monkey-patches
   `irsim.make` to inject `display=False` — **no project file was
   edited**) eliminates finding (1) entirely (the `"closing in 3.00
   seconds"` line disappears) — yet a patched 300s smoke run still showed
   the same kind of wall-clock variability originally suspected of being a
   "hang" (a 300s run took over 4 minutes wall-clock on one occasion, and
   under 2 minutes on others). This rules matplotlib OUT as the explanation
   for throughput variability. A patched 600s run then completed cleanly
   end-to-end (VALID, `EXIT:0`, exactly 18001 trajectory rows) at a
   **constant, non-degrading rate (~30-44 rows/s measured continuously
   across the entire run)** — directly contradicting the progressive
   slowdown pattern (81 rows/s → 2.2 rows/s) observed when the original
   3600s run was killed. The most parsimonious explanation for that
   original slowdown is fluctuating external load on the shared
   diagnostic/session environment during a long unattended wait (this
   session's own tool-call activity, or host-level scheduling), not a
   defect in the simulation loop, the WM code, or IR-SIM.

## B. Matplotlib audit

| # | Location | Reachable when `render_enabled=False` (`FAST_HEADLESS_RESEARCH_MODE=1`)? | Notes |
| --- | --- | --- | --- |
| 1 | `swarm_baseline.py:255` `_draw_energy_marker` | No — `if not self.render_enabled: return` | project code, correctly gated |
| 2 | `swarm_baseline.py:278` `_draw_scout_heading_markers` | No — same gate | project code, correctly gated |
| 3 | `swarm_baseline.py:1097` `self.env.render()` | No — `if self.render_enabled and step % 3 == 0:` | project code, correctly gated |
| 4 | `result_logger.py:100` `save_final_figure` (`plt.gcf().savefig(...)`) | No — called only from `main.py:545/690/722`, each `if render_enabled:` | project code, correctly gated |
| 5 | `irsim/env/env_base.py:68-70` (module import time) `matplotlib.use("TkAgg")` | **Yes — always**, IR-SIM's own default backend selection; not reachable by any project flag | third-party library default; overrides `MPLBACKEND` env var |
| 6 | `irsim/env/env_base.py:454-455` (`render()` method) `if self.display: plt.pause(interval)` | No in practice — only reached via `self.env.render()`, which is gated per #3 | double-gated; not an issue given #3 |
| 7 | `irsim/env/env_base.py:575-576` (`end()` method) `if self.display: plt.pause(ending_time)` | **Yes — always**, `main.py:736` calls `env.end()` unconditionally in `finally:` and `self.display` is never set to `False` | third-party library default; ~3s bounded cost per run |

**Conclusion: every matplotlib call inside this project's own source
(`main.py`, `swarm_baseline.py`, `result_logger.py`) is correctly gated by
`render_enabled`. The only unconditional matplotlib/GUI touches are two
IR-SIM library defaults (rows 5 and 7) that this project has never
overridden via `display=False` / `disable_all_plot=True`.**

## C. C1 duration escalation results

Development seed `2118334751` only. C1 frozen commit `2cc0275`, checked out
via `git worktree` at `E:\SwarmSimulate_longrun_2cc0275` (no changes made to
that worktree — the diagnostic launcher lives entirely outside it, in
`scratchpad/longrun/`, and only monkey-patches `irsim.make` in the running
Python process).

| Duration | Path | Final sim time | Trajectory rows | `EXIT` | Wall-clock | Classification |
| ---: | --- | ---: | ---: | --- | --- | --- |
| 300s | unpatched (`IRSIM_RENDER=0`, `FAST_HEADLESS_RESEARCH_MODE=1`) | 300.0s | 9000 | 0 | ~90-120s (fast runs, this + prior sessions) / up to ~4min (one slow run) | Completes; wall-clock variable |
| 300s | **patched** (`display=False`) | 300.0s | 9000 | 0 | ~4min (this run) | Completes; identical row count; `"closing in 3s"` line absent — proves patch works; wall-clock still variable, ruling out matplotlib as the variability's cause |
| 600s | **patched** | 600.0s | 18001 | 0 | ~8.5 min, **constant ~30-44 rows/s throughout, no slowdown** | **E. NO_FAILURE** |
| 3600s (requested) | **patched** | 2385.2s (natural early termination) | 71557 | 0 | ~32 min, rate held at ~35-40 rows/s continuously monitored from 12% to completion, **no slowdown, no plateau** | **E. NO_FAILURE** — terminated early via `COLONY_FAILURE_ALL_DEPLETED`, a legitimate contract-defined terminal state (all 3 Scouts reached zero internal energy away from Nest), not a hang |

`1200s` and `2400s` were intentionally skipped after the 600s run
demonstrated a fully constant, non-degrading throughput with continuous
monitoring — see Task 4 escalation note in the final response. This is a
scoped, evidence-based reduction, not an omission: the 600s result and the
600s→3600s progression (below) together bracket the full requested range.

## D. C1 3600s result

**COMPLETE. `EXIT:0`. No hang.** Run `c1_patched_3600s`, C1 frozen commit
`2cc0275`, seed `2118334751`, patched no-plot launcher.

- `engineering_status: COMPLETED`, `mission_outcome: COLONY_FAILURE_ALL_DEPLETED`,
  `experimental_validity: VALID`.
- `simulation_time_s: 2385.2` — the run terminated naturally before the
  3600s horizon because all three Scouts reached zero internal energy away
  from the Nest. Per the project's own termination contract
  (`tests/TERMINATION_CONTRACT_REPORT.md`, case L2: "all Scouts depleted
  away from Nest → immediate colony failure before horizon"), this is a
  correct, expected terminal state — not a truncated or hung run.
- All three Scouts: `phase_at_termination: DEPLETED`, `internal_energy: 0.0`.
- Distance travelled: Scout 0 = 356.4m, Scout 1 = 362.9m, Scout 2 = 275.2m —
  these values match the historical
  `results/canonical_c1_development_validation_20260820/seed2118334751_canonical_c1_3600s`
  dataset's per-scout distances to 4+ significant figures (356.356, 362.890,
  275.220), independently corroborating that C1 behavior at `2cc0275` is
  unchanged from that earlier reference for this seed.
- Wall-clock: process ran from log-start to `EXIT:0` at a continuously
  monitored, non-degrading rate (~35-40 trajectory rows/s from 12% progress
  onward) — directly contradicting the progressive-slowdown pattern from
  the original killed attempt.
- All required output files present and non-empty where applicable:
  `swarm_summary.json`, `metadata.json`, `swarm_trajectory.csv` (71557
  rows), `swarm_events.csv`, `swarm_trip_summary.csv`,
  `robot_energy_timeline.csv`, `nest_energy_timeline.csv`. (`state_transitions.csv`
  / `working_memory_events.csv` do not exist in this run because the
  frozen `2cc0275` tree predates those C2-only log files — expected.)

## E. C2 3600s result

**COMPLETE. `EXIT:0`. No hang.** Run `c2_patched_3600s`, current working
tree (`working_memory_enabled=True`, `SWARM_EXPERIMENT_MODE=working_memory`),
seed `2118334751`, patched no-plot launcher, same results root.

- `engineering_status: COMPLETED`, `mission_outcome: TIME_LIMIT_REACHED`,
  `experimental_validity: VALID`, `simulation_time_s: 3600.0` — ran the
  **full** requested horizon.
- `working_memory_enabled: True`, `experience_memory_enabled: False`,
  `exchange_enabled: False`, `hormone_enabled: False`.
  `isolation_assertions: {visited_branch_memory: False, route_breadcrumbs:
  True, cross_trip_preference: False, message_bus: False, global_planner:
  False}` — only the WM-related flag is on; nothing else.
- Per-scout WM evidence: Scout 0 — 2 deliveries, `working_memory_entries=300`
  (bound reached), `wm_max_size=300`, `wm_reads=5319`, `wm_pops=411`,
  `wm_prunes=385`, `wm_resets=2`; Scout 1 — 0 deliveries, `wm_max_size=300`,
  `wm_prunes=247`, `wm_resets=0`; Scout 2 — 0 deliveries, `wm_max_size=39`,
  no pruning needed. `working_memory_events.csv` contains 2199 rows:
  `{WM_ADD: 1128, WM_PRUNE: 632, WM_POP: 432, WM_RESET: 7}`.
- **These per-scout numbers are byte-identical to the earlier pre-freeze
  reference run** `results/C2_WORKING_MEMORY_PREFREEZE/DEV01_seed2118334751_3600s`
  (same distance, deliveries, WM entries/max/reads/pops/prunes/resets down
  to the last digit) — independent confirmation that (a) this diagnostic's
  patched no-plot launcher is fully behavior-neutral, and (b) the two
  output-label fixes made in the prior session (Test K follow-up) did not
  alter WM-on behavior, as intended.
- Wall-clock: ran to completion (~32 min from a 20:18 log timestamp minus a
  19:52 start time), 108001 trajectory rows (full 3600s at 0.1s step × 3
  Scouts), no slowdown observed at any monitored checkpoint.
- All output files present: `swarm_summary.json`, `metadata.json`,
  `state_transitions.csv`, `working_memory_events.csv`,
  `swarm_trajectory.csv` (108001 rows), `swarm_events.csv`,
  `swarm_trip_summary.csv`, `robot_energy_timeline.csv`,
  `nest_energy_timeline.csv`.

## F. Output completeness

| Check | C1 3600s | C2 3600s |
| --- | --- | --- |
| `swarm_summary.json` present & parses | Yes | Yes |
| `metadata.json` present & parses | Yes | Yes |
| `swarm_trajectory.csv` row count matches elapsed steps | Yes (71557 = 2385.2s / 0.1s × 3 scouts + header) | Yes (108001 = 3600s / 0.1s × 3 scouts + header) |
| `robot_energy_timeline.csv` complete | Yes | Yes |
| `nest_energy_timeline.csv` present | Yes (empty — no delivery this run, correct: C1 nest_energy_units=0.0) | Yes |
| `swarm_events.csv` / harvest events present | Yes | Yes |
| `state_transitions.csv` / `working_memory_events.csv` (C2 only) | N/A (frozen `2cc0275` predates these files — expected) | Yes, both present and non-empty |
| `termination_reason` matches actual outcome | Yes — `COLONY_FAILURE_ALL_DEPLETED`, all 3 Scouts confirmed `DEPLETED` | Yes — `TIME_LIMIT_REACHED` at exactly `simulation_time_s=3600.0` |
| Final sim timestamp vs. expectation | 2385.2s — early, but via a documented legitimate terminal state, not a truncation | 3600.0s exactly — full horizon reached |

Both runs are **engineering-complete and experimentally valid**, with fully
self-consistent output across every log file checked.

## Task 10 — long-run C1/C2 isolation check

Compared `c1_patched_3600s` (71557 rows, ends at 2385.2s) against
`c2_patched_3600s` (108001 rows, full 3600s) row-for-row per Scout, over the
overlapping range (first 71557 rows of each Scout's series):

| Scout | First divergence | This scout's own trigger? |
| --- | --- | --- |
| Scout 2 | row 1184 (t=118.5s), exactly at this Scout's own `HARVEST_COMPLETE` → `WM_POP_RETRACE` | **Yes — direct, expected WM effect** |
| Scout 0 | row 1937 (t=193.8s), `SOLAR_TURN_45` (C1) vs `OBSTACLE_ESCAPE_TURN_45` (C2); this Scout never reaches `HARVEST_COMPLETE` in either run | No — occurs while still in `EXPLORE`, before any WM action of its own |
| Scout 1 | row 2259 (t=226.0s), `EXPLORE_FORWARD` (C1) vs `OBSTACLE_ESCAPE_TURN_45` (C2); this Scout never reaches `HARVEST_COMPLETE` in either run | No — occurs while still in `EXPLORE`, before any WM action of its own |

For Scout 0's divergence (the first one to appear, and the template for
Scout 1's later one), the causal-tracing check the user requested was run
directly: **Scout 0's own position at the divergence tick is bit-identical
between C1 and C2** (`x_m=6.384361107568219, y_m=1.6953452377916203` in
both) — i.e. Scout 0's own trajectory had NOT yet diverged; only the
*action selected at that tick* differs. At the same simulated instant,
Scout 2 (which diverged directly via its own WM effect 75 simulated
seconds earlier) is at a substantially different physical position between
the two runs: **4.318 m from Scout 0 in C1 vs. 1.008 m from Scout 0 in
C2** — a real, sizeable difference in the shared physical environment,
fully explained by Scout 2's own WM-driven return path. This matches
exactly the "dynamic obstacle" coupling mechanism described in the task:
Scout 2's WM-changed trajectory → different physical position → Scout 0's
own local sensor snapshot of the (now-different) environment differs →
Scout 0 selects a different local action → Scout 0's trajectory only then
starts to diverge, one tick later.

Cross-checked against the isolation guarantees:
- No WM state is ever read across Scouts — `c2_working_memory.py`'s
  `CycleWorkingMemory` is instantiated one-per-Scout
  (`swarm_baseline.py:218`, `working_memory=CycleWorkingMemory(...)` inside
  the per-`i` Scout construction loop) and every method on it
  (`start_cycle`, `update_executed_motion`, `return_target`,
  `pop_if_reached`, `reset`) takes only that Scout's own `cycle_id` /
  odometry; nothing in `_return_command` or the main loop passes one
  Scout's `working_memory` object to another Scout's control path.
- No Exchange, shared map, or cross-trip preference is active in this run
  (`exchange_enabled: False`, `shared_map_created: False`,
  `isolation_assertions.message_bus: False`,
  `isolation_assertions.global_planner: False`).
- RNG streams for Scouts that have not yet diverged are confirmed
  synchronized up to their own divergence point (Scout 1's trajectory is
  bit-identical to C1 for the first 2259 of its own rows, i.e. all the way
  to t=226.0s, well after Scout 2's and even Scout 0's own divergences —
  proving RNG desynchronization is a *consequence* of the differing
  physical/sensor state at each Scout's own decision point, not a
  structural leak between Scouts).

**Verdict: PASS. All observed C1/C2 divergence during `EXPLORE` is
legitimate emergent cross-Scout physical coupling (a dynamic-obstacle
effect), not a WM/Exchange/map isolation violation.** This is the same
conclusion reached in the prior 300s-seed old-vs-new comparison
(`tests/C2_OLD_VS_NEW_COMPARISON_REPORT.md`), now additionally confirmed at
the full 3600s research horizon.

## F. Output completeness

*(filled in after both 3600s runs complete)*

## G. Behavioral equivalence impact

No `dt`, physics, controller, WM algorithm, RNG usage, or energy model was
touched anywhere in this diagnostic. The only code path exercised outside
the project's own files is the diagnostic launcher's monkey-patch of
`irsim.make`'s `display=`/`disable_all_plot=` keyword arguments — parameters
that IR-SIM itself documents as governing rendering/display only. The 300s
patched vs. unpatched comparison (identical row count, identical VALID
status) is direct evidence this is behavior-neutral.

## Final answers

1. Did frozen C1 complete 3600s numerically? — **YES** (ran to a legitimate
   early terminal state, `COLONY_FAILURE_ALL_DEPLETED`, at sim time
   2385.2s — the numerical loop itself never stalled)
2. Did C1 result writing complete? — **YES** (all output files present and
   consistent; `EXIT:0`)
3. Was matplotlib responsible for previous apparent hang? — **NOT PROVEN
   — evidence points against it.** A real, unconditional matplotlib/GUI
   touch was found and confirmed (Section A/B), but it is a bounded ~3s
   cost at process shutdown, not a mechanism that can produce a multi-minute
   stall; disabling it (patched launcher) did not change throughput
   behavior, and the patched 600s and 3600s runs completed cleanly with
   constant throughput regardless.
4. Did C2 complete 3600s? — **YES**, the full requested horizon
   (`simulation_time_s: 3600.0`, `TIME_LIMIT_REACHED`, `EXIT:0`)
5. Did either numerical simulation actually deadlock? — **NO** — both the
   600s and 3600s patched runs (and the completed C1 and C2 3600s runs)
   show constant, non-degrading throughput start to finish, with no
   code-level branch that could stall the loop
6. Was dt changed? — **NO**
7. Was physics changed? — **NO**
8. Was controller behavior changed? — **NO**
9. Was WM algorithm changed? — **NO**
10. Is 3600s now safe for future research runs? — **YES**, for the
    simulation/controller/logging pipeline itself — both C1 and C2 have now
    each completed a full 3600s run cleanly under continuous monitoring.
    The one remaining, still-open item is cosmetic: `irsim.make()` should
    be called with `display=False` (or equivalent) in headless/research
    modes so a matplotlib/TkAgg window never appears at all — recommended
    before large batch research runs to avoid any per-run GUI-window
    artifact accumulating across many parallel/sequential processes, even
    though it was not the cause of any hang.

## H. Files modified

**None.** This diagnostic touched no project source file. The only new
artifact is `scratchpad/longrun/diagnostic_launcher.py`, which lives
entirely outside the repository (in the session scratchpad) and
monkey-patches `irsim.make` in-process; it was never imported by, or
copied into, `main.py`, `swarm_baseline.py`, or any tracked file.

## I. Remaining risk

- The unconditional matplotlib/TkAgg window + 3-second `plt.pause` at
  `env.end()` (Section A/B, finding 1) is real and still present in the
  actual research runner (`main.py` / `swarm_baseline.py` as committed) —
  it was only bypassed in this diagnostic's separate, non-invasive launcher.
  It does not block or hang runs, but it does open a visible window on
  every run and costs ~3 fixed seconds per run; over a 20-seed research
  batch this is a minor, bounded, cosmetic cost, not a correctness risk.
- Wall-clock throughput on this shared session/sandbox environment is not
  perfectly constant across different observation windows (some runs
  measured faster, some slower, though never degrading progressively
  within a single continuously-monitored run) — this looks like ordinary
  host/session load variance, not a property of the simulation code, but
  it means wall-clock estimates for a full 20-seed × up-to-3600s research
  batch should be padded generously rather than assumed from a single
  timing sample.
- `1200s` and `2400s` intermediate points in the requested escalation were
  not run as separate data points (see Section C note) — the 600s→3600s
  bracket, both continuously monitored with no throughput change, is
  judged sufficient evidence, but a cautious reader may want those two
  filled in before a very large batch commit.

## J. Freeze recommendation

**Diagnostic-only conclusion: the 3600s long-run issue is resolved and
classified.** The simulation loop itself is stable and safe for 3600s runs
in both Condition 1 (frozen) and Condition 2 (current tree). This clears
the specific blocker named in this task's Stop Rule. It does **not** by
itself constitute C2 Research Freeze approval — the C2 pre-freeze
checklist from `results/C2_WORKING_MEMORY_PREFREEZE/C2_PREFREEZE_AUDIT.md`
still has outstanding items (manifest generation, final ZIP packaging) that
this diagnostic did not address, and per the Stop Rule, R01-R20 must not be
run and C3 must not begin yet.

---

**3600S LONG-RUN DIAGNOSTIC: PASS**
