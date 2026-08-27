# C2 Working Memory — Secondary Return Failure Diagnosis

Date: 2026-08-27. Scope: forensic diagnosis only, using data already on
disk from the F3/F4 correction (`scratchpad/f3f4/DEV0{1,2,3}_corrected_...`,
still present, no rerun performed). **No source file was modified. No
commit was made. No research seed (R01-R20) was run. C3 was not started.**

Answers the two independent questions posed:

- **A. Is the WM cycle origin semantically wrong for Central Place
  Foraging?** — **Partially.** For Cycle 1 of two of three Scouts, yes
  (Part D/N). For Cycle 2+, the origin is always Nest-associated by
  construction (Part C).
- **B. Does `skip_unreachable`/route reacquisition cause or contribute to
  the new non-convergent Return behavior?** — **It does not fix it, and in
  most traced instances it has no observable effect on the underlying
  problem** (Part I/O), but the underlying problem itself — a recurring
  obstacle-avoidance/WM-retrace conflict at specific physical
  choke-points — is the same class of mechanism as the original F3, now
  spread across several breadcrumbs instead of frozen on one (Part L).

## A. Initial Scout/Nest geometry

Nest center computed independently from ground truth (offline analysis
only) as the average position of the two `NEST_REACHED` confirmations
available in the corrected DEV01/DEV03 data (DEV01 Scout0 t=1654.7,
DEV03 Scout0 t=172.4): **(1.1010, 1.0267)**. The two confirmations agree
to within 0.028 m of each other — well inside the 0.12 m Nest delivery
radius, confirming this is a reliable reference.

| Run | Scout | Initial X | Initial Y | Nest X | Nest Y | Initial dist to Nest | Nest radius | Inside Nest? | Initial phase | Initial cycle ID |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: |
| DEV01 | 0 | 1.0000 | 1.0000 | 1.1010 | 1.0267 | 0.1045 | 0.12 | **YES** | EXPLORE | 1 |
| DEV01 | 1 | 1.8000 | 1.0000 | 1.1010 | 1.0267 | 0.6995 | 0.12 | NO | EXPLORE | 1 |
| DEV01 | 2 | 2.6000 | 1.0000 | 1.1010 | 1.0267 | 1.4992 | 0.12 | NO | EXPLORE | 1 |
| DEV02 | 0 | 1.0000 | 1.0000 | 1.1010 | 1.0267 | 0.1045 | 0.12 | **YES** | EXPLORE | 1 |
| DEV02 | 1 | 1.8000 | 1.0000 | 1.1010 | 1.0267 | 0.6995 | 0.12 | NO | EXPLORE | 1 |
| DEV02 | 2 | 2.6000 | 1.0000 | 1.1010 | 1.0267 | 1.4992 | 0.12 | NO | EXPLORE | 1 |
| DEV03 | 0 | 1.0000 | 1.0000 | 1.1010 | 1.0267 | 0.1045 | 0.12 | **YES** | EXPLORE | 1 |
| DEV03 | 1 | 1.8000 | 1.0000 | 1.1010 | 1.0267 | 0.6995 | 0.12 | NO | EXPLORE | 1 |
| DEV03 | 2 | 2.6000 | 1.0000 | 1.1010 | 1.0267 | 1.4992 | 0.12 | NO | EXPLORE | 1 |

Scout start positions are **fixed by the world config, identical across
all three seeds** (not randomized) — a row of three Scouts spaced 0.8 m
apart. Only Scout0 spawns inside the valid Nest region.

## B. Verified origin-to-Nest distances

**The previously-reported values (Scout0 ≈ 0.105 m, Scout1 ≈ 0.699 m,
Scout2 ≈ 1.499 m) are confirmed correct**, independently re-derived here
from ground-truth world coordinates using a Nest center computed from
actual `NEST_REACHED` events (not assumed), same coordinate frame (world
meters, `swarm_trajectory.csv` `x_m`/`y_m`), same units, and the values
match to 4 decimal places. These are **world-space Scout mission-start
positions**, not odometric local-frame values — confirmed by construction
(`swarm_trajectory.csv` records world pose; the WM local frame is a
separate internal representation reset to `(0,0)` at `start_cycle`, never
mixed with these numbers in this analysis).

