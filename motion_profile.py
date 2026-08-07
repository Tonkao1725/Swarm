from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileStep:
    requested_speed: float
    applied_speed: float
    acceleration: float
    phase: str


class TrapezoidalProfile:
    """
    Discrete trapezoidal/triangular speed profile.

    The profile accelerates toward max_speed, begins braking when the
    remaining distance requires it, and clamps the final step so the ideal
    simulator reaches the target without overshoot.
    """

    def __init__(
        self,
        max_speed: float,
        acceleration: float,
        control_period_s: float,
    ) -> None:
        if max_speed <= 0:
            raise ValueError("max_speed must be greater than zero.")
        if acceleration <= 0:
            raise ValueError("acceleration must be greater than zero.")
        if control_period_s <= 0:
            raise ValueError("control_period_s must be greater than zero.")

        self.max_speed = float(max_speed)
        self.acceleration = float(acceleration)
        self.dt = float(control_period_s)

    def next_step(
        self,
        remaining: float,
        current_speed: float,
    ) -> ProfileStep:
        if remaining <= 0:
            return ProfileStep(0.0, 0.0, 0.0, "STOPPED")

        # Maximum speed that can still stop within the remaining distance.
        braking_speed = math.sqrt(max(0.0, 2.0 * self.acceleration * remaining))
        requested_speed = min(self.max_speed, braking_speed)

        max_delta = self.acceleration * self.dt

        if requested_speed > current_speed + 1e-12:
            applied_speed = min(requested_speed, current_speed + max_delta)
            phase = "ACCELERATING"
        elif requested_speed < current_speed - 1e-12:
            applied_speed = max(requested_speed, current_speed - max_delta)
            phase = "DECELERATING"
        else:
            applied_speed = requested_speed
            phase = "CRUISING"

        # Do not travel farther than the exact remaining amount.
        applied_speed = min(applied_speed, remaining / self.dt)

        acceleration = (applied_speed - current_speed) / self.dt

        if applied_speed <= 1e-12:
            phase = "STOPPED"
        elif abs(acceleration) <= 1e-9:
            phase = "CRUISING"
        elif acceleration > 0:
            phase = "ACCELERATING"
        else:
            phase = "DECELERATING"

        return ProfileStep(
            requested_speed=requested_speed,
            applied_speed=applied_speed,
            acceleration=acceleration,
            phase=phase,
        )
