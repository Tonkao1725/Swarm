# C2 Working Memory design — development only

**Status note (2026-08-27): this document now describes the CANDIDATE
CORRECTED C2 design** (the F3/F4 Return correction — see
`tests/C2_RETURN_CORRECTION_REPORT.md`, `tests/C2_FAILED_RETURN_ROOT_CAUSE_ANALYSIS.md`
— the Boot/Home Confirmation correction — see
`tests/C2_BOOT_HOME_CONFIRMATION_REPORT.md`,
`docs/COMMON_NEST_INITIALIZATION_DESIGN.md` — the canonical Home/Nest
arrival correction — see `tests/C2_CANONICAL_HOME_ARRIVAL_REPORT.md` —
the sim-to-real NodeMCU ESP32 RF hardware alignment — see
`docs/NEST_BEACON_HARDWARE_PROFILE.md`,
`docs/ESP32_WROOM32_RSSI_SIM_TO_REAL_MODEL.md` — **and** the sim-to-real
software-architecture correction — see
`docs/SIM_TO_REAL_SOFTWARE_ARCHITECTURE.md`,
`tests/SIM_TO_REAL_PORTABILITY_REPORT.md`. RSSI is a dBm value via
`ESP32NestBeaconModel`/`SimulatedNestRSSIModel`, with no geometric
sim-to-real scale coupling; WM (this file's subject) was audited and
confirmed already fully backend-independent -- no change was needed here.
Home confirmation is now `home_observation.HomeConfirmationPolicy`, a
portable core the simulation adapter feeds via `HomeObservation`).
It has not been frozen or research-approved; `C2_RETURN_CORRECTION_REPORT.md`
concludes `FURTHER DIAGNOSIS REQUIRED`, not ready-for-freeze. The lifecycle
and final-approach/route-reacquisition sections below reflect the corrected
behavior currently in `src/swarm_simulate/swarm_baseline.py` and
`src/swarm_simulate/c2_working_memory.py`.

**Canonical wording (superseding any earlier wording in this document):**
- Each Scout maintains its own cycle-local Home Origin, always its own
  `(0,0)` local frame at that Scout's own current position when a cycle
  starts. Origins are **not** shared between Scouts and **not** forced to
  equal the Nest centroid or any global coordinate.
- Working Memory guides Return navigation; local ToF obstacle safety may
  temporarily override it, exactly as before.
- RSSI is HOME CONFIRMATION ONLY — both at Boot and at Return arrival. It
  is never a bearing, distance, steering, or navigation input in either C1
  or C2.
- Nest arrival requires physical membership in the configured Home/Nest
  region **plus** RSSI confirmation — the single canonical
  `_environment_home_confirmed` predicate, used identically for Boot and
  Return (Test HOME-14).
- Returning exactly to the previous local origin (or to any other specific
  point) is **not** required (Test HOME-9) — entering the shared Home/Nest
  region with a passing RSSI reading anywhere inside it is sufficient.

## Boot/Home Confirmation (common infrastructure, precedes WM entirely)

Before any EXPLORE motion or WM initialization, every Scout (C1 and C2
alike) goes through a fixed Boot/Home Confirmation sequence owned by the
environment, not by any Scout: `SCOUT_BOOT` → `HOME_RSSI_SAMPLE` →
`HOME_PHYSICAL_REGION_CHECK` → `HOME_CONFIRMED`. WM size is provably 0
before `HOME_CONFIRMED` (WM's `start_cycle()` is only called after, and only
for C2). A Scout that is not physically inside the derived Home region, or
whose RSSI does not meet the Home confirmation threshold, causes a fail-fast
`RuntimeError("INVALID_INITIAL_HOME_STATE: ...")` rather than a silent
false origin. Full derivation of the Home region, Nest center, and RSSI
threshold is in `docs/COMMON_NEST_INITIALIZATION_DESIGN.md`. The Nest is
environment-owned (the centroid of the configured Scout start layout),
identical for C1 and C2 (Test HOME-5) — this is the shared Nest BEACON/
REGION center, distinct from each Scout's own local Home ORIGIN (above).

Return arrival (`NEST_REACHED`) now uses this exact same
`_environment_home_confirmed` predicate — not the old, separate, much
tighter `nest_delivery_radius_m` (0.12 m) "delivery point" rule. That
constant was audited (`tests/C2_CANONICAL_HOME_ARRIVAL_REPORT.md`) and
found to represent only a historical arrival-point approximation, not a
real physical docking mechanism; there is no requirement that a Scout
return to one tiny docking point.

## Boundary

C2 differs from C1 only when `SWARM_EXPERIMENT_MODE=working_memory`.
Experience Memory, exchange, AIH, maps, planners and ground-truth coordinates
remain off. With WM off, `BaselineSwarmRunner` does not read WM or alter its
existing C1 action/RNG path.

## Data structure and bound

Each Scout owns one `CycleWorkingMemory`. An entry is `(cycle_id, x, y)` in an
arbitrary local odometric frame whose origin/heading reset at cycle start. It
contains no world/Nest/Resource coordinate. Entries are added only after at
least `0.25 m` of executed outbound translation; at most 300 are kept. If full,
the oldest non-origin entry is pruned, retaining the current-cycle origin.

## Lifecycle

0. **Boot/Home Confirmation** (see section above): `SCOUT_BOOT` →
   `HOME_RSSI_SAMPLE` → `HOME_PHYSICAL_REGION_CHECK` → `HOME_CONFIRMED`.
   Only after this does Cycle-1 begin.
1. `EXPLORE`: start with a local origin and record executed own-motion.
2. `HARVEST_COMPLETE`: the Scout enters `RETURN_HOME` (never Explore).
3. `RETURN_HOME`: consume newest breadcrumbs first. The local controller turns
   in 45-degree primitives toward the next recorded local waypoint, using the
   existing live local collision clearance before forward movement.
4. `DELIVER`: reset WM, then begin the next cycle with a new local origin.

The stored route cannot outlive the cycle. C2 does not replay a precomputed
motor command list and does not compute a shortest path.

### Final-origin behavior (F4 correction)

The final current-cycle breadcrumb — the local origin itself — is a valid
WM retrace target on its own, for as long as it is the only entry left.
Earlier development builds stopped using WM guidance the instant only that
one entry remained (even though it still held a precise, valid target),
handing control to the untargeted C1 stateless fallback for the rest of
the episode. The corrected controller keeps steering toward that final
entry instead; `pop_if_reached` still never removes it (`len(entries) > 1`
guards that removal specifically), so this cannot invent or lose a
waypoint — it only lets the final approach finish instead of stopping one
step early. See `tests/C2_FAILED_RETURN_ROOT_CAUSE_ANALYSIS.md` Part K/F4
for the original defect evidence and `tests/C2_RETURN_CORRECTION_REPORT.md`
Parts A/P for the fix and its confirmed 0-recurrence result.

### Obstacle override and route reacquisition (F3 correction)

WM remains the navigation authority for C2 Return; local obstacle
avoidance may still temporarily override it for safety, exactly as
before. What changed: if the *same* active WM retrace target has not
yielded at least one breadcrumb-spacing (`spacing_m`, unchanged at 0.25 m)
of net local progress within a bounded window
(`return_stationary_turn_limit` ticks — the pre-existing pathology bound
already used for the separate, reporting-only stationary-rotation-deadlock
detector), the controller treats that target as temporarily unreachable
and calls `CycleWorkingMemory.skip_unreachable`, which pops it (using the
exact same guard and mechanism as a normal "reached" pop — the origin
entry is still never removed this way) so retrace resumes on the
next-older current-cycle breadcrumb. This uses only information already
stored in WM and this Scout's own current local odometry; it adds no map,
coordinate, or path beyond what was already recorded, and it is fully
gated to `working_memory_enabled=True` (confirmed 0 C1 behavioral
mismatch). See `tests/C2_FAILED_RETURN_ROOT_CAUSE_ANALYSIS.md` Part I/F3
for the original defect evidence (a literal, bit-for-bit repeating
frozen-position deadlock) and `tests/C2_RETURN_CORRECTION_REPORT.md` Parts
B/O for the fix and its confirmed 0-recurrence result for that specific
mechanism.

**Open finding, not yet root-caused or corrected** (see
`tests/C2_RETURN_CORRECTION_REPORT.md` Parts N/O/Q/S for full evidence):
route reacquisition eliminates the frozen-position deadlock, but in 7 of 9
corrected-run failures the Scout now repeatedly reacquires new targets
without ever converging back near its own recorded cycle origin — a
different, not-yet-diagnosed pattern. Separately, for a Scout's first
cycle, the local origin is still that Scout's own boot/mission-start
position, not a value validated against the Nest — Boot/Home Confirmation
(see section above) verifies a Scout is physically *near* the Nest at boot,
but does not reposition WM's local origin onto the Nest center itself, so
this gap remains open. Under the corrected, environment-owned Nest center
(centroid of configured starts — `docs/COMMON_NEST_INITIALIZATION_DESIGN.md`),
the exact per-Scout distances from this original diagnosis are superseded:
for the 3-Scout layout, Scout1 now starts exactly at the Nest center
(0 m), while Scout0 and Scout2 each start 0.80 m away. The qualitative
finding — Cycle-1 local origin ≠ Nest for most Scouts — still holds; only
the specific numbers changed. Neither this nor the reacquisition-pattern
finding is a recurrence of F3 or F4, and per the correction task's Stop
Rule, neither has been patched.

## Development logs

- `state_transitions.csv`: timestamp, seed, Scout, trip/cycle, previous/new
  actual phase and reason.
- `working_memory_events.csv`: sparse WM_ADD/READ/POP/PRUNE/RESET events and
  current size.
- `robot_energy_timeline.csv`: before/after/consumed energy and event fields.
- Existing Nest/Resource event ledgers remain canonical for delivery, recharge
  withdrawal, harvest and depletion.
