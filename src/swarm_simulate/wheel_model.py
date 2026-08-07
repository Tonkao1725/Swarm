from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DifferentialDriveConfig:
    """
    Physical differential-drive geometry.

    IMPORTANT:
    These are initial simulation values, not final hardware calibration.
    Replace them later with measured wheel radius and wheel-track width.
    """

    wheel_radius_m: float = 0.0325
    wheel_track_m: float = 0.1400
    max_wheel_angular_speed_radps: float = 20.0


@dataclass(frozen=True)
class WheelCommand:
    requested_linear_velocity_mps: float
    requested_angular_velocity_radps: float
    requested_left_wheel_radps: float
    requested_right_wheel_radps: float
    applied_left_wheel_radps: float
    applied_right_wheel_radps: float
    reconstructed_linear_velocity_mps: float
    reconstructed_angular_velocity_radps: float
    wheel_speed_limited: bool
    wheel_scale_factor: float


class DifferentialDriveModel:
    """
    Converts robot-body velocity into left/right wheel angular velocity,
    applies wheel-speed limits, then reconstructs body velocity from wheels.

    Equations:
        left  = (v - omega * track / 2) / radius
        right = (v + omega * track / 2) / radius

        v     = radius * (right + left) / 2
        omega = radius * (right - left) / track
    """

    def __init__(self, config: DifferentialDriveConfig) -> None:
        if config.wheel_radius_m <= 0:
            raise ValueError("wheel_radius_m must be greater than zero.")
        if config.wheel_track_m <= 0:
            raise ValueError("wheel_track_m must be greater than zero.")
        if config.max_wheel_angular_speed_radps <= 0:
            raise ValueError(
                "max_wheel_angular_speed_radps must be greater than zero."
            )

        self.config = config

    def body_to_wheels(
        self,
        linear_velocity_mps: float,
        angular_velocity_radps: float,
    ) -> tuple[float, float]:
        radius = self.config.wheel_radius_m
        half_track = self.config.wheel_track_m / 2.0

        left = (
            linear_velocity_mps
            - angular_velocity_radps * half_track
        ) / radius
        right = (
            linear_velocity_mps
            + angular_velocity_radps * half_track
        ) / radius

        return left, right

    def wheels_to_body(
        self,
        left_wheel_radps: float,
        right_wheel_radps: float,
    ) -> tuple[float, float]:
        radius = self.config.wheel_radius_m
        track = self.config.wheel_track_m

        linear = radius * (
            right_wheel_radps + left_wheel_radps
        ) / 2.0
        angular = radius * (
            right_wheel_radps - left_wheel_radps
        ) / track

        return linear, angular

    def apply(
        self,
        linear_velocity_mps: float,
        angular_velocity_radps: float,
    ) -> WheelCommand:
        requested_left, requested_right = self.body_to_wheels(
            linear_velocity_mps,
            angular_velocity_radps,
        )

        peak = max(abs(requested_left), abs(requested_right))
        limit = self.config.max_wheel_angular_speed_radps

        if peak > limit:
            scale = limit / peak
            applied_left = requested_left * scale
            applied_right = requested_right * scale
            limited = True
        else:
            scale = 1.0
            applied_left = requested_left
            applied_right = requested_right
            limited = False

        reconstructed_linear, reconstructed_angular = (
            self.wheels_to_body(applied_left, applied_right)
        )

        return WheelCommand(
            requested_linear_velocity_mps=linear_velocity_mps,
            requested_angular_velocity_radps=angular_velocity_radps,
            requested_left_wheel_radps=requested_left,
            requested_right_wheel_radps=requested_right,
            applied_left_wheel_radps=applied_left,
            applied_right_wheel_radps=applied_right,
            reconstructed_linear_velocity_mps=reconstructed_linear,
            reconstructed_angular_velocity_radps=reconstructed_angular,
            wheel_speed_limited=limited,
            wheel_scale_factor=scale,
        )
