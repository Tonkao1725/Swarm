# Termination Contract Test L

Executed 2026-08-26 with `tests/validate_c1_all_depleted_termination.py` and
`tests/validate_baseline_termination_architecture.py`.

| Case | Expected | Actual | Result |
| --- | --- | --- | --- |
| L1/L6 target delivery | target success has priority; no post-success withdrawal | `NEST_ENERGY_TARGET_REACHED` is checked before recharge handling | PASS |
| L2 all Scouts depleted away from Nest | immediate colony failure before horizon | `COLONY_FAILURE_ALL_DEPLETED` | PASS |
| L3 active Scout at horizon | time-limit outcome | `TIME_LIMIT_REACHED` | PASS |
| L4 zero energy at Nest with Nest energy | not permanently depleted | recharge predicate restores rather than terminates | PASS |
| L5 mixed active/depleted | do not terminate colony | active Scout prevents all-depleted predicate | PASS |

The contract order is success, all-depleted, then time limit. The predicate is
colony-level and considers physical Nest recharge availability.