## C. Exact WM origin initialization semantics

**File:** [src/swarm_simulate/swarm_baseline.py](../src/swarm_simulate/swarm_baseline.py)

Two distinct call sites for `CycleWorkingMemory.start_cycle()`:

1. **Cycle 1 (every Scout), lines 812-818**, inside `.run()`, **before the
   main simulation loop begins** — literally the first per-Scout action
   taken after `scout.previous_pose = self._pose(self.env, scout.scout_id)`
   reads the Scout's just-spawned world pose at `t=0.0`:
   ```python
   for scout in self.scouts:
       scout.previous_pose = self._pose(self.env, scout.scout_id)
       scout.trip_start_s = 0.0
       if self.working_memory_enabled and scout.working_memory is not None:
           scout.working_memory.start_cycle(scout.cycle_id)
           ...
   ```
   This is **option B — "at robot spawn"** — not gated on being inside the
   Nest region, not gated on any `EXPLORE`-specific event, not gated on
   "leaving Nest." It fires unconditionally at simulation start for every
   Scout regardless of where that Scout's fixed world-config spawn point
   happens to be.

2. **Cycle 2+, lines 1122-1131**, inside the `DELIVER` handling block
   (guarded by `nest_energy_before`/`delivered_energy` bookkeeping that
   only executes when a delivery has just occurred):
   ```python
   if scout.phase == "EXPLORE" and not self._nest_target_reached():
       if self.working_memory_enabled and scout.working_memory is not None:
           memory.reset()
           ...
           memory.start_cycle(scout.cycle_id)
   ```
   This is **option E — "after NEST_REACHED"** — the position at this
   moment is, by construction, the position where `_environment_nest_reached`
   just returned `True` (i.e. within `nest_delivery_radius_m = 0.12` of
   the true Nest), because `DELIVER` cannot be entered any other way.

This was verified by reading the actual code and its call context (not
inferred from comments alone), and cross-checked against the `wm_writer`
detail strings (`"cycle_start_local_origin"` for case 1,
`"next_cycle_local_origin"` for case 2) and the DEV data's `WM_RESET`
event timestamps, which align exactly with `t=0.0` (case 1) and each
`NEXT_CYCLE_START`/`DELIVER` event timestamp (case 2).

## D. Whether Cycle 1 starts correctly

**No, not uniformly.** Per the Central Place Foraging semantic audit
(Part 5 in the task, reproduced below with direct answers):

1. **Does every foraging cycle actually begin at Nest?** NO for Cycle 1 of
   Scout1 and Scout2; YES for every Cycle 2+ (all Scouts) and for Scout0's
   Cycle 1.
2. **Can Cycle 1 start while a Scout is physically outside Nest?** YES —
   confirmed in every one of the 9 DEV runs analyzed (3 seeds × Scout1 +
   Scout2 both start outside the 0.12 m Nest radius).
3. **If YES, why?** Because `start_cycle()` for Cycle 1 fires unconditionally
   at the Scout's fixed world-config spawn position (Part C, case 1) with
   no check of distance to Nest.
4. **If Scout begins outside Nest, is the WM origin created there?** YES —
   `start_cycle` always resets the local frame to `(0,0)` at the Scout's
   *current* position at the moment it is called, which for Cycle 1 is the
   spawn position itself.
5. **Can perfect WM retrace therefore return to a point that is not Nest?**
   YES — demonstrated directly in Part E/F below.
