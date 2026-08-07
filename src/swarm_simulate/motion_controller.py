from __future__ import annotations

import math
from dataclasses import dataclass
from collections.abc import Callable

from motion_profile import TrapezoidalProfile
from motion_types import (
    MotionBackend,
    MotionCommandResult,
    RobotPose,
    StepTelemetry,
)


@dataclass(frozen=True)
class MotionConfig:
    linear_speed_mps: float = 0.30
    angular_speed_radps: float = 1.00
    linear_acceleration_mps2: float = 0.40
    angular_acceleration_radps2: float = 2.00
    stop_duration_s: float = 0.30


class MotionController:
    """
    Platform-independent motion primitives.

    High-level mission code calls move/turn methods. The backend decides
    whether those commands go to IR-SIM or future ESP32 hardware.
    """

    def __init__(
        self,
        backend: MotionBackend,
        config: MotionConfig,
        on_command_complete: Callable[[MotionCommandResult], None] | None = None,
    ) -> None:
        self.backend = backend
        self.config = config
        self.on_command_complete = on_command_complete

        positive_fields = {
            "linear_speed_mps": config.linear_speed_mps,
            "angular_speed_radps": config.angular_speed_radps,
            "linear_acceleration_mps2": config.linear_acceleration_mps2,
            "angular_acceleration_radps2": config.angular_acceleration_radps2,
        }
        for name, value in positive_fields.items():
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero.")

        if config.stop_duration_s < 0:
            raise ValueError("stop_duration_s must not be negative.")

    @staticmethod
    def _distance_between(start: RobotPose, end: RobotPose) -> float:
        return math.hypot(end.x_m - start.x_m, end.y_m - start.y_m)

    @staticmethod
    def _signed_angle_delta(start_rad: float, end_rad: float) -> float:
        return math.atan2(
            math.sin(end_rad - start_rad),
            math.cos(end_rad - start_rad),
        )

    def _emit_result(self, result: MotionCommandResult) -> None:
        if self.on_command_complete is not None:
            self.on_command_complete(result)

    def _run_profiled_linear(
        self,
        command: str,
        signed_distance_m: float,
    ) -> MotionCommandResult:
        start_pose = self.backend.read_pose()
        start_time = self.backend.time_s

        direction = 1.0 if signed_distance_m >= 0 else -1.0
        remaining_m = abs(signed_distance_m)
        current_speed = 0.0
        peak_speed = 0.0
        dt = self.backend.control_period_s
        previous_pose = start_pose
        no_progress_steps = 0

        profile = TrapezoidalProfile(
            max_speed=self.config.linear_speed_mps,
            acceleration=self.config.linear_acceleration_mps2,
            control_period_s=dt,
        )

        while remaining_m > 1e-12:
            step = profile.next_step(remaining_m, current_speed)
            signed_applied = direction * step.applied_speed
            signed_requested = direction * step.requested_speed
            signed_acceleration = direction * step.acceleration

            telemetry = StepTelemetry(
                action_name=command,
                motion_phase=step.phase,
                requested_linear_velocity_mps=signed_requested,
                requested_angular_velocity_radps=0.0,
                applied_linear_velocity_mps=signed_applied,
                applied_angular_velocity_radps=0.0,
                linear_acceleration_mps2=signed_acceleration,
                angular_acceleration_radps2=0.0,
            )
            self.backend.apply_velocity(telemetry)

            current_pose = self.backend.read_pose()
            physical_step = self._distance_between(previous_pose, current_pose)
            previous_pose = current_pose
            if step.applied_speed > 1e-6 and physical_step < 1e-6:
                no_progress_steps += 1
            else:
                no_progress_steps = 0
            # Stop the primitive promptly when IR-SIM collision_mode=stop has
            # frozen ground truth. Do not continue integrating a fictitious
            # requested distance for the rest of the profile.
            if no_progress_steps >= 2:
                break

            travelled_m = step.applied_speed * dt
            remaining_m = max(0.0, remaining_m - travelled_m)
            current_speed = step.applied_speed
            peak_speed = max(peak_speed, step.applied_speed)

        end_pose = self.backend.read_pose()
        duration_s = self.backend.time_s - start_time
        actual_distance = direction * self._distance_between(start_pose, end_pose)

        result = MotionCommandResult(
            command=command,
            target_value=signed_distance_m,
            actual_value=actual_distance,
            error_value=actual_distance - signed_distance_m,
            duration_s=duration_s,
            start_pose=start_pose,
            end_pose=end_pose,
            peak_linear_velocity_mps=peak_speed,
        )
        self._emit_result(result)
        return result

    def _run_profiled_turn(
        self,
        command: str,
        signed_angle_rad: float,
    ) -> MotionCommandResult:
        start_pose = self.backend.read_pose()
        start_time = self.backend.time_s

        direction = 1.0 if signed_angle_rad >= 0 else -1.0
        remaining_rad = abs(signed_angle_rad)
        current_omega = 0.0
        peak_omega = 0.0
        dt = self.backend.control_period_s

        profile = TrapezoidalProfile(
            max_speed=self.config.angular_speed_radps,
            acceleration=self.config.angular_acceleration_radps2,
            control_period_s=dt,
        )

        while remaining_rad > 1e-12:
            step = profile.next_step(remaining_rad, current_omega)
            signed_applied = direction * step.applied_speed
            signed_requested = direction * step.requested_speed
            signed_acceleration = direction * step.acceleration

            telemetry = StepTelemetry(
                action_name=command,
                motion_phase=step.phase,
                requested_linear_velocity_mps=0.0,
                requested_angular_velocity_radps=signed_requested,
                applied_linear_velocity_mps=0.0,
                applied_angular_velocity_radps=signed_applied,
                linear_acceleration_mps2=0.0,
                angular_acceleration_radps2=signed_acceleration,
            )
            self.backend.apply_velocity(telemetry)

            turned_rad = step.applied_speed * dt
            remaining_rad = max(0.0, remaining_rad - turned_rad)
            current_omega = step.applied_speed
            peak_omega = max(peak_omega, step.applied_speed)

        end_pose = self.backend.read_pose()
        duration_s = self.backend.time_s - start_time
        actual_angle = self._signed_angle_delta(
            start_pose.theta_rad,
            end_pose.theta_rad,
        )

        result = MotionCommandResult(
            command=command,
            target_value=signed_angle_rad,
            actual_value=actual_angle,
            error_value=actual_angle - signed_angle_rad,
            duration_s=duration_s,
            start_pose=start_pose,
            end_pose=end_pose,
            peak_angular_velocity_radps=peak_omega,
        )
        self._emit_result(result)
        return result

    def stop(self, duration_s: float | None = None) -> MotionCommandResult:
        duration = self.config.stop_duration_s if duration_s is None else duration_s
        if duration < 0:
            raise ValueError("duration_s must not be negative.")

        start_pose = self.backend.read_pose()
        start_time = self.backend.time_s
        dt = self.backend.control_period_s
        elapsed = 0.0

        while elapsed + 1e-12 < duration:
            telemetry = StepTelemetry(
                action_name="STOP",
                motion_phase="STOPPED",
                requested_linear_velocity_mps=0.0,
                requested_angular_velocity_radps=0.0,
                applied_linear_velocity_mps=0.0,
                applied_angular_velocity_radps=0.0,
                linear_acceleration_mps2=0.0,
                angular_acceleration_radps2=0.0,
            )
            self.backend.apply_velocity(telemetry)
            elapsed += dt

        end_pose = self.backend.read_pose()
        actual_duration = self.backend.time_s - start_time

        result = MotionCommandResult(
            command="STOP",
            target_value=duration,
            actual_value=actual_duration,
            error_value=actual_duration - duration,
            duration_s=actual_duration,
            start_pose=start_pose,
            end_pose=end_pose,
        )
        self._emit_result(result)
        return result

    def move_forward(self, distance_m: float) -> MotionCommandResult:
        if distance_m < 0:
            raise ValueError("distance_m must not be negative.")
        return self._run_profiled_linear("MOVE_FORWARD", distance_m)

    def move_backward(self, distance_m: float) -> MotionCommandResult:
        if distance_m < 0:
            raise ValueError("distance_m must not be negative.")
        return self._run_profiled_linear("MOVE_BACKWARD", -distance_m)

    def turn_left(self, angle_degrees: float) -> MotionCommandResult:
        if angle_degrees < 0:
            raise ValueError("angle_degrees must not be negative.")
        return self._run_profiled_turn(
            "TURN_LEFT",
            math.radians(angle_degrees),
        )

    def turn_right(self, angle_degrees: float) -> MotionCommandResult:
        if angle_degrees < 0:
            raise ValueError("angle_degrees must not be negative.")
        return self._run_profiled_turn(
            "TURN_RIGHT",
            -math.radians(angle_degrees),
        )
