# Logger Equivalence Test K

Date: 2026-08-26. Scope: development validation only; no research seed was run.

## Test configuration

- Frozen reference commit: `2cc0275bf29c40fedfba44e8865ac5696d61ec94` ("Preserve C1
  advisor data and analysis package"), checked out into a temporary
  `git worktree` so the comparison is against the exact frozen tree, not a
  historical snapshot from an earlier C1 iteration.
- Comparison target: current working tree on `c2-working-memory-dev` with
  `SWARM_EXPERIMENT_MODE=baseline` (`working_memory_enabled=False`).
- Development seed: `2118334751` (a documented development/regression seed,
  not a canonical research seed).
- Common run env: `SWARM_SCOUT_COUNT=3`, `SWARM_MISSION_MODE=research`,
  `NEST_ENERGY_TARGET=6`, `FORAGING_TRIPS=3`, `SWARM_SIM_DURATION_S=300`,
  `FAST_HEADLESS_RESEARCH_MODE=1`, `IRSIM_RENDER=0`.
- No canonical 20-seed research set was touched.

## A. Behavior equivalence — PASS

All simulation-behavior evidence is identical between the frozen `2cc0275`
run and the current-tree run with WM disabled:

- `swarm_trajectory.csv`: 9,000/9,000 rows identical across every column
  (position, heading, action, linear/angular velocity, sensor readings).
- Console collision warnings identical in scout, position and message on
  both runs (`Scout-2 collided with obstacle_2 at state [4.24, 2.0, -3.14]`,
  `Scout-1 collided with obstacle_2 at state [4.24, 1.89, -2.36]`), confirming
  RNG usage/order is unchanged.
- `robot_energy_timeline.csv`: 9,003/9,003 rows identical on every
  pre-existing column (`sim_time_s`, `scout_id`, `internal_energy`, `phase`).
- `swarm_events.csv`: 408/408 rows identical on every column after the fix
  (see Section B).
- `summary.json`: identical on every field, including ground-truth pose,
  closure error and odometry error.
- `swarm_summary.json`: identical on every pre-existing field — mission
  outcome, delivered/withdrawn energy, distance, phase-at-termination,
  coverage, turn counts for every Scout.
- Termination: both runs end `TIME_LIMIT_REACHED` / `VALID`.

No decision/navigation branch, state transition, termination predicate, RNG
consumption, resource delivery, or energy value differs.

## B. Exact legacy label equivalence — PASS (after fix)

Two label-only fields were previously found to differ from the frozen C1
text even with WM disabled. Both are now fixed and gated explicitly on
`working_memory_enabled` / `experiment_mode.working_memory_enabled`:

| Field | Frozen C1 (`2cc0275`) | Before fix | After fix |
| --- | --- | --- | --- |
| `swarm_events.csv` → `RETURN_HOME_START.detail` (WM off) | `stateless_local_reactive_return; rssi_confirmation_only` | `RETURN_WITHOUT_WORKING_MEMORY; rssi_confirmation_only` | `stateless_local_reactive_return; rssi_confirmation_only` |
| `metadata.json` → `configuration.mission_termination` (WM off, research mode) | `NEST_ENERGY_TARGET_OR_HORIZON` | `NEST_ENERGY_TARGET_OR_ALL_DEPLETED_OR_HORIZON` (unconditional) | `NEST_ENERGY_TARGET_OR_HORIZON` |

Post-fix re-run confirms byte-exact text match on both fields for WM off.

Condition 2 (WM on) text was intentionally left unchanged and verified still
present after the fix:
- `mission_termination` (WM on, research mode) =
  `NEST_ENERGY_TARGET_OR_ALL_DEPLETED_OR_HORIZON` (confirmed via a short
  `SWARM_EXPERIMENT_MODE=working_memory` sanity run, same seed).
- `RETURN_HOME_START.detail` (WM on) source branch is untouched:
  `CURRENT_CYCLE_WORKING_MEMORY_RETRACE; local_safety_override_allowed`.

No decision logic, navigation logic, RNG usage/order, termination logic, or
energy model was touched — only the two literal string values in metadata
construction.

## C. Additive schema differences (still present, behavior-safe)

These remain unchanged by this fix and were already classified as
additive-only in the prior Test K pass:

- Two new per-run files appear even with WM off: `state_transitions.csv`,
  `working_memory_events.csv`.
- `robot_energy_timeline.csv` gains six new columns (`trip_id`, `cycle_id`,
  `energy_before`, `energy_after`, `energy_consumed`, `event`); all
  pre-existing columns and values are unchanged.
- `swarm_summary.json` gains six new per-Scout fields
  (`working_memory_entries/max_size/pops/prunes/reads/resets`), all `0` when
  WM is disabled.

None of these affect simulation behavior or the text of any pre-existing
field.

## Files changed in this fix

- [main.py](../main.py) — `mission_termination` now branches on
  `experiment_mode.working_memory_enabled` instead of being set
  unconditionally for `research` mode.
- [src/swarm_simulate/swarm_baseline.py](../src/swarm_simulate/swarm_baseline.py)
  — the `RETURN_HOME_START` event's `detail` text for the WM-disabled branch
  restored to the frozen C1 wording.

## Test result

**PASS.** Behavior equivalence: PASS. Legacy label equivalence: PASS.
Remaining differences are additive-only (new files/columns/fields), not
behavior or legacy-text changes.

## Conclusion

Condition 1 behavior and Condition 1 output text are both protected: with
`working_memory_enabled=False`, the current working tree reproduces the
frozen `2cc0275` baseline's simulation behavior exactly and now also
reproduces its exact output text on the two fields that previously drifted.
Remaining output differences are strictly additive (new log files/columns)
and do not alter any existing C1 value or label.
