# Common Nest / Boot / Home Confirmation — Design Reference

Status: implemented, unit-tested (HOME-1..HOME-15), not yet frozen.
Scope: common infrastructure shared by Condition 1 (C1, baseline) and
Condition 2 (C2, Working Memory). Applies identically to both; only C2 opens
a Working-Memory (WM) cycle after confirmation, C1 does not.

**2026-08-27 canonical-arrival update:** see
`tests/C2_CANONICAL_HOME_ARRIVAL_REPORT.md` for the full current design.

**2026-08-27 sim-to-real RF hardware update:** the Nest Beacon RSSI is now
a dBm value from a NodeMCU ESP32 / ESP32-WROOM-32 hardware-profile-driven
model (`ESP32NestBeaconModel`), replacing the previous unitless 0-1
scalar. See `docs/NEST_BEACON_HARDWARE_PROFILE.md` and
`docs/ESP32_WROOM32_RSSI_SIM_TO_REAL_MODEL.md`. The Home/Nest region
geometry and confirmation logic described below are unchanged by this --
only the RSSI value's units and source model changed.

**2026-08-27 architecture-correction update:** the NodeMCU ESP32 hardware
profile is a REAL HARDWARE REFERENCE; the active simulation RSSI model is
a separate SIMULATED RSSI SENSOR MODEL (`SimulatedNestRSSIModel`) with no
geometric sim-to-real scale coupling in its causal path. The Home
confirmation decision itself is now a portable `HomeConfirmationPolicy`
(`home_observation.py`) fed by a `HomeObservation` the simulation adapter
builds -- see `docs/SIM_TO_REAL_SOFTWARE_ARCHITECTURE.md`. Physical scale
conversion (`sim_to_real_linear_scale`, the real-scaled Nest rectangle) is
OFFLINE/METADATA only; it does not affect the active behavioral
experiment.
Two corrections from the original version of this document:
1. Boot/Home confirmation and Return arrival now share **one** canonical
   predicate, `_environment_home_confirmed(pose)` — Return no longer uses a
   separate, much tighter `nest_delivery_radius_m` (0.12 m) "delivery
   point." That constant is audited and confirmed to represent only a
   historical arrival-point approximation, not a real docking mechanism,
   and is kept in source only as an unused, clearly-historical attribute.
2. Each Scout's Home ORIGIN (its own local `(0,0)` odometric frame) is
   never the same as the shared Nest BEACON/REGION center described below.
   The beacon/region center is one physical point the environment owns (as
   a real ESP32 Beacon would be); each Scout's own boot pose becomes its
   own local origin, and different Scouts legitimately have different
   origins (Test HOME-8). Returning to that exact origin point is never
   required (Test HOME-9) — only entering the shared Home/Nest region with
   a passing RSSI reading is.

## 1. Real-hardware motivation

On real hardware a Scout is physically placed inside the Nest enclosure,
boots, and only *after* it receives a valid ESP32 Beacon RSSI reading and
confirms it is physically inside the Nest does it initialize its own
odometric Home origin and (for C2) start Cycle-1 Working Memory. Boot
position alone is never trusted as Home — RSSI is confirmation, not a
coordinate source, and the controller never reads Beacon x/y.

This design reproduces that lifecycle in simulation.

## 2. Three previously-conflated concepts, now separated