6. **Does this violate the intended Central Place Foraging semantics?**
   **YES, for Scout1/Scout2's first cycle specifically.** The stated
   intended cycle is `NEST → Leave Nest → Explore → ... → Return Home →
   NEST` (a closed loop). A cycle whose recorded origin is 0.7-1.5 m from
   Nest cannot close that loop through WM retrace alone, no matter how
   accurately WM operates — this is a structural, not a behavioral, gap.
   Per the task's own qualification ("origin does NOT need to equal the
   exact Nest center... but it must be a legitimate Nest-associated cycle
   reference"): 0.699 m and 1.499 m are **not** inside the Nest radius, not
   at a documented "departure point," and not previously discussed in
   `docs/C2_WORKING_MEMORY_DESIGN.md` (checked — no mention of Cycle 1
   start position before this diagnosis). There is no evidence this was an
   intentional design decision — it appears to be an unexamined consequence
   of reusing `start_cycle()` unconditionally for both the mission-start
   case and the post-delivery case.

## E. Perfect-retrace-but-no-Nest cases

Searched all 9 corrected-run failed episodes for: WM stayed valid, Scout's
final approach to its own recorded WM origin became very small, but Nest
was not reached.

| Return ID | Min dist to WM origin | Origin dist to Nest | Min dist to Nest | Energy remaining | WM size (start→end) | Reacquisitions | Final action/state | Classification |
| --- | ---: | ---: | ---: | ---: | --- | ---: | --- | --- |
| DEV02_Scout2_Trip1_Return1 | 0.004 m | 1.499 m | 1.422 m | 0.600 | 21→1 | 0 | `TIME_LIMIT_REACHED`, `RETURN_HOME` | **ORIGIN_NOT_NEST** |
| DEV03_Scout2_Trip1_Return1 | 0.006 m | 1.499 m | 1.483 m | 0.482 | 54→1 | 0 | `TIME_LIMIT_REACHED`, `RETURN_HOME` | **ORIGIN_NOT_NEST** |

No episode fits `ORIGIN_NEAR_NEST_BUT_CONFIRMATION_FAILED` (there is no
case where the Scout got close to the *true* Nest — within, say, 0.3 m —
and confirmation still failed for some other reason; the two cases above
are precisely and only explained by origin ≠ Nest). No episode fits
`ORIGIN_VALID_AND_NEST_REACHED` among the failures by definition (that
would be a success).

## F. Scout2 deep dive

**Precisely verified, both DEV02 and DEV03:**

- DEV02_Scout2: minimum distance to own recorded WM origin over the whole
  Return = **0.0043 m** (`skip_count=0` — WM never needed to reacquire;
  every `WM_POP` and heading/forward decision converged normally).
- DEV03_Scout2: minimum distance to own recorded WM origin = **0.0063 m**
  (`skip_count=0`, same clean convergence).
- Both Scouts' Cycle-1 origin is **1.4992 m** from the true Nest (Part A/B).

Direct answers:

- **Was Working Memory retrace actually successful? YES.** By any
  reasonable navigation-accuracy standard (sub-centimeter), WM guided the
  Scout back to the exact point it recorded as its cycle origin.
- **Was the destination semantically wrong? YES.** That point is the
  Scout's own fixed mission-start position, not the Nest.
- **Could this explain a failed Nest reach even though WM itself navigated
  correctly? YES — conclusively.** These two episodes are the cleanest
  possible evidence that Working Memory's retrace mechanism is not at
  fault; the defect (if it is one) is entirely in what point Cycle 1's
  origin is allowed to be.

## G. Corrected Return episode summary

