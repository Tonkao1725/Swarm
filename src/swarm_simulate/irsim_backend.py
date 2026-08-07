from __future__ import annotations

from collections.abc import Callable
import numpy as np

from encoder_model import EncoderSample, EncoderSimulator
from imperfection_model import ControlledImperfectionModel, PhysicalWheelState
from motion_types import RobotPose, StepTelemetry
from odometry import DifferentialDriveOdometry, OdometrySample
from wheel_model import DifferentialDriveModel, WheelCommand


class IRSimBackend:
    """Backend containing wheel, physical-imperfection, encoder and odometry layers."""

    def __init__(
        self,
        env,
        wheel_model: DifferentialDriveModel,
        imperfection_model: ControlledImperfectionModel,
        encoder_simulator: EncoderSimulator,
        odometry: DifferentialDriveOdometry,
        on_step: Callable[[StepTelemetry, WheelCommand, PhysicalWheelState, EncoderSample, OdometrySample, RobotPose], None] | None = None,
        render_enabled: bool = True,
        render_overlay=None,
        render_every_n_steps: int = 3,
    ) -> None:
        self.env = env
        self.wheel_model = wheel_model
        self.imperfection_model = imperfection_model
        self.encoder_simulator = encoder_simulator
        self.odometry = odometry
        self.on_step = on_step
        self.render_enabled = bool(render_enabled)
        self.render_overlay = render_overlay
        self.render_every_n_steps = max(1, int(render_every_n_steps))
        self._step_counter = 0
        self._control_period_s = float(env.step_time)
        if self._control_period_s <= 0:
            raise ValueError('IR-SIM step_time must be greater than zero.')

    @property
    def control_period_s(self) -> float:
        return self._control_period_s

    @property
    def time_s(self) -> float:
        return float(self.env.time)

    def read_pose(self) -> RobotPose:
        # Ground truth remains the controller feedback source during validation.
        return self._read_ground_truth_pose()

    def read_estimated_pose(self) -> RobotPose:
        return self.odometry.pose

    def _read_ground_truth_pose(self) -> RobotPose:
        values = np.asarray(self.env.get_robot_state(), dtype=float).reshape(-1)
        if values.size < 3:
            raise RuntimeError(f'Unexpected IR-SIM robot state shape: {values.shape}')
        return RobotPose(float(values[0]), float(values[1]), float(values[2]))

    def apply_velocity(self, telemetry: StepTelemetry) -> None:
        wheel = self.wheel_model.apply(
            telemetry.applied_linear_velocity_mps,
            telemetry.applied_angular_velocity_radps,
        )
        physical = self.imperfection_model.apply(wheel)

        self.env.step(np.array([
            [physical.physical_linear_velocity_mps],
            [physical.physical_angular_velocity_radps],
        ], dtype=float))
        self._step_counter += 1
        if (
            self.render_enabled
            and self._step_counter % self.render_every_n_steps == 0
        ):
            self.env.render()
            if self.render_overlay is not None:
                self.render_overlay(
                    self._read_ground_truth_pose(),
                    float(self.env.time),
                )

        # Encoders measure the physically rotating shafts, not requested speed.
        encoder = self.encoder_simulator.update(
            physical.physical_left_wheel_radps,
            physical.physical_right_wheel_radps,
            self._control_period_s,
        )
        odometry_sample = self.odometry.update(encoder)
        truth = self._read_ground_truth_pose()

        if self.on_step is not None:
            self.on_step(telemetry, wheel, physical, encoder, odometry_sample, truth)

    def render(self) -> None:
        if self.render_enabled:
            self.env.render()
            if self.render_overlay is not None:
                self.render_overlay(
                    self._read_ground_truth_pose(),
                    float(self.env.time),
                )

    def close(self) -> None:
        self.env.end()
