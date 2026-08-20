# GRAPH DATA AUDIT — C1 Advisor Review V3

## Data scope

Passive retrospective analysis only. Raw duration remains 3600 s in the source files. **Effective termination time** is recalculated as the latest `ROBOT_DEPLETED` timestamp among the three Scouts in each run; time after that point is excluded from time-series and rate denominators under the proposed all-Scouts-depleted rule.

| Graph | Research question | Raw source / columns | Unit and calculation | Limitation |
|---|---|---|---|---|
| 1 | Colony operates how long? | swarm_events: event, sim_time_s | run; max of three ROBOT_DEPLETED timestamps | retrospective rule, not original runtime termination |
| 2 | Who withdrew Nest energy, when and how much? | swarm_events: NEST_ENERGY_WITHDRAWAL | event; timestamp and parsed withdrawal amount | only actual withdrawal events |
| 3 | What active behavior occupied time? | swarm_trajectory: sim_time_s, scout_id, phase | run; consecutive-sample phase durations summed across all 3 Scouts up to their depletion endpoint, then normalized by total active Scout-time | trajectory sample resolution is 0.1 s |
| 4 | At which C1 stage does loss occur? | swarm_events: event | event count; percentage of started cycles | collection-start event is unavailable and therefore omitted |
| 5 | How often did return physically reach Nest? | swarm_events: RETURN_HOME_START, NEST_REACHED | run; reaches / return starts | physical arrival only; not distance-reduction proxy |
| 6 | Which sources were used and delivered? | swarm_events: HARVEST_COMPLETE, DELIVER, trip_id | event count; delivery origin matched by Scout/trip | no claim of resource preference |
| 7 | When did each Scout deplete? | swarm_events: ROBOT_DEPLETED, NEST_ENERGY_WITHDRAWAL | Scout; depletion timestamp and actual recharge marker | internal energy is a physical constraint, not a C1 decision input |
| 8 | What is the Colony energy accounting? | swarm_summary.json | run; gross delivery, withdrawal, final net; rates divided by effective time | normalized simulation energy units |
| Supplementary | How did net Nest energy change? | nest_energy_timeline.csv; swarm_events | run time series truncated at effective termination | flat post-depletion 3600-s tail intentionally omitted |

## Consistency check

- Runs: 5; Scouts per run: 3; total Scouts: 15.
- Effective termination (s): R01=1670.7, R02=1718.4, R03=1767.9, R04=2246.9, R05=2306.4.
- Total source detections: 17; successful energy collections: 17; return attempts: 17; Nest reaches: 2; deliveries: 2.
- Total Nest withdrawal: 2.0 units; final Net Nest Energy: R01=0.0, R02=0.0, R03=0.0, R04=0.0, R05=0.0.
- Resource successful collections: A=9, B=6, C=2; delivery origins: A=0, B=2, C=0.

All requested behavioral duration categories that exist in the trajectory log were reconstructed. For Graph 3, 100% means **total active Scout-time** (the sum of each Scout's non-depleted trajectory duration), not wall-clock Run time. `APPROACH_RESOURCE` and a separate energy-collection-start event are not logged; neither is inferred or shown as a separate category.
