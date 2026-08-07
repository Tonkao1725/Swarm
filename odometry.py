from __future__ import annotations

import math
from dataclasses import dataclass

from encoder_model import EncoderSample
from motion_types import RobotPose
from wheel_model import DifferentialDriveConfig


@dataclass(frozen=True)
class OdometrySample:
    estimated_pose: RobotPose
    delta_left_distance_m: float
    delta_right_distance_m: float
    delta_center_distance_m: float
    delta_theta_rad: float


class DifferentialDriveOdometry:
    """
    Encoder-only differential-drive odometry.

    Ground-truth IR-SIM pose is used only for initialization and logging.
    Every later estimated pose update comes exclusively from encoder ticks.
    """

    def __init__(
        self,
        drive_config: DifferentialDriveConfig,
        ticks_per_revolution: int,
        initial_pose: RobotPose,
    ) -> None:
        if ticks_per_revolution <= 0:
            raise ValueError(
                "ticks_per_revolution must be greater than zero."
            )

        self.drive_config = drive_config
        self.ticks_per_revolution = ticks_per_revolution
        self._pose = initial_pose

    @property
    def pose(self) -> RobotPose:
        return self._pose

    def update(
        self,
        encoder: EncoderSample,
    ) -> OdometrySample:
        distance_per_tick = (
            2.0
            * math.pi
            * self.drive_config.wheel_radius_m
            / self.ticks_per_revolution
        )

        dl = encoder.delta_left_ticks * distance_per_tick
        dr = encoder.delta_right_ticks * distance_per_tick

        dc = (dl + dr) / 2.0
        dtheta = (
            (dr - dl) / self.drive_config.wheel_track_m
        )

        theta_mid = self._pose.theta_rad + dtheta / 2.0

        new_x = self._pose.x_m + dc * math.cos(theta_mid)
        new_y = self._pose.y_m + dc * math.sin(theta_mid)
        new_theta = math.atan2(
            math.sin(self._pose.theta_rad + dtheta),
            math.cos(self._pose.theta_rad + dtheta),
        )

        self._pose = RobotPose(
            x_m=new_x,
            y_m=new_y,
            theta_rad=new_theta,
        )

        return OdometrySample(
            estimated_pose=self._pose,
            delta_left_distance_m=dl,
            delta_right_distance_m=dr,
            delta_center_distance_m=dc,
            delta_theta_rad=dtheta,
        )
