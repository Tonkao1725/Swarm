# Sim-to-Real Software Architecture

Status: DEVELOPMENT. Corrects the interpretation used in the immediately
preceding RF-hardware-alignment task. See
`tests/SIM_TO_REAL_PORTABILITY_REPORT.md` for validation evidence.

## SIM-TO-REAL GOAL

Same decision/controller software and sensor semantics across simulation
and the real robot.

## NOT REQUIRED

Geometric scale equivalence between simulation and the real world. The
simulation robot, arena, and Nest region do not need to be numerically
scaled versions of the real robot/Nest. Scale is not currently the
research variable.

## What must transfer (shared, portable)

- Controller state machine (EXPLORE / HARVEST / RETURN_HOME / DELIVER / …)
- Working Memory logic (`c2_working_memory.CycleWorkingMemory`)
- Return logic (WM breadcrumb retrace + local obstacle safety)
- Home-confirmation logic (`home_observation.HomeConfirmationPolicy`)
- Energy logic
- Later: EM, Exchange, AIH
- Decision semantics and sensor/observation data interfaces

## What may differ (backend-specific)

- Sensor backend (IR-SIM ToF vs. physical ToF; simulated Solar vs. ADC)
- Actuator backend (IR-SIM motion vs. real motor driver)
- Environment implementation (IR-SIM world vs. real Nest/maze)
- Calibrated hardware parameters (RSSI threshold, TX power, etc.)
- Physical dimensions (robot size, Nest size, arena size)

## Architecture diagram

```
                 SHARED CORE CONTROLLER
              (state machine, WM, Home policy,
               energy policy, later EM/Exchange/AIH)
                         |
          --------------------------------
          |                              |
      SIM ADAPTERS                   REAL ADAPTERS
          |                              |
 IR-SIM ToF (IRSimDirectionalRangeSensor)   physical ToF sensors
 simulated Solar (RandomEndpointEnergySensor) ADC / solar sensors
 simulated encoders (IR-SIM pose deltas)     real wheel encoders
 simulated Nest Beacon (ESP32NestBeaconModel) ESP32 Wi-Fi RSSI (real radio)
 SimNestPresenceAdapter (NestRegion.contains) RealHomeAdapterStub (TBD)
 IR-SIM motors (env.step)                    real motor driver
```

The controller does not need to know "is this simulation or hardware?" --
it consumes the same logical data structures either way.

## Portable domain objects

Preferred shared conceptual inputs (minimum refactor -- only introduced
where not already present):

- `HomeObservation(nest_presence: bool, rssi_dbm: float | None)` --
  `home_observation.py`. Consumed by `HomeConfirmationPolicy.evaluate(...)`.
- Odometry: WM already consumes `moved_m: float, heading_delta_rad: float,
  cycle_id: int` via `update_executed_motion` -- no change needed, already portable.
- Range/Solar/Energy observations: existing `IRSimDirectionalRangeSensor`
  snapshot and `EnergyReading` already carry only scalar/logical fields
  into the controller (front/left/right ranges, detected/guidance) -- not
  restructured in this task; flagged as already reasonably portable, no
  redesign performed (minimum-refactor principle).

## Home confirmation: portable core + adapters

```
HOME_CONFIRMED = observation.nest_presence
                 AND observation.rssi_dbm is not None
                 AND observation.rssi_dbm >= threshold_dbm
```

- **`HomeConfirmationPolicy`** (`home_observation.py`): PORTABLE_CORE. No
  IR-SIM, no ESP-IDF, no world pose. Same code decides for sim or real.
- **Simulation adapter** (`BaselineSwarmRunner._environment_home_confirmed`):
  builds `HomeObservation` from environment ground truth
  (`NestRegion`/`home_region_radius_m` membership -> `nest_presence`) and
  the simulated Beacon (`ESP32NestBeaconModel.sample(pose)` -> `rssi_dbm`),
  then calls the policy. `NestRegion.contains()`-style ground truth is
  acceptable as SIMULATION ENVIRONMENT GROUND TRUTH; it is not a
  dependency of the portable policy itself.
- **Real adapter** (`home_observation.RealHomeAdapterStub`): a documented,
  intentionally-unimplemented contract point.
  `REAL_NEST_PRESENCE_SENSOR = "TBD / HARDWARE DESIGN PENDING"` -- no real
  Home-presence mechanism is invented in this task. A future
  implementation must return the same `HomeObservation` shape from real
  sensors/radio; `HomeConfirmationPolicy` requires no change to consume it.

`home_signal_threshold` is a **configuration value**
(`SIMULATION_DEVELOPMENT_THRESHOLD` in simulation), not part of the
policy's code. The same code runs with a simulation-calibrated threshold
in simulation and a hardware-calibrated threshold on real Scouts.

## RSSI model

`ESP32NestBeaconModel` (simulation sim adapter) wraps
`nest_beacon_hardware.SimulatedNestRSSIModel` -- a SIMULATED RSSI SENSOR
MODEL with dBm-compatible output semantics. It operates directly on
simulation-scale distance; it does **not** claim to predict the real
NodeMCU Beacon's RSSI at the same physical distance. Its purpose is to
exercise Home-signal presence, threshold confirmation, and the
no-RSSI-navigation architecture -- not to recreate final physical RF
propagation. See `docs/ESP32_WROOM32_RSSI_SIM_TO_REAL_MODEL.md`.

The NodeMCU ESP32 / ESP32-WROOM-32 hardware profile
(`nest_beacon_hardware.NODEMCU_ESP32_WROOM32_PROFILE`) is kept as a REAL
HARDWARE REFERENCE (datasheet + ESP-IDF facts, `PROVISIONAL_UNTIL_BOARD_MARKING_VERIFIED`)
-- useful for the eventual real implementation, decoupled from the active
simulation geometry model.

## Physical scale / Nest size status

Real robot diameter (~0.10 m) and real Nest size (0.25 x 0.25 m) are kept
as **PHYSICAL_IMPLEMENTATION_REFERENCE** records (`docs/PHYSICAL_SCALE_AUDIT.md`,
`docs/sim_to_real_parameter_registry.json`, `nest_beacon_hardware.REAL_ROBOT_RADIUS_M`/
`REAL_NEST_WIDTH_M`/`REAL_NEST_HEIGHT_M`), useful for future hardware
design -- but they are **not** `ACTIVE_BEHAVIORAL_SIMULATION_CONSTRAINT`s.
`swarm_baseline.py` does not import or reference them (Test PORT-11). The
active simulation NestRegion (`home_region_radius_m`, a circle derived
from Scout spawn geometry) is the simulation's own experimentally
appropriate region; every experimental Condition uses the same one (Test
RF-10/PORT-10), and it is not required to numerically match the real
25x25 cm Nest.

## Minimum implementation target achieved

- Home confirmation logic: backend-independent (`HomeConfirmationPolicy`).
- Working Memory: backend-independent (already was; confirmed by audit).
- RSSI: consistent dBm semantics across the Home-observation boundary.
- Physical-scale conversion: absent from the behavioral decision path
  (kept only as offline/metadata tooling: `sim_to_real_linear_scale()`,
  `DevelopmentFreeSpacePathLossModel`, `RectangularNestRegion.from_real_nest_spec`).
- Nest global geometry: absent from reusable controller logic (only the
  simulation adapter reads it).
- Hardware-specific RSSI acquisition: isolated in the simulation
  adapter/beacon model; a real adapter would isolate it in
  `RealHomeAdapterStub`'s eventual implementation.