| Concept | Old code | New code | Purpose |
|---|---|---|---|
| **NEST / HOME REGION** | not modeled; boot pose trusted implicitly | `home_region_radius_m` around an environment-owned Nest center | Physical containment check at boot — "is this Scout actually inside the Nest enclosure?" |
| **NEST BEACON** | `IdealizedRSSILikeNestBeacon` at `self._pose(env, 0)` (Scout 0's pose) | same beacon type, centered on the environment-owned Nest center | Idealized scalar RSSI-like signal, monotonically decreasing with distance; confirmation-only, never exposes x/y |
| **DELIVERY / HOME CONFIRMATION RADIUS** | `nest_delivery_radius_m = 0.12` m, used only by `_environment_nest_reached` | unchanged, `nest_delivery_radius_m = 0.12` m | Tight Return-arrival / colony-recharge trigger — proven (audit below) to already be too small to represent the whole physical Nest, so it was never repurposed for boot containment |

### Pre-edit audit finding (why 0.12 m could not be reused as the Home region)

`_ROBOT_RADIUS_M = 0.25` m (from `config/robot_world.yaml`'s `shape.radius`
and `_add_scouts`). A physical containment radius smaller than the robot's
own body radius (0.12 m < 0.25 m) cannot represent a region a robot's center
can occupy while the robot's body stays inside a Nest enclosure — it is
provably only a **delivery/arrival point check**, not a physical region. It
was left untouched; a new, separately-derived `home_region_radius_m` was
added instead of stretching this constant beyond its proven meaning.

## 3. Nest ownership: environment, not Scout 0

Old: `nest_pose = self._pose(env, 0)` — the Nest center was read back from
Scout 0's simulated pose. This is backwards: the environment should define
where the Nest is; Scout 0 should not incidentally *be* the Nest definition.

New: the Nest center is the **centroid of the configured Scout start
positions**, computed from static config alone (`_SCOUT_START_STATES`),
never read back from any live Scout pose:

```python
_ROBOT_RADIUS_M = 0.25
_SCOUT_START_STATES = [
    [1.00, 1.00, 0.0], [1.80, 1.00, 0.0], [2.60, 1.00, 0.0], [3.35, 1.00, 0.0],
]
```

For the research `scout_count=3` configuration, the three starts used are
`[1.00,1.00]`, `[1.80,1.00]`, `[2.60,1.00]`.

- Nest center (centroid): **(1.80, 1.00)**
- Max distance from centroid to any used start: **0.80 m**
- `home_region_radius_m = 0.80 + _ROBOT_RADIUS_M = 1.05 m`
- `home_rssi_threshold = beacon.sample_at_distance(1.05) ≈ 0.6557` — derived
  from the beacon's own falloff so the physical boundary and the RSSI
  boundary agree by construction; not a guessed number.

This value is **derived, not invented**: it is the smallest radius that
still contains every configured Scout start plus each robot's own body
radius, which is the direct geometric definition of "the region a
collision-free swarm boots into."

Collision-free check: minimum pairwise distance between configured starts is
0.80 m (adjacent), well above the 2 × 0.25 m = 0.50 m non-overlap
requirement (Test HOME-7).

## 4. Boot / Home Confirmation lifecycle

For every Scout, at simulation start, before any EXPLORE motion or WM
initialization:

1. `SCOUT_BOOT` — event logged with the Scout's boot pose.
2. `HOME_RSSI_SAMPLE` — the Scout samples the Nest Beacon at its boot pose;
   `rssi` and the applicable `home_signal_threshold` are logged.
3. `HOME_PHYSICAL_REGION_CHECK` — physical containment
   (`distance(boot_pose, nest_center) <= home_region_radius_m`) is
   evaluated and logged.
4. If **both** the physical check and the RSSI threshold pass:
   `HOME_CONFIRMED` is logged, and only then (C2 only) is
   `working_memory.start_cycle()` called, followed by `SCOUT_START`.
5. If **either** check fails: `RuntimeError("INVALID_INITIAL_HOME_STATE: ...")`
   is raised (with an explicit event/file flush first) — this is a fail-fast
   configuration error, not a recoverable runtime state, because it means
   the configured Scout starts and the derived Home region are inconsistent.

Both checks are required (AND, not OR) — proven independently in Test HOME-3
by holding physical containment true while forcing the RSSI threshold to an
unreachable value.

## 5. RSSI is confirmation-only — never a steering input

`_boot_home_check` and `_environment_nest_reached` are the only two places
the Nest Beacon is read. Neither exposes `nest_x_m`/`nest_y_m` beyond a
boolean/scalar confirmation; neither computes bearing, heading, or a
distance used for steering. `_return_command` and `_explore_command` never
reference `_nest_beacon` — verified by source audit (Test HOME-4). Return
navigation is unchanged: WM (C2) or the stateless local-reactive policy (C1)
drives movement; RSSI only confirms the final physical Nest-entry event via
the pre-existing, unchanged `_environment_nest_reached`.

## 6. Simulation vs. real-hardware RSSI mapping

| | Simulation | Real hardware |
|---|---|---|
| Signal source | `IdealizedRSSILikeNestBeacon.sample()` — deterministic `1/(1+distance/scale_m)`, `scale_m=2.0` | ESP32 Beacon RF RSSI, noisy, environment-dependent |
| Used for | Boolean confirmation only (Boot/Home, Return arrival) | same intended role |
| Not used for | Bearing, distance estimate, steering, mapping | same |
| Idealization disclosed | Yes — this is deliberately noise-free/unitless, not a real RF model | n/a |

## 7. Effect on Condition 1

This is common infrastructure. Moving Nest ownership from "Scout 0's pose"
to "environment-owned start centroid" changes the *numeric position* of the
Nest for C1 exactly as it does for C2 (same method, same values — Test
HOME-5). C1's controller logic, WM (none), Return navigation, and energy
accounting are otherwise untouched.

Three pre-existing test fixtures (`tests/validate_baseline_termination_architecture.py`,
`tests/validate_c1_all_depleted_termination.py`,
`tests/validate_c1_energy_accounting.py`) place their resource endpoint at
`(1.0, 1.0)` and/or assert on `scouts[0]` specifically, both of which
implicitly assumed the old "Nest == Scout 0's boot pose" co-location. Under
the corrected centroid Nest, Scout 1 (not Scout 0) is now the one co-located
with the Nest for the 3-Scout configuration, and the endpoint at `(1.0,1.0)`
is now 0.8 m from the Nest rather than 0 m. These fixtures now fail for a
fully traced, expected reason — see
`tests/C2_BOOT_HOME_CONFIRMATION_REPORT.md` §6 — and are flagged for the
user's decision rather than modified unilaterally, since C1's frozen-control
status means any change to its fixtures is a decision point, not an
engineering default.

Old (pre-Boot/Home) C1 results remain on disk, untouched, as historical
reference. This document and the corrected geometry above are the new
common reference going forward.

## 8. Provisional status of the circular Home region

`home_region_radius_m` (1.05 m for the 3-Scout layout) remains a
DEVELOPMENT/PROVISIONAL geometry — a circle derived from the configured
Scout start layout, not a formally specified physical Nest boundary (e.g.
walls, a doorway, a mat, or another documented enclosure). No such
specification exists elsewhere in this repository as of this writing.

It has been verified, by direct line-of-sight sampling against every wall
segment in `config/robot_world.yaml` (see
`tests/C2_CANONICAL_HOME_ARRIVAL_REPORT.md` §H), to contain **no** point
that requires crossing a wall to reach from the Nest center in the current
14x14 m maze. This is empirical evidence for the current maze only, not a
general property of circular regions — a different maze layout, robot
start layout, or radius could reintroduce a "Home through a wall" case, so
this should be re-verified (the same line-of-sight method applies
directly) whenever the maze or Scout start layout changes. `Test HOME-12`
regression-guards the code-level defense (the physical-region AND RSSI
check) independent of this maze-specific finding.
