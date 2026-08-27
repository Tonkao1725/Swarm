# C2 Working Memory — three-seed development report

Development-only runs: three Scouts, research semantics, 3600 s maximum,
Nest target 6. These are engineering checks, not research data or statistics.

| Dev | Seed | Validity | Outcome | Deliveries | WM reset evidence | Contact stall / stationary deadlock |
| --- | ---: | --- | --- | ---: | --- | --- |
| DEV01 | 2118334751 | VALID | TIME_LIMIT_REACHED | 2 | Scout 0: 2 | none / none |
| DEV02 | 920265301 | VALID | TIME_LIMIT_REACHED | 0 | none (no completed cycle) | none / none |
| DEV03 | 652974033 | VALID | TIME_LIMIT_REACHED | 6 | Scout 0: 3; Scout 1: 3 | none / none |

## Runtime checks

- All runs completed without crash or NaN.
- WM ADD/READ/POP events exist in the raw per-run `working_memory_events.csv`.
- WM maximum size was bounded at 300 entries for the long routes; pruning was
  observed where required.
- No cross-cycle entry remained after delivery: reset count equals completed
  deliveries for the Scouts that completed cycles.
- No Experience Memory, Exchange, AIH, global map or shared-peer sensing was
  enabled.
- The initial C2 turn-overwrite pathology was found by the targeted smoke run,
  fixed, and the successful full runs show no stationary-turn deadlock.

## Caveat

All three runs ended at the time horizon. This is a legitimate mission
outcome under the fixed common configuration and has not been tuned. C2 is
not yet approved for the research seed set until the advisor approves it.
