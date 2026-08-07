from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from motion_types import RobotPose


@dataclass(frozen=True)
class DirectionalRangeSnapshot:
    sequence: int
    sim_time_s: float
    pose: RobotPose

    left_m: float
    front_m: float
    right_m: float

    # Physical four-ToF layout:
    # front_left / front_right / side_left / side_right.
    # front_m remains the conservative fused value used by navigation.
    front_left_m: float
    front_right_m: float

    left_valid: bool
    front_valid: bool
    right_valid: bool
    front_left_valid: bool
    front_right_valid: bool

    left_beam_index: int
    front_beam_index: int
    right_beam_index: int
    front_left_beam_index: int
    front_right_beam_index: int

    left_beam_angle_rad: float
    front_beam_angle_rad: float
    right_beam_angle_rad: float
    front_left_beam_angle_rad: float
    front_right_beam_angle_rad: float

    beam_count: int


class DirectionalRangeSensor(Protocol):
    """
    Hardware abstraction for four physical ranging channels.

    Layout:
        front-left
        front-right
        side-left
        side-right

    IR-SIM extracts these channels from a dense LiDAR scan. Navigation keeps
    using left_m / front_m / right_m, where front_m is the conservative minimum
    of front-left and front-right.
    """

    def read(self) -> DirectionalRangeSnapshot:
        ...
