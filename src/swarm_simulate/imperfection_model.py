from __future__ import annotations

from dataclasses import dataclass

from wheel_model import DifferentialDriveModel, WheelCommand


@dataclass(frozen=True)
class ImperfectionConfig:
    """Deterministic physical imperfections; each effect can be isolated."""

    enabled: bool = True
    left_motor_gain: float = 0.985
    right_motor_gain: float = 1.000
    left_wheel_radius_scale: float = 1.000
    right_wheel_radius_scale: float = 1.000


@dataclass(frozen=True)
class PhysicalWheelState:
    commanded_left_wheel_radps: float
    commanded_right_wheel_radps: float
    physical_left_wheel_radps: float
    physical_right_wheel_radps: float
    left_linear_speed_mps: float
    right_linear_speed_mps: float
    physical_linear_velocity_mps: float
    physical_angular_velocity_radps: float
    left_motor_gain: float
    right_motor_gain: float
    left_wheel_radius_m: float
    right_wheel_radius_m: float


class ControlledImperfectionModel:
    """
    Applies reproducible motor and wheel mismatches after the ideal wheel model.

    No random noise is used in Level 2D. This makes every run repeatable and
    allows one cause to be enabled at a time during debugging.
    """

    def __init__(self, drive_model: DifferentialDriveModel, config: ImperfectionConfig) -> None:
        self.drive_model = drive_model
        self.config = config
        for name, value in {
            'left_motor_gain': config.left_motor_gain,
            'right_motor_gain': config.right_motor_gain,
            'left_wheel_radius_scale': config.left_wheel_radius_scale,
            'right_wheel_radius_scale': config.right_wheel_radius_scale,
        }.items():
            if value <= 0:
                raise ValueError(f'{name} must be greater than zero.')

    def apply(self, wheel: WheelCommand) -> PhysicalWheelState:
        if self.config.enabled:
            left_gain = self.config.left_motor_gain
            right_gain = self.config.right_motor_gain
            left_scale = self.config.left_wheel_radius_scale
            right_scale = self.config.right_wheel_radius_scale
        else:
            left_gain = right_gain = left_scale = right_scale = 1.0

        physical_left = wheel.applied_left_wheel_radps * left_gain
        physical_right = wheel.applied_right_wheel_radps * right_gain

        nominal_radius = self.drive_model.config.wheel_radius_m
        left_radius = nominal_radius * left_scale
        right_radius = nominal_radius * right_scale

        left_linear = physical_left * left_radius
        right_linear = physical_right * right_radius
        physical_linear = (left_linear + right_linear) / 2.0
        physical_angular = (
            right_linear - left_linear
        ) / self.drive_model.config.wheel_track_m

        return PhysicalWheelState(
            commanded_left_wheel_radps=wheel.applied_left_wheel_radps,
            commanded_right_wheel_radps=wheel.applied_right_wheel_radps,
            physical_left_wheel_radps=physical_left,
            physical_right_wheel_radps=physical_right,
            left_linear_speed_mps=left_linear,
            right_linear_speed_mps=right_linear,
            physical_linear_velocity_mps=physical_linear,
            physical_angular_velocity_radps=physical_angular,
            left_motor_gain=left_gain,
            right_motor_gain=right_gain,
            left_wheel_radius_m=left_radius,
            right_wheel_radius_m=right_radius,
        )
