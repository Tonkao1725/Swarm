# SOLAR_TURN_45 EXPLORE Deadlock — Root-Cause Diagnosis

Date: 2026-08-27. Scope: diagnosis (this document was written before any
edit). Source: `tests/post_arch/DEV01_post_arch_seed2118334751_3600s/`
(the run analyzed in `tests/C2_POST_ARCHITECTURE_DEV_RERUN_REPORT.md`,
which flagged DEV01 `experimental_validity=INVALID_CONTROLLER_CONTACT_FAILURE`).

## A. Exact pathological interval

Scout0, `t_start=1882.3 s`, `t_end=3600.0 s` (simulation horizon) —
**1717.7 s (28.6 min)**, **17,177 consecutive ticks**, all in `phase=EXPLORE`,
`cycle_id=2` (Scout0's second cycle, after one successful delivery in cycle 1).

## B. Physical/spatial behavior

`x_m`/`y_m` are **bit-identical across the entire 17,177-tick window**:
`(11.510899508938143, 7.868086448332094)`. Spatial diameter = 0.0 m. A
circular differential-drive robot rotating in place has, by construction,
zero linear displacement — confirmed directly from `swarm_trajectory.csv`,
not inferred.

## C. Solar sensor behavior

`solar_max` (last column before distance counters) cycles through a
**perfectly repeating sequence** with period exactly 17 ticks (1.7 s) —
see `tests/SOLAR_TURN_EXPLORE_DEADLOCK_TRACE.csv` for a verbatim excerpt
(t=1882.3–1886.0). Concretely, `front_m`/`left_m`/`right_m` at t=1884.2
are **bit-identical** to their values at t=1882.4 (one full period
earlier) — the Scout returns to the exact same effective heading/geometry
every 17 ticks and repeats forever.

## D. ToF behavior

`front_m` stays in the 1.4–2.0 m range throughout — **never near
`safe_front_m` (0.72 m)**. The episode is not caused by a physical
obstruction; the front path was clear (verified: front_m never drops below
1.43 m in the traced window).

## E. Turn-state behavior

`action` = `SOLAR_TURN_45` for essentially every one of the 17,177 ticks
(one stray `EXPLORE_FORWARD` at the very start, t=1882.3, immediately
before entering the pattern). `angular_velocity_radps` alternates
`+0.9 → +0.9 → ... → +0.65 (partial-tick completion) → -0.9 → -0.9 → ... →
-0.65 (partial-tick completion) → +0.9 → ...` — i.e. **a completed 45°
turn in one direction is immediately followed by a completed 45° turn in
the opposite direction**, forever. Each individual turn primitive
completes normally (8–9 ticks, matching `turn_angle_rad /
(angular_speed_radps * step_time) ≈ 8.7`) — turns are not stalling
mid-primitive.

## F. Commanded vs. executed motion

Commanded and executed rotation match exactly (each 45° primitive
completes as commanded — §E). Commanded linear velocity is `0.0` for the
entire window (never requested). Net translation = 0. No collision/stop
flag is present in `swarm_events.csv` for this Scout in this window — this
is not an actuator/physics failure; the *controller* never requested
forward motion once inside the pattern.

## G. Proven root cause

**Mechanism B + C**, proven directly from source and confirmed by the
above evidence (not merely inferred):

`src/swarm_simulate/swarm_baseline.py`, `_explore_command` (pre-correction):

```python
if scout.turn_remaining_rad and scout.escape_direction == 0.0:
    return self._continue_turn(scout)
if reading.detected:
    ...
if scout.escape_direction != 0.0:
    return self._obstacle_escape_command(scout, snapshot)
if reading.guidance_active and reading.strongest_direction != "CENTER":
    direction = 1.0 if reading.strongest_direction == "LEFT" else -1.0
    self._start_turn(scout, direction, "SOLAR_TURN_45")
    return self._continue_turn(scout)
```

The turn-continuation guard (`if scout.turn_remaining_rad: ...`) correctly
prevents a turn primitive from being interrupted mid-flight. But it does
**nothing** once a primitive fully completes (`turn_remaining_rad == 0`):
control falls straight through to the solar-guidance check on the very
next tick, with no intervening forward-progress requirement and no
hysteresis on `strongest_direction` (`energy_sensor.py`:
`strongest = max(channels, key=channels.get)` — a bare argmax, no
deadband).

At this specific position, LEFT and RIGHT solar intensity are close enough
that a completed 45° turn toward the (momentarily) stronger side changes
the geometry just enough to make the **other** side read strongest on the
very next evaluation — and since position never changes (turning in place
cannot change it), the two headings' L/R readings are an exact,
self-sustaining 2-cycle: turn toward LEFT, next evaluation says RIGHT is
now stronger, turn toward RIGHT, next evaluation says LEFT is stronger
again, forever. This matches candidates **B** ("strongest solar direction
repeatedly requests another 45° turn every time the previous primitive
finishes") **and C** ("solar left/right guidance oscillates around a
threshold") from the task's own hypothesis list — proven jointly, not
individually. **D** (physical inability to rotate) and **E** (blocked
light path) are ruled out by §D (front_m never near the safety threshold)
and §F (every commanded rotation executed exactly as requested).

## H. Whether the common C1/C2 controller is affected

**Yes — this is common infrastructure, not a C2-specific defect.**
`_explore_command` contains no `working_memory`/WM/Return-specific logic
in this branch; the same solar-guidance code path is reachable by any
Condition whose Scouts run EXPLORE with light guidance active (C1 and C2
alike, and by inheritance any later Condition reusing `_explore_command`).
Classified: **COMMON EXPLORATION CONTROLLER DEFECT**, not a C2 Working
Memory or Return-behavior issue. `_return_command` (S4's home) is
architecturally separate and untouched by this finding.
