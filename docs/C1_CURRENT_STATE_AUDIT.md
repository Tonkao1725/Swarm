# C1 Current State Audit

## Active path

- Entry point: `main.py`
- C1 runner: `src/swarm_simulate/swarm_baseline.py::BaselineSwarmRunner`
- Maze: `config/robot_world.yaml`
- Three persistent source configuration: `config/resource_harvesting_config.json`
- Solar sensing: `energy_sensor.py`
- Local ToF / dense-ray adapter: `irsim_range_sensor.py`
- Headless and parallel checks: `tests/run_headless_equivalence.py`, `tests/run_parallel_equivalence.py`

## Current commit and worktree

- Base commit: `14653722720eeb0f97f8dd6c2d8ccfe904cabbee`
- The worktree is intentionally dirty with in-progress harvesting, safety, logging, and validation changes.

## Validated/in-scope infrastructure retained

- Fixed 14 m maze and local nominal ToF boundary.
- Persistent A/B/C pilot-normalized harvesting configuration.
- Strict LOS and local Solar L/C/R synthesis.
- Stateless local collision/contact safety and physical stationary-turn detection.
- Fast-headless raw-output equivalence evidence.

## Canonical C1 changes completed in this worktree

1. RETURN_HOME uses current local ToF, bounded safety state, and seeded randomness only. RSSI is sampled only by the environment-owned physical Nest-entry confirmation check.
2. Three persistent A/B/C sources use the configured pilot-normalized harvest rate × dt model. Sources have no global carrier lock and concurrent harvesting is permitted.
3. The runner records internal Robot Energy, executed-motion energy cost, depletion, basic Nest recharge, gross delivery, recharge withdrawal, and net Nest Energy separately.
4. `cycle_id` is emitted for Scout-local foraging cycles. Legacy `trip_id` remains development-compatible but cannot terminate research mode.
5. `nest_energy_timeline.csv` records `DELIVERY` and `ROBOT_RECHARGE_WITHDRAWAL` as distinct ledger events.

## Current validation status

- Targeted static and runner-level lifecycle/accounting checks: PASS.
- Fast-headless versus standard deterministic equivalence (60 s): PASS.
- Canonical 3-seed × 3600 s development validation: PASS for engineering validity, with no contact stall or stationary-turn deadlock.
- These development outputs are not research data and do not authorize a freeze or 20-seed batch yet; final static provenance/config review remains pending.

## Files expected to change

`swarm_baseline.py`, `main.py`, energy/config/logging/aggregation files, targeted tests, and C1 validation documentation.

## Files preserved

Historical result roots, prior exact-bearing/RSSI-gradient/single-resource datasets, physical-scale artifacts, and replay tooling remain untouched and unmerged.
