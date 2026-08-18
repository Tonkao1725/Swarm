# Condition 1 — Baseline Research Freeze v2

Status: current Condition 1 research freeze.  This document supersedes
`BASELINE_CONDITION1_FREEZE_V1.md`; V1 is retained as the historical record.

## Freeze identity

- Freeze date: 2026-08-18
- Git tag: `baseline-condition1-v2`
- Git commit: the immutable commit targeted by that tag
- Canonical seed manifest:
  `results/baseline_research_20seed_v1/research_seed_set_v1.json`
- Seed manifest SHA-256:
  `85d78ecddf4623f9344ab002e9ab5b84cd8aa71bb30ac3653ebc8a8874d7edd9`
- Seed policy: exactly R01–R20 in manifest order; reuse unchanged for
  Conditions 1–6.

The manifest was recovered on 2026-08-18 from the project owner's canonical
record after the generated results folder was lost.  Its R03 value
(`358777504`) agrees with the historical V1 freeze document.

## Condition definition and feature boundary

Condition 1 is an operationally competent but behaviourally naive control:
current local ToF/LiDAR sensing, strict-LOS resource sensing, seeded reactive
exploration, an idealized instantaneous common Nest bearing, and bounded local
collision recovery.

| Capability | Condition 1 state |
| --- | --- |
| Working Memory | OFF |
| Experience Memory | OFF |
| Experience Exchange | OFF |
| Artificial Internal Hormone | OFF |
| Shared/global map or SLAM | OFF |
| Centralized controller | OFF |
| Breadcrumb / route replay | OFF |
| Junction, visited-branch, waypoint, or cross-trip preference | OFF |
| Planner / shortest-path algorithm | OFF |

The common Nest cue is `IDEALIZED_COMMON_STATELESS_NEST_HOMING_CUE`: it gives
only the current direction to the one physical colony Nest at `(1.0, 1.0)`.
It is identical infrastructure for every future Condition unless that
condition explicitly studies a change to it.

## Return-home audit

The audit verified the home-vector mathematics using
`atan2(nest_y - y, nest_x - x)` and signed wrapped angular error
`wrap(desired_heading - current_heading)`.  Positive error commands a
counter-clockwise 45-degree turn and negative error commands clockwise turn.
The audit corrected two implementation defects: all Scouts now share the
single colony Nest rather than individual start positions, and an unseen
outside-FOV Nest bearing is no longer misclassified as an observed obstacle.

`tests/controlled_return_home_diagnostic.py` is a non-research diagnostic. It
uses the production return and delivery state machine with an obstacle-free
line to the Nest and demonstrates:

`RETURN_HOME → NEST_REACHED → DELIVER → NEST_ENERGY_UPDATED → NEXT_TRIP_START`

Therefore residual no-delivery outcomes in the research maze are retained as
valid memoryless reactive outcomes unless a new demonstrable engineering
defect invalidates a run.  The controller must not be tuned post-freeze to
raise delivery rate.

Known valid limitations include slow exploration, late or absent resource
detection, local reactive detours around blocking geometry, no delivery before
the global horizon, and `TIME_LIMIT_REACHED`.

## Frozen common configuration

- Maze: `original_selected_validated_maze`, fixed 14 m × 14 m wall topology
- Nest: `(1.0, 1.0)` m; resource: `E_FIXED_NE` at `(11.875, 11.875)` m
- Scouts: 3 circular bodies, radius 0.25 m
- Wall thickness: 0.18 m; IR-SIM timestep: 0.1 s; collision mode: `stop`
- ToF/LiDAR: 0.05–5.0 m, ±90-degree FOV; local turns: 45 degrees
- Research mission mode: `research`
- Research horizon: 3600 s maximum
- Nest Energy target: 6 units
- One valid `DELIVER`: +1 Nest Energy unit
- Mission success: cumulative Nest Energy >= 6
- Otherwise termination: `TIME_LIMIT_REACHED` at the global horizon
- `FORAGING_TRIPS`: development-only tooling; never a Research Mode stop rule
- After a delivery before target: `NEXT_TRIP_START → EXPLORE`; all Scouts
  remain active until mission success or horizon.

Each research run records its freeze commit/tag, manifest hash, mode, seed,
map/config snapshot, feature states, runtime timestamps, mission outcome, and
experimental-validity classification.  Future Conditions must preserve this
common infrastructure and metric definitions unless changing that item is the
explicit independent variable.
