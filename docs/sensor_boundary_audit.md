# Condition 1 sensor boundary — RSSI baseline

| Source | Access | Classification | Permitted effect |
|---|---|---|---|
| `irsim_range_sensor.py:read` | Front-left `+20°`, front-right `-20°`, side-left `+90°`, side-right `-90°` | NOMINAL_ROBOT_SENSOR | Current local obstacle avoidance and safe turn selection. |
| `swarm_baseline.py:_forward_body_clearance_safe` | `-45°`, `+45°` range rays | COMMON_LOW_LEVEL_COLLISION_SAFETY | Rejects the immediate forward command if the circular body would clip a near corner. It cannot nominate an explore branch, Nest direction, Resource direction, or route. |
| `energy_sensor.py` | Resource geometry internal to strict-LOS solar synthesis and collection event | ENVIRONMENT/SENSOR IMPLEMENTATION | The C1 behavior receives only Solar L/C/R, detected/collection state. It does not read source x/y, distance, or bearing. |
| `swarm_baseline.py:_environment_nest_reached` | Nest geometry | ENVIRONMENT EVENT | Physical arrival/delivery detection only; it is not a steering input. |
| `swarm_baseline.py:_return_command` | RSSI-like scalar | NOMINAL_COMMON_NEST_CUE | One current scalar compared with one previous scalar sample; no position, bearing, distance, map, or route. |

Verdict: C1 behavioral navigation has four nominal local ToF channels. The two extra diagonal rays are constrained to immediate body-clearance safety.
