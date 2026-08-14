# Condition 1 — Baseline Research Control v1

Status: frozen research control. Do not optimise Baseline performance without a
confirmed shared engineering defect followed by renewed Baseline regression.

## Reproducible dataset

- Dataset: `results/baseline_research_20seed_v1_restart_20260814/`
- Canonical seed set: `results/baseline_research_20seed_v1/research_seed_set_v1.json`
- Research seeds: R01–R20 from that immutable manifest; reuse exactly for
  Conditions 1–6A/6B.
- Development regression seeds (not research seeds): 2118334751, 920265301,
  652974033.
- Source/config hashes and prior invalidated attempt are recorded in
  `source_freeze_restart1.json` alongside the dataset.

## Common infrastructure

Maze: `compact_complex_perfect_maze_v2`; fixed upper-right resource endpoint;
3 Scouts; circular robot radius 0.25 m; IR-SIM collision safety; dense
front/side ToF; strict-LOS three-cell solar field; 45-degree movement
primitives; 0.1 s timestep; 300 s horizon; deterministic seed handling; and
the existing CSV/JSON result schema.

Nest cue: `IDEALIZED_COMMON_STATELESS_NEST_HOMING_CUE`. It supplies only the
current nest direction. It has no route history, spatial memory, map, planner,
or prior-trip knowledge and must be identical in every condition.

Breadcrumb return is a `WORKING_MEMORY_MECHANISM`, not common infrastructure.

## Condition 1 feature boundary

WM OFF; EM OFF; Exchange OFF; AIH OFF. Allowed inputs are current local
sensors, current actuator safety state, the current common nest cue, seeded
stochastic reactive decisions, and physical resource occupancy. Forbidden:
breadcrumb, visited branch/loop memory, win-shift, best route, experience,
exchange, AIH, map, or planner.

## Validation evidence

The restart dataset contains 20/20 completed and experimentally valid runs
(60 Scout observations). Full natural lifecycle proof is R03 / seed 358777504
/ Scout 2: detect 167.7 s; collect and return start 167.8 s; nest reached
281.0 s; deliver and next-trip start 281.1 s; nest energy 0 to 1.

Observed distribution is intentionally not optimised: 18/60 discovery and
collection; 1/60 delivery; 18/20 simulations with discovery; 1/20 simulations
with delivery. Low delivery is valid control performance, not a defect.