Recalculated directly from the corrected-run logs (not trusted from prior
session's summary blindly) — full table in
[tests/C2_SECONDARY_RETURN_EPISODES.csv](C2_SECONDARY_RETURN_EPISODES.csv).
**11 episodes total** (2 success, 9 failed) across DEV01 (4), DEV02 (3),
DEV03 (4) — matches the corrected-run totals reported previously.

## H. skip_unreachable source audit

**Files:** [src/swarm_simulate/swarm_baseline.py](../src/swarm_simulate/swarm_baseline.py) `_return_command` (~lines 570-625), [src/swarm_simulate/c2_working_memory.py](../src/swarm_simulate/c2_working_memory.py) `skip_unreachable` (~lines 114-131).

- **No-progress detection:** each tick, if `target` (the coordinate of
  `memory.entries[-1]`) is unchanged since the last tick, compare the
  Scout's current local position (`memory.x_m, memory.y_m`) to the
  position recorded when this exact target was first locked
  (`wm_target_lock_x_m/y_m`). If the Euclidean distance moved is `>=
  memory.spacing_m` (0.25 m, unchanged), progress is recognized and the
  lock/counter reset to the new position. Otherwise `wm_stuck_ticks`
  increments by 1.
- **Target lock:** `scout.wm_target_lock` stores the target coordinate
  tuple itself (not an index); a change in the returned `(x, y)` — which
  only happens when `memory.entries[-1]` changes, i.e. after a `WM_POP` or
  a `WM_ROUTE_REACQUIRE` — resets the lock and counter.
- **Progress threshold:** exactly `memory.spacing_m` = 0.25 m (unchanged,
  reused from the existing breadcrumb-spacing constant, not a new value).
- **Stationary-turn threshold:** `wm_stuck_ticks >= self.return_stationary_turn_limit`.
  Verified value: `return_stationary_turn_limit = 2 * 8 * ceil(turn_angle_rad
  / (angular_speed_radps * step_time)) = 16 * ceil(0.7854 / (0.90 * 0.1)) =
  16 * 9 = 144` ticks of the WM decision block being reached with no
  qualifying progress (not 144 physics ticks total — many physics ticks
  are spent inside `_continue_turn`/`_obstacle_escape_command` before the
  WM block is reached again, so 144 WM-block visits corresponds to
  roughly 150-190 s of simulated time in the observed data, not 14.4 s).
- **When `skip_unreachable()` is called:** exactly once, when the stuck
  counter reaches the limit, inside the WM block of `_return_command`,
  immediately followed by resetting the lock/counter and returning the
  `"WM_ROUTE_REACQUIRE"` action for that tick.
- **Which breadcrumb is skipped:** always `memory.entries[-1]` — the
  current top-of-stack (most recently recorded, i.e. the active retrace
  target) — via the same `.pop()` call structure as `pop_if_reached`.
- **How the next target is chosen:** implicitly — after the pop, the very
  next WM read (`return_target`) simply returns the new `entries[-1]`,
  i.e. the next-older recorded breadcrumb. There is no separate selection
  logic; it is a strict LIFO stack.
- **Whether origin is protected:** YES — `skip_unreachable` uses the exact
  same guard as `pop_if_reached`, `if len(self.entries) > 1:`, so the
  final origin entry (index 0) can never be removed by either mechanism.
- **Whether skipped entries can be revisited:** NO — once popped (by
  either `pop_if_reached` or `skip_unreachable`), an entry is permanently
  gone from `self.entries` for the rest of the cycle; there is no
  "requeue" or "retry later" mechanism.
- **Whether multiple consecutive skips can occur:** YES, unboundedly, as
  long as `len(self.entries) > 1` — confirmed directly in the data (e.g.
  DEV02_Scout0: 18 consecutive skips over 3421.7 s, `wm_size` falling from
  26 to 7).

## I. Every reacquisition/skip classification

Full per-event trace (timestamp, Scout, cycle, `wm_size` after skip,
seconds since the previous skip, pre-/post-skip bounding box and net
displacement, world position and distance-to-true-Nest at the moment of
skip — offline analysis only) is in
[tests/C2_REACQUISITION_EVENT_TRACE.csv](C2_REACQUISITION_EVENT_TRACE.csv), **75 events total** across all three DEV runs.

Classification method: for each skip, the physical bounding box of the
Scout's world position over the window *before* the skip (since the
previous skip, or cycle start) and *after* the skip (until the next skip,
or episode end) is computed. A window with bounding box `< 0.30 m`
indicates the Scout was physically confined to a small pocket for that
entire multi-minute window (i.e., genuinely not making progress, not just
slow).

