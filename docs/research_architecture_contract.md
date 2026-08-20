# Condition 1 — Frozen Research Architecture Contract

Condition 1 is a three-Scout, independent, stateless reactive baseline in the original maze.

- Research mode terminates with `MISSION_SUCCESS` only when cumulative Nest Energy reaches 6. It terminates immediately with `COLONY_FAILURE_ALL_DEPLETED` only when no Scout has a valid future recharge, delivery, or other energy-changing action; otherwise its 3600 s global horizon yields `TIME_LIMIT_REACHED`.
- One valid delivery adds one Nest Energy unit. A delivery completes one foraging episode, starts the delivering Scout's next trip, and does not stop the colony before the target.
- Working Memory, Experience Memory, Exchange, AIH, shared maps, route storage, breadcrumbs, visited-branch memory, and planners are OFF.
- Exploration receives nominal local ToF and solar L/C/R resource sensing. The Resource coordinate is available only to the environment/sensor implementation.
- Return receives only the scalar `IDEALIZED_RSSI_LIKE_COMMON_NEST_CUE`, current local ToF, current actuator maneuver state, and its seeded local random draw. It receives no Nest position, bearing, or distance.
- Physical Nest arrival is an environment event, not a navigation input.
- The common fixed Resource is at `(11.875, 11.875)` m. The common Nest is at `(1.0, 1.0)` m.
- Fast headless mode disables rendering only. It preserves timestep, physics, sensors, controller actions, RNG, global horizon, and result logging.

Research data must include the frozen metric definitions and the canonical 20-seed-set hash. Historical exact-bearing results are not part of the RSSI baseline dataset.
