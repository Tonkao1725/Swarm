# C2 Working Memory acceptance test report

Date: 2026-08-24. Scope: development preparation only; no research seed was run.

| Test | Result | Evidence |
| --- | --- | --- |
| A C1 isolation | PASS | Disabled WM has size zero and no return target; C1 mode flag remains OFF. |
| B starts empty | PASS | `start_cycle` creates only the current local origin. |
| C current-cycle storage | PASS | mismatched cycle cannot add entries. |
| D return usage | PASS | current-cycle target read/pop is deterministic. |
| E reset | PASS | reset empties entries before the next cycle starts. |
| F no cross-cycle memory | PASS | old cycle target is unavailable after reset. |
| G no ground truth | PASS | pure WM module contains no Nest/Resource x/y, planner, RNG or map input. |
| H central place | PASS | `HARVEST_COMPLETE` transitions directly to `RETURN_HOME`. |
| I bound | PASS | 300-entry configured bound with prune rule; deterministic fixture exercises pruning. |
| J deterministic seed | PASS | identical executed odometry produces identical WM state. |
| Logger non-interference | PASS (static) | WM/logger modules contain no Scout RNG access; runtime C1 termination regression also passed. A reduced-logging runtime toggle is not yet implemented. |

Automated commands passed:

```text
python tests/validate_c2_working_memory.py
python tests/validate_condition_isolation.py
python tests/validate_baseline_termination_architecture.py
```

The `working_memory_events.csv` and `state_transitions.csv` files from the
development runs provide runtime evidence in addition to the unit fixture.
