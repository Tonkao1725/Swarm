# Condition 1 common infrastructure and measurement schema v2

## Frozen research settings

- Mission mode: `research`
- Mission success: `nest_energy_units >= nest_energy_target`
- Nest-energy target: 6 units
- Maximum experiment horizon: 3600 s
- Baseline feature flags: WM OFF, EM OFF, Exchange OFF, AIH OFF

`FORAGING_TRIPS` is development tooling only and never terminates a research
mission. A delivery completes a trip; it does not complete the colony mission
unless the cumulative nest-energy target is reached.

## Common local sensing abstraction

Each robot has a noise-free dense 2D LiDAR scan spanning approximately -90 to
+90 degrees, range 0.05–5.0 m. The nominal physical directional channels are:

- FL: +20 degrees
- FR: -20 degrees
- SL: +90 degrees
- SR: -90 degrees

`front_m` is `min(FL, FR)`. Invalid beams are interpreted conservatively as
the minimum range, never as free space. The controller also queries the same
current LiDAR scan at 0, +/-45, and +/-90 degrees, plus the current nest
bearing when it lies in the LiDAR field of view. +/-45 rays are a body-corner
clearance guard for a 0.25 m circular robot; they are not additional memory,
mapping, communication, or planning capability.

This idealized current-scan sensing abstraction is common infrastructure for
Conditions 1–6A/6B. Any future condition may add its experimental mechanism,
but must retain this sensor model and physics.

## Return-cycle classification

The 3-seed 3600 s development stress run had physical movement and substantial
nest-distance reduction after collection, with no contact-stall, zero-motion,
or stationary-arbitration failure. Subsequent local repetition occurs because
the stateless controller has no information that a local action/region was
recently encountered. It is therefore classified as a legitimate Baseline
Working-Memory limitation, not an engineering defect.

Passive revisit/repetition diagnostics are calculated only after a run from
trajectory and action history. They never feed the controller, RNG, state
machine, sensor readings, physics, or actuation.

## Metric hierarchy

Primary colony metrics: mission outcome, time to target, Nest Energy versus
time, final energy, and delivery/energy rate.

Secondary behavioural metrics: outcome funnel, return progress, coverage versus
distance, trips/deliveries per Scout, passive repetition diagnostics, and
exploration efficiency.

## Frozen graph framework

The final framework has seven Common Graphs: (1) foraging-episode funnel,
(2) return progress, (3) coverage versus distance, (4) Nest Energy versus
time, (5) final energy/mission outcome by seed, (6) trips and deliveries per
Scout, and (7) foraging efficiency rate. The funnel unit is a trip/foraging
episode, never a unique Scout count.

Three future AIH-specific graphs are frozen as schema requirements only:
AIH level versus time per Scout, AIH level versus decision/behaviour, and
individual behavioural change versus matched colony performance (C4 vs C6A;
C5 vs C6B). Baseline writes AIH fields as disabled/null/zero and does not
generate AIH state or implement AIH behaviour.
