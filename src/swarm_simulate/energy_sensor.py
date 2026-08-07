from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Sequence

from motion_types import RobotPose


@dataclass(frozen=True)
class EnergyEndpoint:
    endpoint_id: str
    x_m: float
    y_m: float


@dataclass(frozen=True)
class EnergyReading:
    # Backward-compatible acquisition fields
    detected: bool
    endpoint_id: str | None
    distance_m: float
    signal_strength: float
    relative_bearing_rad: float
    inside_sensor_fov: bool
    beam_hit_valid: bool
    wall_distance_m: float
    line_of_sight_clear: bool
    blocked_by_wall: bool
    within_detection_radius: bool
    acquisition_clearance_m: float

    # New 3-solar-cell light-field values
    solar_left: float
    solar_center: float
    solar_right: float
    solar_max: float
    solar_mean: float
    strongest_direction: str
    guidance_active: bool
    collect_threshold_reached: bool
    approach_active: bool
    light_state: str
    light_path_factor: float


class RandomEndpointEnergySensor:
    """
    Three-channel solar-cell light-field model.

    Sensor layout relative to robot heading:
        LEFT   = +90 degrees
        CENTER =   0 degrees
        RIGHT  = -90 degrees

    This matches the intended physical layout: one solar cell facing the
    left side, one facing forward, and one facing the right side.

    Light intensity:
        distance field
        x solar-cell angular response
        x strict line-of-sight gate

    A wall blocks the source completely in this controlled experiment.
    No diffuse/reflected light is used because that behavior has not been
    measured or calibrated for the physical Solar Cell hardware.

    Collection is a separate near-field event: the robot must physically enter
    the acquisition radius. Solar intensity is not used as the final pickup
    trigger because the source may move behind the directional cells after the
    robot crosses the marker centre.
    """

    SENSOR_ANGLES_RAD = {
        "LEFT": math.radians(90.0),
        "CENTER": 0.0,
        "RIGHT": math.radians(-90.0),
    }

    # The simulated front LiDAR ends at approximately +/-90 degrees.
    # A source only slightly beyond the last beam must not jump abruptly from
    # direct light to blocked/diffuse light because of a sub-degree bearing
    # change. Clamp a small edge band to the side beam.
    LOS_FOV_EDGE_TOLERANCE_RAD = math.radians(5.0)
    ZERO_LIGHT_EPSILON = 1e-9

    def __init__(
        self,
        *,
        endpoints: Sequence[EnergyEndpoint],
        detection_radius_m: float,
        random_seed: int | None,
        line_of_sight_margin_m: float = 0.03,
        visible_marker_radius_m: float = 0.12,
        guidance_threshold: float = 0.001,
        collect_threshold: float = 0.90,
        light_range_scale_m: float = 2.75,
        blocked_light_factor: float = 0.0,
        diffuse_guidance_threshold: float = 0.003,
        maximum_diffuse_guidance_distance_m: float = 7.0,
        angular_exponent: float = 2.0,
        ambient_light: float = 0.0,
    ) -> None:
        if not endpoints:
            raise ValueError("At least one endpoint is required")
        if detection_radius_m <= visible_marker_radius_m:
            raise ValueError(
                "Detection radius must exceed marker radius"
            )
        if not 0.0 <= guidance_threshold < collect_threshold <= 1.0:
            raise ValueError(
                "Require 0 <= guidance_threshold < "
                "collect_threshold <= 1"
            )
        if light_range_scale_m <= 0:
            raise ValueError("light_range_scale_m must be positive")
        if not 0.0 <= blocked_light_factor <= 1.0:
            raise ValueError(
                "blocked_light_factor must be in [0, 1]"
            )
        if angular_exponent <= 0:
            raise ValueError("angular_exponent must be positive")

        self._endpoints = tuple(endpoints)
        self.detection_radius_m = detection_radius_m
        self.line_of_sight_margin_m = line_of_sight_margin_m
        self.visible_marker_radius_m = visible_marker_radius_m
        # In the current Memory-only experiment this is the minimum
        # detectable directional-light level. Once exceeded, guidance is ON.
        # AIH will later decide whether to exploit or ignore experience; it is
        # not allowed to suppress basic light detection in this phase.
        self.guidance_threshold = guidance_threshold
        self.detect_threshold = guidance_threshold
        self.collect_threshold = collect_threshold
        self.light_range_scale_m = light_range_scale_m
        self.blocked_light_factor = blocked_light_factor
        self.diffuse_guidance_threshold = float(
            diffuse_guidance_threshold
        )
        self.maximum_diffuse_guidance_distance_m = float(
            maximum_diffuse_guidance_distance_m
        )
        self.angular_exponent = angular_exponent

        # Kept only for backward-compatible constructor calls.
        # Strict LOS ignores all diffuse-light parameters.
        self.ambient_light = max(0.0, min(1.0, ambient_light))

        self.random_seed = random_seed
        self._rng = random.Random(random_seed)
        self._active = self._endpoints[0]

    @property
    def active_endpoint(self) -> EnergyEndpoint:
        return self._active

    def select_next_endpoint(
        self,
        *,
        avoid_endpoint_id: str | None = None,
    ) -> EnergyEndpoint:
        """
        Select the Energy source for the next foraging trip.

        When more than one endpoint exists, the immediately previous endpoint
        is excluded so two consecutive trips do not appear unchanged merely
        because random choice repeated the same value.
        """
        # The current controlled experiment uses one fixed source. Keep
        # this method for API compatibility; it intentionally returns the
        # same source on every trip.
        return self._active

    @staticmethod
    def _wrap(angle_rad: float) -> float:
        return math.atan2(
            math.sin(angle_rad),
            math.cos(angle_rad),
        )

    def _distance_field(self, distance_m: float) -> float:
        # Smooth inverse-distance field:
        # d=0 -> 1.0, d=scale -> 0.5, then gradually decreases.
        ratio = distance_m / self.light_range_scale_m
        return 1.0 / (1.0 + ratio * ratio)

    def _cell_response(
        self,
        *,
        source_bearing_rad: float,
        sensor_angle_rad: float,
        distance_field: float,
        path_factor: float,
    ) -> float:
        angular_error = abs(
            self._wrap(source_bearing_rad - sensor_angle_rad)
        )

        # Solar cells only receive useful light from their forward hemisphere.
        cosine = max(0.0, math.cos(angular_error))
        directional = cosine ** self.angular_exponent

        value = (
            self.ambient_light
            + distance_field * directional * path_factor
        )
        return max(0.0, min(1.0, value))

    def read(self, pose: RobotPose, range_sensor) -> EnergyReading:
        dx = self._active.x_m - pose.x_m
        dy = self._active.y_m - pose.y_m
        distance = math.hypot(dx, dy)
        relative = self._wrap(
            math.atan2(dy, dx) - pose.theta_rad
        )

        los_query_bearing = relative
        if (
            math.pi / 2.0
            < relative
            <= math.pi / 2.0 + self.LOS_FOV_EDGE_TOLERANCE_RAD
        ):
            los_query_bearing = math.pi / 2.0
        elif (
            -math.pi / 2.0 - self.LOS_FOV_EDGE_TOLERANCE_RAD
            <= relative
            < -math.pi / 2.0
        ):
            los_query_bearing = -math.pi / 2.0

        wall, _, inside_fov, beam_valid = (
            range_sensor.ray_distance(los_query_bearing)
        )

        los_limit = (
            wall
            + self.visible_marker_radius_m
            + self.line_of_sight_margin_m
        )
        clear = inside_fov and los_limit >= distance
        blocked = inside_fov and not clear

        # Strict LOS policy:
        # any confirmed wall between robot and source blocks all Solar Cell
        # channels. The sensor must not reveal source direction through walls.
        path_factor = 1.0 if clear else 0.0
        distance_field = self._distance_field(distance)

        if clear:
            channels = {
                name: self._cell_response(
                    source_bearing_rad=relative,
                    sensor_angle_rad=angle,
                    distance_field=distance_field,
                    path_factor=path_factor,
                )
                for name, angle in self.SENSOR_ANGLES_RAD.items()
            }
        else:
            channels = {
                "LEFT": 0.0,
                "CENTER": 0.0,
                "RIGHT": 0.0,
            }

        solar_left = channels["LEFT"]
        solar_center = channels["CENTER"]
        solar_right = channels["RIGHT"]
        solar_max = max(
            solar_left,
            solar_center,
            solar_right,
        )
        solar_mean = (
            solar_left + solar_center + solar_right
        ) / 3.0
        strongest = (
            "NONE"
            if solar_max <= self.ZERO_LIGHT_EPSILON
            else max(channels, key=channels.get)
        )

        guidance_active = (
            clear
            and solar_max >= self.detect_threshold
        )

        within = distance <= self.detection_radius_m
        acquisition_clearance = (
            self.detection_radius_m - distance
        )

        # Pickup is based on physical near-field proximity, not on directional
        # solar intensity. If the source lies just behind the robot after
        # crossing its centre, the front LiDAR cannot confirm LOS; that must
        # not invalidate an already reached pickup point.
        #
        # A wall blocks pickup only when the source ray is measurable inside
        # the sensor FOV and the wall is confirmed closer than the source.
        confirmed_wall_block = (
            inside_fov
            and beam_valid
            and blocked
        )
        collect_reached = (
            within
            and not confirmed_wall_block
        )

        approach_active = (
            guidance_active
            and not collect_reached
        )

        if collect_reached:
            light_state = "READY_TO_COLLECT"
        elif approach_active:
            light_state = "LIGHT_APPROACH"
        else:
            light_state = "SEARCH"
        detected = collect_reached

        return EnergyReading(
            detected=detected,
            endpoint_id=(
                self._active.endpoint_id if detected else None
            ),
            distance_m=distance,
            signal_strength=solar_max,
            relative_bearing_rad=relative,
            inside_sensor_fov=(
                inside_fov
                and clear
                and solar_max >= self.detect_threshold
            ),
            beam_hit_valid=beam_valid,
            wall_distance_m=wall,
            line_of_sight_clear=clear,
            blocked_by_wall=blocked,
            within_detection_radius=within,
            acquisition_clearance_m=acquisition_clearance,
            solar_left=solar_left,
            solar_center=solar_center,
            solar_right=solar_right,
            solar_max=solar_max,
            solar_mean=solar_mean,
            strongest_direction=strongest,
            guidance_active=guidance_active,
            collect_threshold_reached=collect_reached,
            approach_active=approach_active,
            light_state=light_state,
            light_path_factor=path_factor,
        )
