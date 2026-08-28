# C2 S4 Return Limit-Cycle — Root-Cause Reconfirmation (post-SOLAR-correction source)

Date: 2026-08-27/28. Scope: diagnosis, reconfirmed against the CURRENT
source (after the SOLAR_TURN_45 EXPLORE correction, before any S4 edit).
Evidence source: `tests/C2_POST_ARCHITECTURE_RETURN_EPISODES.csv`,
`tests/C2_POST_ARCHITECTURE_REACQUISITION_TRACE.csv`,
`tests/C2_POST_ARCHITECTURE_LIMIT_CYCLES.csv`,
`tests/C2_POST_ARCHITECTURE_DEV_RERUN_REPORT.md` (all unmodified by this
task), re-verified directly against `src/swarm_simulate/swarm_baseline.py`
lines 750-843 (`_return_command`) as they stood immediately before this
task's edit.

## Reconfirmed strongest episode: DEV02 Scout1

- 12 consecutive `WM_ROUTE_REACQUIRE` events, t=1353.6 s to t=3430.3 s
  (**2076.7 s / 34.6 min**), all classified `NO_EFFECT`.
- Physical bounding box confined to **0.02-0.13 m** the entire time.
- 13 WM breadcrumb entries consumed (`wm_size` 266 -> 253) with zero net
  spatial progress.

## Reconstructed sequence, item by item (per task's numbered checklist)

1. **Active WM target**: `memory.return_target(scout.cycle_id)` --
   `entries[-1]`, unchanged across the whole 2076.7 s window (no `WM_POP`
   between the 12 reacquire events; only `WM_ROUTE_REACQUIRE` operations
   advance the target, each one only after the full stuck-tick bound).
2. **Heading error to target**: recomputed every arbitration tick from
   the Scout's *current* `memory.x_m/y_m/heading_rad` vs. the fixed
   target -- by construction, always re-derived from the live (if
   unmoving) local pose.
3. **`WM_RETRACE_TURN_45` requests**: issued whenever `abs(heading_error)
   > 22.5 deg`, which recurs every arbitration cycle because the escape
   maneuver (item 4) changes heading without changing position.
4. **Obstacle-escape requests**: whenever `_forward_body_clearance_safe`
   fails after a `WM_RETRACE_TURN_45` completes, `_return_command`
   (pre-correction) fell straight through past the whole
   `working_memory_enabled` block to the generic C1 branches
   (`_obstacle_escape_command` / `_begin_clear_side_turn`).
5. **Actual translation**: `_obstacle_escape_command` clears
   (`_clear_escape`) as soon as `front_m > safe_front_m and
   min(left,right) >= turn_side_clearance_m` -- returning exactly **one**
   `OBSTACLE_ESCAPE_FORWARD` tick (`linear_speed_mps * step_time` =
   0.022 m) before clearing. This is the entire "escape."
6. **Actual rotation**: each `WM_RETRACE_TURN_45` and
   `OBSTACLE_ESCAPE_TURN_45`/`RETURN_LOCAL_*_ESCAPE_45` primitive
   completes exactly as commanded (proven in the SOLAR diagnosis's
   identical turn-primitive mechanics, reused here) -- rotation itself is
   never the problem.
7. **ToF geometry**: consistent with a genuine tight local conflict (not
   a sensor artifact) -- front/side clearance genuinely fails immediately
   after turning toward the target, every cycle.
8. **Spatial pocket diameter**: 0.02-0.13 m -- smaller than the robot's
   own 0.25 m radius; the one-tick, 0.022 m `OBSTACLE_ESCAPE_FORWARD`
   step is on the same order of magnitude as the pocket itself, explaining
   why it can never escape it.
9. **Route reacquisition timing**: exactly every ~177 s (144
   arbitration-reaching ticks, per `return_stationary_turn_limit`, spread
   over many more physical ticks consumed by the intervening
   turn/escape sub-cycles that bypass the arbitration block entirely).
10. **Whether skip changed local physical state**: **No** -- confirmed
    directly (pre-/post-skip bounding box unchanged, 0.02-0.13 m, in all
    12 events).
11. **Whether the same geometry recurred immediately afterward**: **Yes**
    -- the next-older breadcrumb (now the new target) was reached from
    the *same* physical pocket the previous target could not be escaped
    from, so the identical local conflict recurred.

## Canonical failure mechanism -- confirmed, not merely hypothesized

```
WM requests motion toward current breadcrumb
-> local obstacle rule overrides for safety (_obstacle_escape_command)
-> escape clears after ONE safe-forward tick (~0.022 m) -- far short of
   leaving the 0.02-0.13 m conflict pocket
-> controller returns immediately to WM arbitration
-> heading toward the SAME target recomputed from the barely-changed
   position -> same blocked geometry
-> WM / obstacle arbitration repeats
-> wm_stuck_ticks (only incremented on ticks that reach the arbitration
   block, i.e. NOT during turn/escape sub-cycles) eventually reaches
   return_stationary_turn_limit (144) -> skip_unreachable fires
-> next-older breadcrumb attempted from essentially the same physical
   pocket -> same obstacle geometry repeats
-> 12 consecutive skips, all NO_EFFECT
```

This exactly matches the task's hypothesized mechanism. **Exact
arbitration defect**: `_return_command` had no minimum-displacement
requirement between a completed obstacle-escape maneuver and the next WM
heading re-arbitration -- the escape's own completion criterion ("front
and side momentarily clear") is unrelated in scale to "far enough from
the conflict pocket to make the same heading safe again."

## Why `skip_unreachable` is not the primary fix

- `PREMATURE_SKIP = 0` (pre-correction evidence, `tests/C2_POST_ARCHITECTURE_DEV_RERUN_REPORT.md`
  §N) -- every skip fired only after the full 144-arbitration-tick bound,
  never while genuine progress was occurring.
- All 12 DEV02-Scout1 skips (and the majority of skips generally, 55%
  overall) were `NO_EFFECT` -- the mechanism *popping a breadcrumb*
  clearly works exactly as designed; the mechanism that fails is
  *arriving at the next breadcrumb from a physically different position*,
  which `skip_unreachable` itself has no way to influence (it only
  changes which coordinate is targeted, not where the Scout physically
  is).
- Making skip fire sooner, more aggressively, or discard more breadcrumbs
  would only change *which* stale target is retried from the same stuck
  pocket -- it does not address the root cause (insufficient displacement
  before re-arbitration), and was explicitly excluded from this task's
  scope.

**Conclusion**: the correction must target the obstacle-escape/WM
re-arbitration boundary in `_return_command`, not `skip_unreachable`
itself, and not `c2_working_memory.py`'s storage/retrace semantics.
