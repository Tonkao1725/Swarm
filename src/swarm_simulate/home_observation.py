"""Portable Home-confirmation domain object and policy.

This module is the PORTABLE_CORE of Home confirmation: it contains no
IR-SIM import, no ESP-IDF/hardware-profile import, no world-coordinate
concept, and no geometric scale conversion. It is written so the exact
same code can decide HOME_CONFIRMED for a simulated Scout or a real Scout,
given only an abstract observation.

Sim-to-Real goal (see docs/SIM_TO_REAL_SOFTWARE_ARCHITECTURE.md): the same
core decision code should be reusable on real hardware. Simulation and real
robots may have different physical scale, different sensor backends, and
different calibrated thresholds -- only the DECISION LOGIC and the
OBSERVATION SHAPE need to match.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class HomeObservation:
    """The only Home-relevant information the portable policy ever sees.

    nest_presence: whether *some* physical/logical Home-presence signal
        currently reports True. In simulation this is environment ground
        truth (`NestRegion.contains(pose)` or equivalent); on real
        hardware the concrete mechanism is not yet decided (see
        `RealHomeAdapterStub` below) -- the policy does not need to know
        which.
    rssi_dbm: the current Nest Beacon RSSI reading in dBm, or None if no
        reading is currently available (e.g. radio not yet associated).
    """

    nest_presence: bool
    rssi_dbm: float | None


class HomeConfirmationPolicy:
    """HOME_CONFIRMED = nest_presence AND rssi_dbm is not None AND
    rssi_dbm >= threshold_dbm. Both conditions independently required --
    RSSI alone (e.g. a strong reading from an adjacent corridor or through
    a wall) is never sufficient; nest_presence alone (with no/failing RSSI)
    is never sufficient either.

    `threshold_dbm` is deployment configuration, not part of this class's
    code -- the SAME policy code runs with a simulation-calibrated
    threshold in simulation and a hardware-calibrated threshold on real
    Scouts (see docs/SIM_TO_REAL_SOFTWARE_ARCHITECTURE.md).
    """

    def __init__(self, threshold_dbm: float) -> None:
        self.threshold_dbm = float(threshold_dbm)

    def evaluate(self, observation: HomeObservation) -> bool:
        return (
            observation.nest_presence
            and observation.rssi_dbm is not None
            and observation.rssi_dbm >= self.threshold_dbm
        )


class HomeAdapter(Protocol):
    """The contract any backend (simulation or real) must satisfy to
    supply a `HomeObservation` to `HomeConfirmationPolicy`. Structural
    (Protocol), not a base class Scouts must inherit from -- a simulation
    adapter and a future real adapter each implement `read` independently."""

    def read(self) -> HomeObservation: ...


class RealHomeAdapterStub:
    """Documented contract point for the future real-hardware Home
    adapter. Deliberately NOT an implementation -- no real Home-presence
    sensing mechanism is decided in this task.

    REAL_NEST_PRESENCE_SENSOR = "TBD / HARDWARE DESIGN PENDING"

    A future real adapter must implement `read() -> HomeObservation`
    (satisfying the same `HomeAdapter` protocol the simulation adapter
    satisfies) using whatever physical Home-presence mechanism is
    eventually designed (e.g. a proximity/contact sensor, a dedicated IR
    beacon, a docking switch -- not decided here) plus the real ESP32's
    actual Wi-Fi RSSI reading for `rssi_dbm`. `HomeConfirmationPolicy`
    requires no change to consume it.
    """

    REAL_NEST_PRESENCE_SENSOR = "TBD / HARDWARE DESIGN PENDING"

    def read(self) -> HomeObservation:
        raise NotImplementedError(
            "RealHomeAdapterStub.read() is an intentionally unimplemented "
            "contract point -- REAL_NEST_PRESENCE_SENSOR = "
            f"{self.REAL_NEST_PRESENCE_SENSOR}. Implement this once the "
            "real Home-presence mechanism is designed; it must return a "
            "HomeObservation(nest_presence=..., rssi_dbm=...) from real "
            "sensor/radio reads, with no simulation dependency."
        )