| Classification | Count | Meaning |
| --- | ---: | --- |
| **NO_EFFECT** | **53 (71%)** | Scout was confined to a small pocket both before *and* after the skip — the skip changed which breadcrumb was targeted but did not change the Scout's physical situation at all |
| **JUSTIFIED_RECOVERY** | 15 (20%) | Scout was confined before the skip, and moved to a materially different area afterward |
| **UNKNOWN** | 7 (9%) | No post-skip window available (the skip was the last one recorded before the episode/run ended) |
| **PREMATURE_SKIP** | 0 | No traced event shows a target that was clearly still easily reachable being abandoned — every skip fired only after the full 144-tick, zero-net-progress bound was exhausted |
| **ROUTE_CONTINUITY_BROKEN** | 0 (in the literal sense) | The Scout's physical trajectory is always continuous (it cannot teleport); no evidence of the *next* target being spatially disconnected from the Scout's current position in a way distinguishable from ordinary retrace |

**The single clearest example** (DEV02, Scout0, `t=877.4` through
`t=3542.9`, cycle 1): the Scout's world position alternates between
exactly two points, `(3.224, 0.988)` and `(3.239, 1.004)` — **2.1 cm
apart** — across **16 consecutive route-reacquisition events** and
**2665.5 simulated seconds**. The per-tick action trace at one of these
events (`t≈1055-1059`) shows a fully periodic pattern: `WM_RETRACE_TURN_45`
rotates the Scout to face its target, `front_m` drops to ≈0.38 m (below
`safe_front_m=0.72`), `OBSTACLE_ESCAPE_TURN_45` then rotates the Scout
through nearly a full circle (heading sweeps from ≈175° down through
every value to 45°) before a single `OBSTACLE_ESCAPE_FORWARD` moves it
2.1 cm to the other point, where the identical conflict repeats in
reverse. Over this entire window: `WM_RETRACE_TURN_45` = 12,960,
`OBSTACLE_ESCAPE_TURN_45` = 12,960 (**exactly equal**), `OBSTACLE_ESCAPE_FORWARD`
= 720, `WM_RETRACE_FORWARD` = 0. This is a **local physical deadlock at a
specific choke point** — WM keeps requesting a heading the local
obstacle-clearance check keeps refusing, regardless of which breadcrumb
is currently active.

## J. Non-convergent Return analysis

Recalculated (not trusted from the prior session): **9 of 11** corrected
episodes are failures; of those, **2** are the pure origin-gap cases (Part
E), **1** (DEV02_Scout1) has too few skip events (only 1) to classify with
confidence, and **6** show the recurring-obstacle-pocket signature
(≥30% of that episode's skips classified `NO_EFFECT`, with at least 2
skip events observed):

- DEV01_Scout2_Trip1 (10 skips, 4 `NO_EFFECT`)
- DEV01_Scout1_Trip1 (14 skips, 10 `NO_EFFECT`)
- DEV01_Scout0_Trip2 (9 skips, 7 `NO_EFFECT`)
- DEV02_Scout0_Trip1 (18 skips, 15 `NO_EFFECT`)
- DEV03_Scout1_Trip1 (6 skips, 4 `NO_EFFECT`)
- DEV03_Scout0_Trip2 (14 skips, 12 `NO_EFFECT`)

(The prior session's approximate count of "7" non-convergent episodes is
close to but not identical to this more granular recount — it counted
every non-origin-gap failure as one bucket; this diagnosis further splits
that bucket into 6 recurring-obstacle-pocket cases plus 1
insufficient-evidence case.)

## K. Successful vs failed comparison

