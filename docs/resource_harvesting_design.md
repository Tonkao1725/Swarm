# Persistent Three-Resource Harvesting Design

This is common experimental infrastructure for later C1–C6 development, not final research data.

## Pilot model

The sources are persistent light-energy fields. They do not disappear, deplete, or become exclusively owned when a Scout reaches them. More than one Scout may harvest from the same valid near field at once.

| ID | Position (m) | Category | Pilot normalized harvest rate |
| --- | --- | --- | --- |
| A | (3.0, 3.0) | near / low | 0.025 |
| B | (7.0, 7.0) | medium / medium | 0.050 |
| C | (11.875, 11.875) | far / high | 0.100 |

These are transparent `PILOT_NORMALIZED_HARVEST_RATES`, not Watts, Volts, Amps, dBm, or measured solar-cell properties. They will be replaced only through `config/resource_harvesting_config.json` after physical P=VI calibration.

## C1 lifecycle

`EXPLORE → RESOURCE_LIGHT_DETECTED → RESOURCE_APPROACH → HARVEST_START → HARVEST_ACTIVE → HARVEST_COMPLETE → RETURN_HOME → NEST_REACHED → DELIVER → NEXT_TRIP_START → EXPLORE`

The behavioral controller uses local Solar Left/Center/Right, valid near-field state, current local ToF, and the scalar RSSI-like Nest cue. It never receives Resource global coordinates, exact distance, exact bearing, source rank, or harvest rate as a strategic input.

## Energy accounting

For a valid near-field, strict-LOS harvesting tick:

`carried_harvest_energy = min(HARVEST_PAYLOAD_TARGET, carried_harvest_energy + relative_harvest_rate × dt)`

`HARVEST_PAYLOAD_TARGET = 1.0` and `NEST_ENERGY_TARGET = 6.0` in the pilot configuration. On a valid delivery, the Nest receives the Scout's actual carried harvested energy, then that Scout's carried buffer resets. Mission success is based only on cumulative Nest Energy.

If strict LOS or the near-field condition is lost, harvesting pauses immediately. Accumulated carried energy is retained and may resume accumulating only after the valid condition returns. No energy may accumulate through a wall or as a function of wall-clock time.
