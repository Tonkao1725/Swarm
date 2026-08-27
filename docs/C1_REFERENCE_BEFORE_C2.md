# C1 Reference before C2 development

Recorded before creating `c2-working-memory-dev` from C1 checkpoint
`2cc0275bf29c40fedfba44e8865ac5696d61ec94` on branch `main`.

This reference is protected as existing output: `results/ADVISOR_REVIEW_C1_5SEEDS`
and `results/RAW_EXPORT_C1_R01_R05` are not regenerated or overwritten by C2.

## Common configuration

- Environment: original validated fixed 14 m × 14 m maze, 0.18 m walls; three
  0.25 m-radius Scouts start at the Nest-side corridor.
- Nest: physical entry at the common Nest, scalar RSSI-like cue for
  confirmation only (not a bearing/vector navigation input).
- Resources: persistent A `(3,3)`, B `(7,7)`, C `(11.875,11.875)` m, harvest
  rates `0.025`, `0.050`, `0.100` pilot-normalized units/s respectively;
  payload target `1.0`.
- Energy: Scout capacity/initial energy `3.0`; movement cost `0.01` per
  encoder-distance unit; valid delivery transfers carried payload to Nest.
- Mode: `research`; horizon `3600 s`; Nest target `6` net units; three Scouts.
- Sensor boundary: current local ToF/LiDAR and strict-LOS Solar L/C/R only.
- C1 flags: WM OFF, Experience Memory OFF, Exchange OFF, AIH OFF.

## Advisor-review seeds (not rerun here)

| Run | Seed |
| --- | ---: |
| R01 | 82784102 |
| R02 | 98386804 |
| R03 | 358777504 |
| R04 | 385197017 |
| R05 | 413997162 |