| Return ID | Success | Origin valid for Nest | Start energy | WM start size | Skip count | Min dist to origin | Min dist to Nest | Duration (s) | Root cause |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| DEV01_Scout0_Trip1 | YES | YES | 2.209 | 262 | 3 | 0.111 | 0.028 | 1186.4 | — |
| DEV03_Scout0_Trip1 | YES | YES | 2.907 | 29 | 0 | 0.105 | 0.028 | 75.6 | — |
| DEV01_Scout2_Trip1 | NO | NO | 2.877 | 39 | 10 | 2.094 | 2.880 | 3481.6 | S4 (+S1) |
| DEV01_Scout1_Trip1 | NO | NO | 1.786 | 300 | 14 | 1.850 | 2.271 | 2645.9 | S4 (+S1) |
| DEV01_Scout0_Trip2 | NO | YES | 1.941 | 59 | 9 | 2.257 | 2.249 | 1781.4 | S4 |
| DEV02_Scout2_Trip1 | NO | NO | 2.939 | 21 | 0 | 0.004 | 1.422 | 3526.9 | S1 |
| DEV02_Scout1_Trip1 | NO | NO | 2.818 | 55 | 1 | 1.279 | 1.975 | 3454.2 | S9 |
| DEV02_Scout0_Trip1 | NO | YES | 2.810 | 53 | 18 | 2.224 | 2.123 | 3421.7 | S4 |
| DEV03_Scout2_Trip1 | NO | NO | 2.827 | 54 | 0 | 0.006 | 1.483 | 3468.8 | S1 |
| DEV03_Scout1_Trip1 | NO | NO | 2.635 | 111 | 6 | 1.430 | 2.129 | 3325.7 | S4 (+S1) |
| DEV03_Scout0_Trip2 | NO | YES | 2.472 | 181 | 14 | 2.739 | 2.744 | 3134.0 | S4 |

**Systematic difference, evidence only:** both successes minimized their
distance-to-origin to ≈0.11 m (which was also ≈Nest, since both are
"origin valid" cases) with a small number of skips (0-3). Every failure
either has an invalid origin (S1, min-to-origin near-zero but irrelevant)
or never gets its min-distance-to-origin below ≈1.3 m at all, regardless
of starting energy (which spans nearly the same 1.79-2.94 range for both
successes and failures — energy is not a discriminator, consistent with
the earlier F3/F4 correction report). Skip count alone is not
discriminating (DEV02_Scout2 succeeded at convergence with 0 skips;
DEV02_Scout0 failed at convergence with 18) — what discriminates is
whether the *physical location* the Scout needed to pass through allowed
forward progress at all, which the `NO_EFFECT` classification (Part I)
captures directly.

## L. Old C2 vs corrected C2 causal comparison

Mechanism determination for why Nest-reach count fell from 8 to 2, using
the evidence gathered above:

- **(A) previous successes were partly "lucky" C1 fallback behavior:**
  Plausible and consistent — in the old code, F4 caused WM to hand off to
  the untargeted C1 stateless branch early and often; that branch's
  behavior does not depend on any specific breadcrumb, so it could
  "wander past" a choke point that would otherwise deadlock a
  target-directed controller, purely by chance. Not directly falsifiable
  from available data, but consistent with every other finding here.
- **(B) new reacquisition skips valid breadcrumbs:** **Not supported by
  the event-level evidence.** 0 of 75 traced skips show a target being
  abandoned while genuinely progressing (Part I: `PREMATURE_SKIP = 0`).
  Every skip fired only after the full no-progress bound was exhausted.
- **(C) the corrected logic exposes origin≠Nest:** **Confirmed, for 2 of 9
  failures** (Part E/F) — this mechanism is real and fully evidenced, but
  only accounts for a minority of the reduction.
