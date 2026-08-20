# PRELIMINARY C1 ADVISOR REVIEW

This is a five-seed preliminary behavioral/design-review package, not a final research dataset and not a basis for confirmatory statistics.

C1 is a stateless reactive Swarm Scout baseline. It contains the same common physical and energy infrastructure intended for later experimental conditions but has no Working Memory, Experience Memory, Experience Exchange, or Artificial Internal Hormone.

Internal Energy exists as a common system constraint, but C1 does not use Internal Energy as an adaptive behavioral decision variable.

RSSI is used only to confirm Nest arrival and is not used to navigate toward the Nest.

- Git SHA: `e0e49850b8244a9321be9f8a2bcc1b18726d79bd`
- Resource config SHA-256: `096cc6f002cd699ec030de23ad5228d6fd0ae5c2daf1eaac52c8df366764200c`
- Seeds: R01 82784102; R02 98386804; R03 358777504; R04 385197017; R05 413997162
- Mission: 3 Scouts, 3600 simulated seconds, target net Nest Energy = 6
- Features: WM OFF; EM OFF; Exchange OFF; AIH OFF

## Known limitations

Five seeds are for advisor review only. TIME_LIMIT_REACHED, low net Nest Energy, unequal Scout contributions, and occasional depletion are valid baseline outcomes when engineering validity remains VALID.

## Robot Internal Energy analysis

- Total Nest withdrawal across five seeds: `2.000000` units.
- Recharge withdrawals (Scout, time s, energy after recharge):
  - R04 Scout 0: t=1045.5; energy=2.174506
  - R05 Scout 1: t=960.7; energy=2.31585
- Depletion events (Scout, time s):
  - R01 Scout 0: t=1670.7 (cycle 1, phase DEPLETED)
  - R01 Scout 1: t=1629.7 (cycle 1, phase DEPLETED)
  - R01 Scout 2: t=1637.2 (cycle 1, phase DEPLETED)
  - R02 Scout 0: t=1718.4 (cycle 1, phase DEPLETED)
  - R02 Scout 1: t=1678.0 (cycle 1, phase DEPLETED)
  - R02 Scout 2: t=1698.4 (cycle 1, phase DEPLETED)
  - R03 Scout 0: t=1700.6 (cycle 1, phase DEPLETED)
  - R03 Scout 1: t=1689.4 (cycle 1, phase DEPLETED)
  - R03 Scout 2: t=1767.9 (cycle 1, phase DEPLETED)
  - R04 Scout 0: t=2246.9 (cycle 2, phase DEPLETED)
  - R04 Scout 1: t=1697.0 (cycle 1, phase DEPLETED)
  - R04 Scout 2: t=1668.1 (cycle 1, phase DEPLETED)
  - R05 Scout 0: t=1684.1 (cycle 1, phase DEPLETED)
  - R05 Scout 1: t=2306.4 (cycle 2, phase DEPLETED)
  - R05 Scout 2: t=1665.1 (cycle 1, phase DEPLETED)
- Survival after recharge:
  - R04 Scout 0: 1201.4 s after recharge.
  - R05 Scout 1: 1345.7 s after recharge.
