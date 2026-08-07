from __future__ import annotations

import math
from typing import Any

import numpy as np

from motion_types import RobotPose
from sensor_types import DirectionalRangeSnapshot


class IRSimDirectionalRangeSensor:
    """
    Extract four physical ToF channels and arbitrary line-of-sight rays from
    a dense IR-SIM LiDAR scan.

    Physical layout:
        FRONT_LEFT  = +20 degrees
        FRONT_RIGHT = -20 degrees
        SIDE_LEFT   = +90 degrees
        SIDE_RIGHT  = -90 degrees

    The navigation-facing front_m value is:
        min(front_left_m, front_right_m)

    This prevents the robot centre ray from passing beside a wall edge while
    the circular robot body collides with it.
    """

    def __init__(
        self,
        env,
        range_max_m: float,
        minimum_beam_count: int = 90,
        maximum_direction_error_deg: float = 2.0,
    ) -> None:
        if range_max_m <= 0:
            raise ValueError("range_max_m must be greater than zero.")
        if minimum_beam_count < 3:
            raise ValueError("minimum_beam_count must be at least 3.")
        if maximum_direction_error_deg <= 0:
            raise ValueError(
                "maximum_direction_error_deg must be greater than zero."
            )

        self.env = env
        self.range_max_m = range_max_m
        self.minimum_beam_count = minimum_beam_count

        # IR-SIM marks hits closer than the configured LiDAR range_min as
        # invalid. Invalid must be treated as near/unsafe, not as free space.
        self.range_min_m = 0.05
        self.maximum_direction_error_rad = math.radians(
            maximum_direction_error_deg
        )

        # Match the intended real robot geometry. The exact mechanical angle
        # can later be calibrated without changing controller logic.
        self.front_left_angle_rad = math.radians(20.0)
        self.front_right_angle_rad = math.radians(-20.0)

        self._sequence = 0

    def _pose(self) -> RobotPose:
        values = np.asarray(
            self.env.get_robot_state(),
            dtype=float,
        ).reshape(-1)
        if values.size < 3:
            raise RuntimeError(
                f"Unexpected robot state shape: {values.shape}"
            )
        return RobotPose(
            x_m=float(values[0]),
            y_m=float(values[1]),
            theta_rad=float(values[2]),
        )

    @staticmethod
    def _scalar(scan: dict[str, Any], key: str) -> float | None:
        if key not in scan:
            return None
        values = np.asarray(scan[key], dtype=float).reshape(-1)
        if values.size == 0:
            return None
        return float(values[0])

    def _extract_angles(
        self,
        scan: dict[str, Any],
        count: int,
    ) -> np.ndarray:
        angle_min = self._scalar(scan, "angle_min")
        angle_increment = self._scalar(scan, "angle_increment")
        if angle_increment is None:
            angle_increment = self._scalar(scan, "angle_inc")

        if angle_min is not None and angle_increment is not None:
            return angle_min + np.arange(count) * angle_increment

        for key in ("angles", "angle_list", "angle"):
            if key in scan:
                values = np.asarray(
                    scan[key],
                    dtype=float,
                ).reshape(-1)
                if values.size == count:
                    return values

        raise RuntimeError(
            "LiDAR scan does not expose usable angle metadata. "
            f"Available keys: {sorted(scan.keys())}"
        )

    @staticmethod
    def _nearest_index(
        angles: np.ndarray,
        target_rad: float,
    ) -> tuple[int, float]:
        errors = np.abs(
            np.arctan2(
                np.sin(angles - target_rad),
                np.cos(angles - target_rad),
            )
        )
        index = int(np.argmin(errors))
        return index, float(errors[index])

    def _clean_scan(
        self,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        scan = self.env.get_lidar_scan()
        if not isinstance(scan, dict):
            raise RuntimeError(
                "IR-SIM get_lidar_scan() did not return a dictionary."
            )
        if "ranges" not in scan:
            raise RuntimeError(
                "IR-SIM LiDAR scan has no 'ranges' field."
            )

        ranges = np.asarray(
            scan["ranges"],
            dtype=float,
        ).reshape(-1)
        if ranges.size < self.minimum_beam_count:
            raise RuntimeError(
                "Directional extraction requires a dense LiDAR scan. "
                f"Expected at least {self.minimum_beam_count} beams, "
                f"received {ranges.size}."
            )

        angles = self._extract_angles(scan, ranges.size)

        if "valid" in scan:
            valid = np.asarray(
                scan["valid"],
                dtype=bool,
            ).reshape(-1)
            if valid.size != ranges.size:
                valid = np.isfinite(ranges)
        else:
            valid = np.isfinite(ranges)

        finite = np.isfinite(ranges)

        # IR-SIM uses range_max for a valid no-hit beam. A beam marked invalid
        # is commonly a hit inside range_min (for example a wall only 0.04 m
        # from the sensor). The previous adapter replaced every invalid beam
        # with range_max, converting immediate collision danger into 5 m of
        # apparent clearance.
        #
        # Use a conservative near reading for invalid beams. This may reject a
        # questionable turn, but it cannot authorize motion through a wall.
        clean_ranges = np.where(
            valid & finite,
            ranges,
            self.range_min_m,
        )
        clean_ranges = np.clip(
            clean_ranges,
            self.range_min_m,
            self.range_max_m,
        )
        return clean_ranges, angles, valid

    def ray_distance(
        self,
        relative_angle_rad: float,
        *,
        maximum_error_deg: float = 2.0,
    ) -> tuple[float, float, bool, bool]:
        """
        Return obstacle distance along a robot-relative bearing.

        Returns:
            distance_m,
            selected_beam_error_rad,
            bearing_inside_lidar_fov,
            selected_beam_hit_valid
        """
        ranges, angles, valid = self._clean_scan()

        # This LiDAR covers approximately -90 to +90 degrees.
        angle_min = float(np.min(angles))
        angle_max = float(np.max(angles))
        inside_fov = (
            angle_min - 1e-9
            <= relative_angle_rad
            <= angle_max + 1e-9
        )
        if not inside_fov:
            return self.range_max_m, math.inf, False, False

        index, error = self._nearest_index(
            angles,
            relative_angle_rad,
        )
        maximum_error_rad = math.radians(maximum_error_deg)
        if error > maximum_error_rad:
            return self.range_max_m, error, False, False

        return (
            float(ranges[index]),
            error,
            True,
            bool(valid[index]),
        )

    def _direction_value(
        self,
        *,
        clean_ranges: np.ndarray,
        valid: np.ndarray,
        index: int,
    ) -> tuple[float, bool]:
        """
        Return conservative directional clearance.

        An invalid directional beam is reported as range_min rather than
        range_max. The validity flag remains False for diagnostics.
        """
        if not bool(valid[index]):
            return self.range_min_m, False
        return float(clean_ranges[index]), True

    def read(self) -> DirectionalRangeSnapshot:
        clean_ranges, angles, valid = self._clean_scan()

        right_index, right_error = self._nearest_index(
            angles, -math.pi / 2.0
        )
        left_index, left_error = self._nearest_index(
            angles, math.pi / 2.0
        )
        front_left_index, front_left_error = self._nearest_index(
            angles,
            self.front_left_angle_rad,
        )
        front_right_index, front_right_error = self._nearest_index(
            angles,
            self.front_right_angle_rad,
        )

        bad = {
            name: math.degrees(error)
            for name, error in {
                "SIDE_LEFT": left_error,
                "FRONT_LEFT": front_left_error,
                "FRONT_RIGHT": front_right_error,
                "SIDE_RIGHT": right_error,
            }.items()
            if error > self.maximum_direction_error_rad
        }
        if bad:
            raise RuntimeError(
                "LiDAR has no beam close enough to required "
                f"directions: {bad}."
            )

        directional_indices = {
            left_index,
            front_left_index,
            front_right_index,
            right_index,
        }
        if len(directional_indices) != 4:
            raise RuntimeError(
                "Four ToF channels resolved to duplicate LiDAR beams: "
                f"SL={left_index}, FL={front_left_index}, "
                f"FR={front_right_index}, SR={right_index}."
            )

        left_m, left_valid = self._direction_value(
            clean_ranges=clean_ranges,
            valid=valid,
            index=left_index,
        )
        front_left_m, front_left_valid = self._direction_value(
            clean_ranges=clean_ranges,
            valid=valid,
            index=front_left_index,
        )
        front_right_m, front_right_valid = self._direction_value(
            clean_ranges=clean_ranges,
            valid=valid,
            index=front_right_index,
        )
        right_m, right_valid = self._direction_value(
            clean_ranges=clean_ranges,
            valid=valid,
            index=right_index,
        )

        # Conservative front fusion. Both channels must be valid; either one
        # seeing a close wall is sufficient to stop the robot.
        front_m = min(
            front_left_m,
            front_right_m,
        )
        front_valid = (
            front_left_valid
            and front_right_valid
        )

        # Keep a representative front beam for legacy diagnostics.
        if front_left_m <= front_right_m:
            front_index = front_left_index
        else:
            front_index = front_right_index

        self._sequence += 1
        return DirectionalRangeSnapshot(
            sequence=self._sequence,
            sim_time_s=float(self.env.time),
            pose=self._pose(),
            left_m=left_m,
            front_m=front_m,
            right_m=right_m,
            front_left_m=front_left_m,
            front_right_m=front_right_m,
            left_valid=left_valid,
            front_valid=front_valid,
            right_valid=right_valid,
            front_left_valid=front_left_valid,
            front_right_valid=front_right_valid,
            left_beam_index=left_index,
            front_beam_index=front_index,
            right_beam_index=right_index,
            front_left_beam_index=front_left_index,
            front_right_beam_index=front_right_index,
            left_beam_angle_rad=float(angles[left_index]),
            front_beam_angle_rad=float(angles[front_index]),
            right_beam_angle_rad=float(angles[right_index]),
            front_left_beam_angle_rad=float(
                angles[front_left_index]
            ),
            front_right_beam_angle_rad=float(
                angles[front_right_index]
            ),
            beam_count=int(clean_ranges.size),
        )