- **(D) combination of B+C:** Not the best fit, since B is not evidenced.
- **(E) another mechanism — recurring obstacle-avoidance/WM-retrace
  conflict at multiple breadcrumbs (this diagnosis's main finding):**
  **Best-supported by the evidence**, accounting for 6 of 9 failures. This
  is mechanistically the *same* conflict as the original F3 defect (WM
  requests a turn, local safety refuses it, repeat) — the F3 correction
  successfully stops it from looping on a single breadcrumb forever, but
  it does not, and was not designed to, prevent the *same* physical
  conflict from recurring at the *next* breadcrumb, and the one after
  that. The net effect in these 6 cases: the Scout consumes its recorded
  route (through repeated 144-tick-bounded stalls) largely without net
  spatial progress, until either the route is exhausted, energy runs low,
  or the horizon ends.

**Overall: primarily (E), with (C) as a real, independent, secondary
contributor, and (A) plausible but not directly provable from these
logs.**

## M. Root-cause distribution

| Primary cause | Count | Episodes |
| --- | ---: | --- |
| S1 — INVALID_CYCLE_ORIGIN | 2 | DEV02_Scout2, DEV03_Scout2 |
| S4 — LEGITIMATE_OBSTACLE_COMPLEXITY | 6 | DEV01_Scout2 (+S1 secondary), DEV01_Scout1 (+S1 secondary), DEV01_Scout0_Trip2, DEV02_Scout0, DEV03_Scout1 (+S1 secondary), DEV03_Scout0_Trip2 |
| S9 — UNRESOLVED (insufficient evidence) | 1 | DEV02_Scout1 (only 1 skip event recorded; cannot distinguish a recurring-pocket pattern from another cause with confidence) |
| S2 / S3 / S5 / S6 / S7 / S8 | 0 | no episode's primary evidence matches these |

No failure was classified as primarily energy- or time-limited — those
are downstream terminal events, not root causes, in every depleted or
horizon-ended episode examined (per the task's own Part 17 instruction).

## N. Whether origin initialization is defective

1. Is WM origin semantically Nest-associated for every cycle? **NO.**
2. Is Cycle 1 different from later cycles? **YES.**
3. Do Scouts start outside Nest? **YES** (Scout1, Scout2; Scout0 does not).
4. If YES, is that intentional experiment design? **NOT DOCUMENTED** —
   no mention of Cycle-1 start-position handling exists in
   `docs/C2_WORKING_MEMORY_DESIGN.md` prior to this diagnosis, and the
   module docstring in `c2_working_memory.py` describes "a reset-at-Nest
   odometric frame," which Cycle 1 for Scout1/Scout2 does not actually
   satisfy.
5. Can perfect retrace terminate at a non-Nest location? **YES.**
6. Did this occur in DEV data? **YES** (Part E/F, 2 confirmed instances).
7. Does origin initialization require correction? **Evidence supports
   YES for Cycle 1 specifically** — see Part P for the smallest candidate
   correction (not implemented).

## O. Whether reacquisition logic is defective

1. Does `skip_unreachable` trigger only on genuinely unusable targets?
   **By its own bounded, deterministic criterion, YES** — every traced
   skip fired only after 144 WM-block ticks (~150-190 s) of less than one
   breadcrumb-spacing of net progress toward that specific target; no
   evidence of premature triggering was found.
2. Can it skip a still-valid breadcrumb? **In the sense of "reachable in
   principle, just not yet reached" — arguably yes for any bounded
   detector, but no *observed* instance in this data shows a target that
   was clearly progressing being cut off; the detector's threshold is not
   shown to be miscalibrated in either direction from available evidence.**
3. Can it break route continuity? **No literal/physical instance found**
   (the Scout is always spatially continuous); however, since a skip
   permanently discards the popped entry, if that entry's route segment
   was the only way around a specific obstacle, skipping it could remove
   the Scout's best chance of an eventual solution for that segment —
   this is a plausible structural risk, not directly falsified or
   confirmed by the available traces.
4. Can multiple skips produce non-convergent wandering? **Observed
   behavior is not "wandering" (net displacement stays small) — it is
   repeated re-confinement to the same or a similar physical pocket.**
   Multiple skips do not, by themselves, cause net divergence from Nest
   in the traced data; they primarily consume the recorded route while
   the Scout is trapped.
5. Did this occur in DEV data? **YES** (Part I/J, 6 of 9 failures).
6. Does reacquisition logic require correction? **The reacquisition
   mechanism is functioning exactly as designed and does not appear to be
   the root defect — the root cause of the 6 S4 failures is the
   underlying local-safety/WM-heading conflict recurring at successive
   breadcrumbs, which reacquisition can only delay, not resolve.**
   Whether *that* underlying conflict needs a correction is a distinct,
   larger question than "is `skip_unreachable` itself buggy" — see Part P.

## P. Minimal justified correction(s)

**Not implemented — proposals only, per the Stop Rule.**

### For the origin issue (S1, 2 confirmed episodes)

Two candidates, evaluated against the existing architecture:

1. **Align first-cycle initialization with the later-cycle
   NEST_REACHED-reset semantics.** Instead of calling `start_cycle()`
   unconditionally at `t=0` for every Scout, defer it until that Scout's
   first `_environment_nest_reached()` becomes `True` (Scout0 would
   satisfy this almost immediately; Scout1/Scout2 would begin WM
   recording only once they first physically enter the Nest region). This
   most closely matches "create WM cycle origin at Nest departure" and
   reuses the exact same predicate already used for Cycle 2+, so it is
   architecturally the smallest change (one call-site condition, not a
   new mechanism).
2. **Initialize first-cycle origin only when Scout is in the valid Nest
   region; otherwise treat pre-Nest-entry motion as C1-equivalent
   (WM-inactive) until entry is confirmed.** Functionally similar to (1)
   but framed as a temporary WM-disable rather than a deferred
   `start_cycle` call.

Both avoid enlarging the Nest radius (forbidden) and avoid touching WM
capacity/spacing. Candidate (1) appears to match the existing
architecture more directly, since it reuses `_environment_nest_reached`
verbatim rather than introducing a new WM-disable state.

### For the reacquisition/obstacle-recurrence issue (S4, 6 confirmed episodes)

Given Part O's finding that `skip_unreachable` itself is not shown to be
defective, the more directly-supported candidate targets the underlying
conflict, not the skip mechanism:

1. **Temporary avoidance tolerance / hysteresis on the WM turn-vs-avoid
   boundary** at the specific heading where `WM_RETRACE_TURN_45` and
   `OBSTACLE_ESCAPE_TURN_45` alternate — e.g. a bounded number of
   alternations before trying the *other* rotation direction once, rather
   than always re-requesting the same WM-preferred heading. This is the
   closest match to "route reacquisition without permanently skipping a
   valid target," since it does not consume any WM entry at all.
2. **Ability to retry a previously-skipped breadcrumb** if the Scout's
   local heading/position changes enough (e.g., after such a
   hysteresis-based local maneuver succeeds) that the old target might
   now be approachable from a different angle — this would require a
   small, bounded "recently skipped" list rather than permanent removal,
   a slightly larger change than (1).

Neither proposal is implemented. Both require their own dedicated
regression tests (equivalent to Tests M-Q) and a fresh DEV01-03 rerun
before any decision to implement.

## Q. Whether C2 can Freeze now

**No.** Two independent, evidenced defects/gaps remain open:
(1) Cycle-1 WM origin is not reliably Nest-associated for 2 of 3 Scouts
(S1, structural gap in origin initialization, not a WM retrace defect);
(2) a recurring local obstacle-avoidance/WM-retrace conflict — the same
underlying mechanism as the original F3 — causes 6 of 9 corrected-run
failures by repeatedly stalling at successive breadcrumbs rather than one
(S4). Per the task's Stop Rule, neither has been implemented or tuned in
this diagnosis. A deliberate decision is needed on whether to pursue
Part P's proposals (smallest first) before a freeze decision, or to
document these as accepted, disclosed limitations of the current C2
design and freeze anyway — that choice is not this diagnosis's to make.

---

**C2 SECONDARY RETURN DIAGNOSIS: CORRECTION JUSTIFIED**
