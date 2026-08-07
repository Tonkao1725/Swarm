from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RobotPose:
    x_m: float
    y_m: float
    theta_rad: float


@dataclass(frozen=True)
class StepTelemetry:
    action_name: str
    motion_phase: str
    requested_linear_velocity_mps: float
    requested_angular_velocity_radps: float
    applied_linear_velocity_mps: float
    applied_angular_velocity_radps: float
    linear_acceleration_mps2: float
    angular_acceleration_radps2: float


@dataclass(frozen=True)
class MotionCommandResult:
    command: str
    target_value: float
    actual_value: float
    error_value: float
    duration_s: float
    start_pose: RobotPose
    end_pose: RobotPose
    peak_linear_velocity_mps: float = 0.0
    peak_angular_velocity_radps: float = 0.0


class MotionBackend(Protocol):
    """
    Hardware abstraction shared by IR-SIM and future ESP32 backends.
    """

    @property
    def control_period_s(self) -> float:
        ...

    @property
    def time_s(self) -> float:
        ...

    def read_pose(self) -> RobotPose:
        ...

    def apply_velocity(self, telemetry: StepTelemetry) -> None:
        ...

    def render(self) -> None:
        ...

    def close(self) -> None:
        ...
