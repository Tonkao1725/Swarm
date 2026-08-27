# C2 source snapshot audit

Pre-freeze DEV01–DEV03 source snapshots were inspected on 2026-08-26.
Every run contains the same ten project-local runtime artifacts:
`main.py`, `swarm_baseline.py`, `c2_working_memory.py`, `energy_sensor.py`,
`irsim_range_sensor.py`, `result_logger.py`, `experiment_modes.py`,
`robot_world.yaml`, its run runtime-world YAML, and
`resource_harvesting_config.json`.

`c2_working_memory.py` is included in all three snapshots. Python standard
library and installed packages are intentionally excluded; reproduction also
requires the documented Python/IR-SIM environment recorded in `metadata.json`.
The machine-readable per-run SHA256 listing is
`results/C2_WORKING_MEMORY_PREFREEZE/SOURCE_SNAPSHOT_MANIFEST.csv`.
