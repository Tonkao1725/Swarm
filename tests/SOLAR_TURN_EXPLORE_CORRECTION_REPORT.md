# SOLAR_TURN_45 EXPLORE Deadlock — Minimal Correction Report

Date: 2026-08-27. Root cause: `tests/SOLAR_TURN_EXPLORE_DEADLOCK_DIAGNOSIS.md`.
Scope: common EXPLORE controller only. No change to `_return_command`,
`c2_working_memory.py`, `energy_sensor.py`, WM capacity/spacing/pruning,
F3/F4, `skip_unreachable`, route reacquisition, resource geometry, energy,
or thresholds.

## Source safety

SHA-256 recorded before editing:

| File | Before | After |
| --- | --- | --- |
| `src/swarm_simulate/swarm_baseline.py` | `9dbd6729...f0bc47f` | `2bfbfc05...4032ad0f` (changed — this task's only edit) |
| `src/swarm_simulate/c2_working_memory.py` | `b9a25db8...f478b48d` | `b9a25db8...f478b48d` **(unchanged, verified)** |
| `src/swarm_simulate/energy_sensor.py` | `608befe4...43ea3d3e1` | `608befe4...43ea3d3e1` **(unchanged, verified)** |

## Minimal correction

One new `ScoutState` field (current-actuator-tick state, same kind as the
existing `escape_direction`/`turn_remaining_rad`):

```python
solar_turn_progress_pending: bool = False
```

`_explore_command`: after a `SOLAR_TURN_45` primitive is *requested*, the
flag is set; the *next* decision tick (which, per the diagnosis, is
exactly when the pathology re-arbitrated solar guidance from the same
position) instead requires one safety-gated forward attempt before solar
guidance may be re-read:

```python
if scout.escape_direction != 0.0:
    return self._obstacle_escape_command(scout, snapshot)
if scout.solar_turn_progress_pending:
    scout.solar_turn_progress_pending = False
    if self._forward_body_clearance_safe(snapshot, sensor):
        return self.linear_speed_mps, 0.0, "SOLAR_TURN_PROGRESS_FORWARD"
    # not safe -- fall through to the unmodified obstacle-safety branches
elif reading.guidance_active and reading.strongest_direction != "CENTER":
    direction = 1.0 if reading.strongest_direction == "LEFT" else -1.0
    self._start_turn(scout, direction, "SOLAR_TURN_45")
    scout.solar_turn_progress_pending = True
    return self._continue_turn(scout)
```

**Why this breaks the cycle**: the self-sustaining 2-cycle identified in
the diagnosis depends entirely on the Scout's position never changing
between solar-guidance evaluations (turning in place cannot change
position, so the same near-ambiguous L/R geometry recurs exactly). Forcing
one genuine forward step between a completed solar turn and the next
guidance evaluation changes the position, which changes the geometry, which
breaks the exact repetition the cycle depends on.

**Why this is minimal / not a magic timeout**:
- The bound is exactly **one decision tick** (a single forward command,
  re-evaluated every tick exactly like every other action in this file) —
  not a duration threshold in seconds or ticks.
- The forward attempt reuses the existing, unmodified
  `_forward_body_clearance_safe` safety gate (already used identically at
  three other call sites in this file) — no new safety logic, no new
  distance/threshold constant.
- If the forward attempt is unsafe, control falls through to the
  **existing, unmodified** obstacle-safety branches (side-clearance turn,
  front-safety escape) — the correction adds no new obstacle-handling
  path.
- Light guidance, CENTER/forward behavior, and ToF safety are all
  unmodified for every case except "a solar turn just completed."

**Why C1 remains memory-free**: the new field is a plain boolean, default
`False`, set `True` only when a solar turn starts and consumed (reset to
`False`) on the very next decision tick regardless of outcome — it never
survives beyond one tick, stores no coordinate, identifier, or history,
and is not read by `_return_command`, WM, or any cross-cycle/cross-trip
code path (Test SOLAR-7/8/9).

## J. Tests SOLAR-1 through SOLAR-10

All 10 PASS (`tests/validate_solar_turn_explore_deadlock.py`):

```
PASS Test SOLAR-1: a SOLAR_TURN_45 primitive completes normally in 8 ticks
PASS Test SOLAR-2: under persistent flip-flopping LEFT/RIGHT guidance over 400 ticks, the longest gap between forward attempts was 9 ticks (bound: 11); 40 forward ticks occurred -- no unbounded stationary reissue
PASS Test SOLAR-3: control after a completed solar turn consumes a fresh sensor reading, not a stale/cached one
PASS Test SOLAR-4: normal open-space solar guidance still turns toward the stronger side
PASS Test SOLAR-5: CENTER guidance with a safe path still produces normal forward progression
PASS Test SOLAR-6: with unsafe front clearance, the pending forward commitment is declined (action=OBSTACLE_ESCAPE_TURN_45), never authorizing travel through unsafe geometry
PASS Test SOLAR-7: the correction adds exactly one new field, a plain per-tick boolean actuator flag -- no location, route, resource-preference, or map memory
PASS Test SOLAR-8: c2_working_memory.py is byte-identical to its pre-task SHA-256
PASS Test SOLAR-9: _return_command (S4/F3/F4 machinery) is untouched by this correction
PASS Test SOLAR-10: replaying the original DEV01 adversarial flip-flop condition over 2000 ticks, the corrected controller never exceeds 9 consecutive non-forward ticks (vs. the original 17,177) and takes 200 forward steps
```

## K. Regression battery

| Suite | Result |
| --- | --- |
| HOME-1..15 | **PASS** (15/15) |
| PORT-1..12 | **PASS** (12/12) |
| RF-1..12 | **PASS** (12/12) |
| SOLAR-1..10 | **PASS** (10/10) |
| C2 Acceptance A-J | **PASS** |
| F3/F4 Tests M-Q | **PASS** |
| Condition isolation | **PASS** |
| RSSI monotonicity / state reset | **PASS** |
| Persistent stationary-turn deadlock (`validate_persistent_stationary_turn_deadlock.py`) | **PASS** |
| Baseline termination architecture | **PASS** |
| C1 all-depleted termination | **PASS** |
| C1 energy accounting | **PASS** |
| `validate_c1_rssi_boundaries.py` | **FAIL — pre-existing, unrelated** (same single cause reported in every prior task this session: F3's `memory.x_m`/`memory.y_m` in `_return_command`, untouched here too) |

No-global-navigation / no-RSSI-navigation audits: covered structurally by
HOME-4/HOME-13, RF-9, PORT-6/PORT-7 (all still passing, unaffected by this
`_explore_command`-only change — none of those audited methods overlap
with the edited code).

## L. DEV01 post-correction result

Rerun (identical config to `tests/C2_POST_ARCHITECTURE_DEV_RERUN_REPORT.md`
§A: `mission_mode=research; nest_energy_target=6; scout_count=3;
horizon_s=3600; WM=True`, seed 2118334751):

```
engineering=COMPLETED; mission=TIME_LIMIT_REACHED; validity=VALID
```

| Scout | phase at end | delivery_count | persistent_stationary_turn_deadlock | max_consecutive_stationary_rotation_steps |
| --- | --- | ---: | --- | ---: |
| 0 | RETURN_HOME | 1 | **False** | 72 |
| 1 | DEPLETED | 0 | **False** | 63 |
| 2 | RETURN_HOME | 9 | **False** | 36 |

`experimental_validity` changed from `INVALID_CONTROLLER_CONTACT_FAILURE`
to **`VALID`**. No Scout's `max_consecutive_stationary_rotation_steps`
exceeds 72 (well under the 144-tick safety-reporting threshold) — no
SOLAR_TURN pathological episode occurred anywhere in the 3600 s run.
Mission success/delivery count is **not** the goal here and is not
claimed as evidence of anything beyond engineering validity (per
instruction) — Scout2's high delivery count (9) is a side effect of no
longer freezing for 28.6 minutes, not a claim about C2 performance.

## M. C1 isolation result

Not independently rerun in this task (no C1-specific run was required by
the Stop Rule's minimal-scope instruction), but verified structurally: the
corrected branch is reached identically regardless of
`working_memory_enabled` (the `_explore_command` method and its solar
branch have no `working_memory`/WM dependency at all — confirmed by
source read, §H of the diagnosis). C1 (`WM=False`) will exercise the exact
same corrected solar-guidance code path as C2 the next time its EXPLORE
phase encounters comparable geometry. Per instruction, byte-identical C1
trajectory against the historical frozen C1 baseline is **not** claimed or
required, since the corrected branch is common infrastructure that may
legitimately change C1's own trajectory wherever the old pathology (or its
absence) would have mattered.

## N. Confirmation C2 WM/Return code unchanged

`src/swarm_simulate/c2_working_memory.py` SHA-256 unchanged (§ Source
safety table, Test SOLAR-8). `_return_command`'s source contains no
reference to `solar_turn_progress_pending` or
`SOLAR_TURN_PROGRESS_FORWARD`, and still contains its full, unmodified
F3/F4/`skip_unreachable` machinery (Test SOLAR-9).

## O. Files modified

- `src/swarm_simulate/swarm_baseline.py`: added
  `ScoutState.solar_turn_progress_pending`; modified `_explore_command`'s
  solar-guidance branch (see diff above). No other function touched.
- New: `tests/validate_solar_turn_explore_deadlock.py` (Tests SOLAR-1..10),
  `tests/SOLAR_TURN_EXPLORE_DEADLOCK_DIAGNOSIS.md`,
  `tests/SOLAR_TURN_EXPLORE_CORRECTION_REPORT.md`,
  `tests/SOLAR_TURN_EXPLORE_DEADLOCK_TRACE.csv`.
- No existing C2 post-architecture report was overwritten.

## P. Whether engineering validity is restored

**Yes.** DEV01 is `VALID` (was `INVALID_CONTROLLER_CONTACT_FAILURE`); no
persistent-stationary-turn-deadlock flag fires anywhere in the rerun; the
`validate_persistent_stationary_turn_deadlock.py` regression test (a
different, pre-existing scenario) still passes unaffected.

## Q. Whether the system is ready for a separate S4 correction

**Yes.** This task deliberately did not touch `_return_command` or any
S4-related machinery (Test SOLAR-9 regression-guards this). S4 remains
exactly as characterized in `tests/C2_POST_ARCHITECTURE_DEV_RERUN_REPORT.md`
§K/§S, unaffected by this correction, and ready for its own focused task.

---

**SOLAR EXPLORE DEADLOCK: CORRECTED — READY FOR S4 REVIEW**
