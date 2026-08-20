"""Experimental-control implementation for Condition 1: Baseline.

Every Scout is an independent, memory-free reactive forager.  The only
persistent controller values are those needed to execute its *current* action
and the fixed nest cue shared by all experimental conditions.  In particular,
this module contains no visited-port history, route/breadcrumb, map, message
bus, or cross-trip preference.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import csv
import json
import math
from pathlib import Path
import random
from typing import Any

import numpy as np
from matplotlib.patches import Circle, FancyArrowPatch

from energy_sensor import RandomEndpointEnergySensor
from irsim_range_sensor import IRSimDirectionalRangeSensor
from motion_types import RobotPose


def _wrap(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


@dataclass
class ScoutState:
    scout_id: int
    rng: random.Random
    phase: str = "EXPLORE"
    # A C1 cycle is one Scout-local EXPLORE → ... → DELIVER lifecycle.  It is
    # deliberately independent of legacy development ``trip_id`` limits.
    cycle_id: int = 1
    completed_cycle_count: int = 0
    trip_id: int = 1
    started_trip_count: int = 1
    turn_remaining_rad: float = 0.0
    turn_reason: str = ""
    # This is actuator state for one current obstacle-escape maneuver only.
    # It is cleared as soon as the current front geometry is traversable and
    # is never used as branch, route, or cross-trip information.
    escape_direction: float = 0.0
    escape_turn_count: int = 0
    distance_m: float = 0.0
    trip_distance_m: float = 0.0
    diagonal_turn_count: int = 0
    obstacle_turn_count: int = 0
    blocked_count: int = 0
    resource_found_count: int = 0
    collection_count: int = 0
    # Current payload only: not route, source-choice, or cross-trip memory.
    carried_harvest_energy: float = 0.0
    harvest_resource_id: str | None = None
    harvest_start_s: float | None = None
    harvest_elapsed_s: float = 0.0
    harvest_episode_count: int = 0
    total_harvested_energy: float = 0.0
    delivered_harvest_energy: float = 0.0
    last_delivered_energy: float = 0.0
    internal_energy: float = 3.0
    minimum_internal_energy: float = 3.0
    depleted: bool = False
    nest_withdrawn_energy: float = 0.0
    delivery_count: int = 0
    return_attempt_count: int = 0
    contact_stall_steps: int = 0
    contact_stalled: bool = False
    # A contact episode is the uninterrupted physical no-progress condition
    # currently being recovered.  It is deliberately separate from the total
    # count reported for a run: a recovery that demonstrably left the contact
    # must not consume the bounded budget of a later, independent contact.
    contact_recovery_episode_count: int = 0
    contact_recovery_count: int = 0
    recovery_stage: str = ""
    recovery_steps_remaining: int = 0
    # Evidence collected over the current bounded contact-recovery maneuver.
    # This is actuator progress only; it is discarded at completion and is
    # never used to identify a place, obstacle, or route.
    recovery_translation_m: float = 0.0
    recovery_rotation_rad: float = 0.0
    recovery_failure_detail: str = ""
    recovery_departure_steps: int = 0
    # Current obstacle-bypass maneuver only. Cleared as soon as a fresh scan
    # says that the nest cue can be pursued through a turn-safe local opening.
    bypass_active: bool = False
    bypass_departure_steps: int = 0
    # Reporting-only physical-motion detector. It never feeds navigation.
    # It is phase/action agnostic: persistent rotation without translation is
    # invalid whether it occurs in Explore or Return.
    stationary_rotation_steps: int = 0
    max_stationary_rotation_steps: int = 0
    persistent_stationary_turn_deadlock: bool = False
    previous_pose: RobotPose | None = None
    trip_start_s: float = 0.0
    collected_at_s: float | None = None
    trip_rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class IdealizedRSSILikeNestBeacon:
    """Environment-owned common Nest beacon.

    The environment retains the physical nest position solely to synthesize a
    deterministic scalar measurement.  The behavioral controller receives
    only the return value of :meth:`sample`, never this object or its x/y.
    Values are unitless and intentionally are not claimed as calibrated dBm.
    """

    nest_x_m: float
    nest_y_m: float
    scale_m: float = 2.0

    def sample(self, pose: RobotPose) -> float:
        distance = math.hypot(pose.x_m - self.nest_x_m, pose.y_m - self.nest_y_m)
        return 1.0 / (1.0 + distance / self.scale_m)


class BaselineSwarmRunner:
    """Run Condition 1 without any learning or inter-Scout communication."""

    def __init__(
        self, *, env, run_dir: Path, energy_sensor: RandomEndpointEnergySensor,
        seed: int, scout_count: int, duration_s: float, trip_count: int,
        render_enabled: bool, mission_mode: str = "trip_limited",
        nest_energy_target: int | None = None, harvest_payload_target: float = 1.0,
        internal_energy_capacity: float = 3.0, initial_internal_energy: float = 3.0,
        energy_cost_per_encoder_distance: float = 0.01,
    ) -> None:
        if scout_count < 2:
            raise ValueError("Baseline swarm requires at least two Scouts")
        if trip_count < 1:
            raise ValueError("Baseline swarm requires at least one trip")
        self.env = env
        self.run_dir = run_dir
        self.energy_sensor = energy_sensor
        self.seed = int(seed)
        self.scout_count = int(scout_count)
        self.duration_s = float(duration_s)
        self.trip_count = int(trip_count)
        self.mission_mode = str(mission_mode)
        self.nest_energy_target = nest_energy_target
        self.harvest_payload_target = float(harvest_payload_target)
        self.internal_energy_capacity = float(internal_energy_capacity)
        self.initial_internal_energy = float(initial_internal_energy)
        self.energy_cost_per_encoder_distance = float(energy_cost_per_encoder_distance)
        self.nest_energy = 0.0
        self.gross_delivered_energy = 0.0
        self.total_nest_withdrawal = 0.0
        if self.harvest_payload_target <= 0.0:
            raise ValueError("harvest_payload_target must be positive")
        if self.mission_mode not in {"research", "trip_limited"}:
            raise ValueError("mission_mode must be 'research' or 'trip_limited'")
        if self.mission_mode == "research" and (
            self.nest_energy_target is None or self.nest_energy_target < 1
        ):
            raise ValueError("Research mission mode requires NEST_ENERGY_TARGET >= 1")
        self.render_enabled = bool(render_enabled)
        self.safe_front_m = 0.72
        # A 0.25 m radius body needs lateral room to rotate at a wall corner.
        # This is distinct from forward stopping distance: it guards a
        # requested 45° body turn from clipping the turn-side obstacle.
        self.turn_side_clearance_m = 0.42
        self.nest_delivery_radius_m = 0.12
        self.turn_angle_rad = math.radians(45.0)
        self.angular_speed_radps = 0.90
        self.linear_speed_mps = 0.22
        # A bypass must leave the current corner geometry before it may be
        # re-arbitrated.  Derive the bound from the already-established
        # body-safe front clearance rather than an ungrounded tick constant.
        self.bypass_departure_step_count = int(math.ceil(
            self.safe_front_m / (self.linear_speed_mps * self.env.step_time)
        ))
        # Two complete 360-degree scans at 45-degree primitives without any
        # translation is a controller pathology, not a slow baseline trial.
        self.return_stationary_turn_limit = 2 * 8 * int(math.ceil(
            self.turn_angle_rad / (self.angular_speed_radps * self.env.step_time)
        ))
        # One complete local 360-degree scan may be a valid current-clearance
        # maneuver. A second scan without any departure must yield/back off;
        # otherwise two nearby bodies can keep each other in clearance limbo.
        self.escape_turn_limit = 8
        # Display-only marker for visual replay.  It has no IR-SIM body and
        # never participates in collision, sensing, or controller state.
        self._display_energy_markers: list[Circle] = []
        # IR-SIM's stock velocity glyph is 0.40 m long regardless of robot
        # size.  Use a display-only, physical-scale heading marker instead.
        self._display_heading_arrows: list[FancyArrowPatch] = []
        self._add_scouts()
        self.sensors = [
            IRSimDirectionalRangeSensor(env=env, range_max_m=5.0, robot_id=i)
            for i in range(self.scout_count)
        ]
        # This is environment-only geometry.  It is used to synthesize a
        # common scalar RSSI-like signal and to score physical Nest arrival;
        # no Scout/controller receives the position, bearing, or distance.
        nest_pose = self._pose(env, 0)
        self._nest_beacon = IdealizedRSSILikeNestBeacon(
            nest_x_m=nest_pose.x_m, nest_y_m=nest_pose.y_m,
        )
        self.scouts = [
            ScoutState(
                scout_id=i,
                rng=random.Random(self.seed + 104729 * i),
                internal_energy=self.initial_internal_energy,
                minimum_internal_energy=self.initial_internal_energy,
            )
            for i in range(self.scout_count)
        ]

    def _add_scouts(self) -> None:
        # These are separated start locations within the common nest-side
        # corridor.  Each Scout receives the same stateless nest-cue mechanism
        # that the pre-existing single-robot baseline uses.
        starts = [
            [1.00, 1.00, 0.0], [1.80, 1.00, 0.0], [2.60, 1.00, 0.0],
            [3.35, 1.00, 0.0],
        ]
        if self.scout_count > len(starts):
            raise ValueError("Baseline swarm currently supports at most 4 Scouts")
        self.env.robot_list[0]._state = np.asarray(starts[0], dtype=float).reshape(3, 1)
        extras = []
        for scout_id, state in enumerate(starts[1:self.scout_count], start=1):
            extras.append(self.env.create_robot(
                name=f"Scout-{scout_id}", kinematics={"name": "diff"},
                shape={"name": "circle", "radius": 0.25}, state=state,
                vel_max=[0.80, 1.00], color=["b", "m", "c"][scout_id - 1],
                sensors=[{"name": "lidar2d", "range_min": 0.05, "range_max": 5.0,
                          "angle_range": math.pi, "number": 181, "noise": False,
                          "alpha": 0.10}],
                # Hide IR-SIM's fixed-size (0.4 m) velocity glyph.  It is
                # visually larger than the 0.10 m physical-scale robot.
                plot={"show_trail": False, "show_sensor": False, "show_goal": False,
                      "show_arrow": False},
            ))
        if extras:
            self.env.add_objects(extras)

    def _draw_energy_marker(self) -> None:
        """Keep every persistent C1 source visible in rendered replays."""
        if not self.render_enabled:
            return
        import matplotlib.pyplot as plt

        figure = plt.gcf()
        if not figure.axes:
            return
        axes = figure.axes[0]
        palette = [("yellow", "goldenrod"), ("orange", "saddlebrown"), ("gold", "darkorange")]
        while len(self._display_energy_markers) < len(self.energy_sensor.endpoints):
            index = len(self._display_energy_markers)
            endpoint = self.energy_sensor.endpoints[index]
            facecolor, edgecolor = palette[index % len(palette)]
            self._display_energy_markers.append(Circle(
                (endpoint.x_m, endpoint.y_m), self.energy_sensor.visible_marker_radius_m,
                facecolor=facecolor, edgecolor=edgecolor, linewidth=1.5, zorder=100,
            ))
        for marker in self._display_energy_markers:
            if marker not in axes.patches:
                axes.add_patch(marker)

    def _draw_scout_heading_markers(self) -> None:
        """Draw one display-only, maze-scale heading arrow per Scout."""
        if not self.render_enabled:
            return
        import matplotlib.pyplot as plt

        figure = plt.gcf()
        if not figure.axes:
            return
        axes = figure.axes[0]
        marker_length_m = 0.30
        while len(self._display_heading_arrows) < self.scout_count:
            arrow = FancyArrowPatch(
                (0.0, 0.0), (0.0, 0.0),
                arrowstyle="-|>", mutation_scale=9,
                linewidth=1.2, color="gold", zorder=110,
            )
            self._display_heading_arrows.append(arrow)
            axes.add_patch(arrow)
        for scout_id, arrow in enumerate(self._display_heading_arrows):
            pose = self._pose(self.env, scout_id)
            # Red is a visual-only carrying indicator.  It reads the current
            # physical carry state; it is not fed back into any controller
            # decision, memory, or inter-Scout communication.
            carrying_energy = (
                self.scouts[scout_id].carried_harvest_energy > 0.0
                and self.scouts[scout_id].phase == "RETURN_HOME"
            )
            arrow.set_color("red" if carrying_energy else "gold")
            arrow.set_positions(
                (pose.x_m, pose.y_m),
                (
                    pose.x_m + marker_length_m * math.cos(pose.theta_rad),
                    pose.y_m + marker_length_m * math.sin(pose.theta_rad),
                ),
            )

    @staticmethod
    def _pose(env, scout_id: int) -> RobotPose:
        value = np.asarray(env.robot_list[scout_id]._state, dtype=float).reshape(-1)
        return RobotPose(float(value[0]), float(value[1]), float(value[2]))

    def _start_turn(self, scout: ScoutState, direction: float, reason: str) -> None:
        scout.turn_remaining_rad = direction * self.turn_angle_rad
        scout.turn_reason = reason
        scout.diagonal_turn_count += 1
        if reason == "OBSTACLE_ESCAPE_TURN_45":
            scout.obstacle_turn_count += 1

    def _continue_turn(self, scout: ScoutState) -> tuple[float, float, str]:
        sign = 1.0 if scout.turn_remaining_rad > 0.0 else -1.0
        delta = min(abs(scout.turn_remaining_rad), self.angular_speed_radps * self.env.step_time)
        scout.turn_remaining_rad -= sign * delta
        if abs(scout.turn_remaining_rad) < 1e-9:
            scout.turn_remaining_rad = 0.0
        # Scale the final control period instead of applying a full angular
        # velocity after the requested 45 degrees has almost completed.
        # This makes every completed local turn 45° rather than ~46.4°.
        return 0.0, sign * delta / self.env.step_time, scout.turn_reason

    def _record_physical_stationary_rotation(
        self, scout: ScoutState, *, moved_m: float, turned: bool,
        angular_velocity_radps: float,
    ) -> None:
        """Classify sustained physical rotation without departure.

        This is reporting-only safety validation.  It deliberately uses no
        phase or action label, so a renamed controller action cannot hide a
        persistent Explore or Return deadlock.
        """
        if abs(angular_velocity_radps) > 1e-9 and turned and moved_m < 1e-7:
            scout.stationary_rotation_steps += 1
            scout.max_stationary_rotation_steps = max(
                scout.max_stationary_rotation_steps, scout.stationary_rotation_steps
            )
            if scout.stationary_rotation_steps >= self.return_stationary_turn_limit:
                scout.persistent_stationary_turn_deadlock = True
        else:
            scout.stationary_rotation_steps = 0

    def _clear_escape(self, scout: ScoutState) -> None:
        scout.escape_direction = 0.0
        scout.escape_turn_count = 0

    def _obstacle_escape_command(self, scout: ScoutState, snapshot) -> tuple[float, float, str]:
        """Complete one local turn-side maneuver using only live geometry.

        Re-evaluating the larger side after every 45° was shown by the run log
        to select the opposite side at two adjacent headings, producing an
        in-place two-heading oscillation.  Once a side is chosen from the
        *current* scan, retain it only until a forward-safe heading is found.
        This is equivalent to completing a single motor maneuver, not storing
        a visited route or a preference.
        """
        if scout.turn_remaining_rad:
            return self._continue_turn(scout)

        # A front-clear beam alone is insufficient near a wall endpoint: the
        # circular body can side-swipe the corner on the next forward tick.
        # Use the same current side-clearance rule as normal exploration
        # before an obstacle-escape maneuver may commit to translation.
        if (
            snapshot.front_m > self.safe_front_m
            and min(snapshot.left_m, snapshot.right_m)
            >= self.turn_side_clearance_m
        ):
            self._clear_escape(scout)
            return self.linear_speed_mps, 0.0, "OBSTACLE_ESCAPE_FORWARD"
        if scout.escape_direction == 0.0:
            scout.escape_direction = 1.0 if snapshot.left_m >= snapshot.right_m else -1.0
        scout.escape_turn_count += 1
        if scout.escape_turn_count > self.escape_turn_limit:
            # A full local scan did not expose a traversable segment. Yield
            # with a bounded reverse maneuver, then take a fresh local scan.
            # This retains only the current safety episode; no peer, location,
            # obstacle, branch, or route is recorded.
            scout.escape_direction = 0.0
            scout.escape_turn_count = 0
            scout.recovery_stage = "BACK_OFF"
            scout.recovery_steps_remaining = self.bypass_departure_step_count
            scout.recovery_translation_m = 0.0
            scout.recovery_rotation_rad = 0.0
            return -self.linear_speed_mps, 0.0, "CLEARANCE_YIELD_BACK_OFF"
        self._start_turn(scout, scout.escape_direction, "OBSTACLE_ESCAPE_TURN_45")
        return self._continue_turn(scout)

    def _begin_clear_side_turn(self, scout: ScoutState, snapshot, reason: str) -> tuple[float, float, str]:
        direction = 1.0 if snapshot.left_m >= snapshot.right_m else -1.0
        scout.escape_direction = direction
        scout.escape_turn_count += 1
        self._start_turn(scout, direction, reason)
        return self._continue_turn(scout)

            # ``front_m`` is deliberately the minimum of the ±20 degree
            # body-leading beams.  A clear centre ray alone can pass a corner
            # that the 0.25 m circular body will clip, so it must never
            # authorize a straight recovery/bypass departure by itself.
    def _contact_recovery_command(self, scout: ScoutState, snapshot) -> tuple[float, float, str]:
        """Bounded stateless recovery after simulator contact/no-progress.

        This is a current actuator maneuver: back off briefly, then choose a
        turn from the newly sampled local clearances.  It contains no record
        of the obstacle, previous route, or previous decision once complete.
        """
        # IR-SIM's ``collision_mode: stop`` retains the contact report and
        # stop latch from the preceding overlap.  Clear both only while this
        # bounded safety maneuver is being evaluated.  The next physics step
        # still recomputes collision for the commanded pose and immediately
        # reasserts either flag if the body remains in contact, so this never
        # authorizes passage through a wall.
        robot = self.env.robot_list[scout.scout_id]
        robot.stop_flag = False
        robot.collision_flag = False
        if scout.recovery_stage == "BACK_OFF":
            scout.recovery_steps_remaining -= 1
            if scout.recovery_steps_remaining <= 0:
                scout.recovery_stage = "REORIENT"
            return -self.linear_speed_mps, 0.0, "CONTACT_RECOVERY_BACK_OFF"
        if scout.recovery_stage == "REORIENT":
            direction = 1.0 if snapshot.left_m >= snapshot.right_m else -1.0
            scout.escape_direction = direction
            self._start_turn(scout, direction, "CONTACT_RECOVERY_TURN_45")
            scout.recovery_stage = "TURNING"
            return self._continue_turn(scout)
        if scout.recovery_stage == "TURNING":
            if scout.turn_remaining_rad:
                return self._continue_turn(scout)
            # Completion is assessed after the command has passed through
            # physics in ``run``.  It must not mean merely that the intended
            # tick sequence has elapsed.
            scout.recovery_stage = "VERIFY"
        if scout.recovery_stage == "VERIFY":
            return 0.0, 0.0, "CONTACT_RECOVERY_VERIFY"
        return 0.0, 0.0, "CONTACT_RECOVERY_VERIFY"

    def _recovery_physically_succeeded(self, scout: ScoutState) -> bool:
        """Require measured recovery motion and a collision-free current body."""
        robot = self.env.robot_list[scout.scout_id]
        return (
            scout.recovery_translation_m >= 0.003
            and scout.recovery_rotation_rad >= math.radians(10.0)
            and not bool(robot.collision)
            and not bool(robot.stop_flag)
        )

    def _forward_body_clearance_safe(self, snapshot, sensor) -> bool:
        """Require local clearance for the circular body, not only its nose.

        The three cardinal ToF beams can miss the endpoint of a wall while a
        circular robot clips that corner on the next forward tick.  Two fresh
        +/-45 degree rays close that body-clearance gap.  This is a current
        sensor gate only: it retains neither an obstacle location nor a past
        choice.
        """
        if snapshot.front_m <= self.safe_front_m:
            return False
        corner_clearance = self.turn_side_clearance_m + (
            self.linear_speed_mps * self.env.step_time
        )
        for offset in (-math.pi / 4.0, math.pi / 4.0):
            ray, _, inside, valid = sensor.ray_distance(offset)
            if inside and valid and ray <= corner_clearance:
                return False
        return True

    def _explore_command(self, scout: ScoutState, snapshot, reading, sensor) -> tuple[float, float, str]:
        if scout.recovery_stage:
            return self._contact_recovery_command(scout, snapshot)
        if scout.recovery_departure_steps:
            if snapshot.front_m > self.safe_front_m:
                scout.recovery_departure_steps -= 1
                return self.linear_speed_mps, 0.0, "CONTACT_RECOVERY_DEPART_FORWARD"
            scout.recovery_departure_steps = 0
        if scout.turn_remaining_rad and scout.escape_direction == 0.0:
            return self._continue_turn(scout)
        if reading.detected:
            scout.resource_found_count += 1
            scout.phase = "HARVEST"
            scout.harvest_resource_id = reading.endpoint_id
            scout.harvest_start_s = float(self.env.time)
            scout.harvest_elapsed_s = 0.0
            scout.harvest_episode_count += 1
            return 0.0, 0.0, "RESOURCE_LIGHT_DETECTED"
        # An obstacle escape is one bounded actuator maneuver. It takes
        # priority over light/random exploration until a fresh scan confirms
        # a safe forward direction, then its state is immediately discarded.
        if scout.escape_direction != 0.0:
            return self._obstacle_escape_command(scout, snapshot)
        if reading.guidance_active and reading.strongest_direction != "CENTER":
            direction = 1.0 if reading.strongest_direction == "LEFT" else -1.0
            self._start_turn(scout, direction, "SOLAR_TURN_45")
            return self._continue_turn(scout)
        # The front pair alone cannot prevent two circular Scouts from
        # side-swiping while their headings cross.  The same live side
        # clearance already required for a safe 45-degree body turn is also
        # a local collision guard during Explore.  No Scout identity, route,
        # or previous encounter is retained.
        if min(snapshot.left_m, snapshot.right_m) < self.turn_side_clearance_m:
            scout.blocked_count += 1
            return self._begin_clear_side_turn(
                scout, snapshot, "OBSTACLE_ESCAPE_TURN_45"
            )
        if snapshot.front_m <= self.safe_front_m:
            scout.blocked_count += 1
            return self._obstacle_escape_command(scout, snapshot)
        if scout.rng.random() < 0.012:
            direction = 1.0 if scout.rng.random() < 0.5 else -1.0
            self._start_turn(scout, direction, "EXPLORE_TURN_45")
            return self._continue_turn(scout)
        if not self._forward_body_clearance_safe(snapshot, sensor):
            scout.blocked_count += 1
            return self._begin_clear_side_turn(
                scout, snapshot, "OBSTACLE_ESCAPE_TURN_45"
            )
        return self.linear_speed_mps, 0.0, "EXPLORE_FORWARD"

    def _retired_return_policy(self, scout: ScoutState, snapshot, sensor) -> tuple[float, float, str] | None:
        """Existing baseline's stateless home-vector policy, quantized to 45°.

        The fixed home pose is a common navigation infrastructure cue, not a
        remembered outbound route.  No previous branch, route, or trip result
        is consulted here.
        """
        # The exact-bearing implementation is deliberately unreachable in C1.
        return None
            # An outside-FOV home bearing is not an obstacle observation.  A
            # prior implementation treated it as one, entering bypass even in
            # open space and forcing a long departure away from the Nest.
            # Rotate one body-safe 45-degree primitive to bring the cue into
            # the forward sensor field; only an *observed*, unsafe home ray
            # may invoke obstacle bypass.
    def _return_command(self, scout: ScoutState, snapshot, sensor) -> tuple[float, float, str]:
        """Stateless local return movement; RSSI never steers this policy."""
        if scout.recovery_stage:
            return self._contact_recovery_command(scout, snapshot)
        if scout.escape_direction != 0.0:
            return self._obstacle_escape_command(scout, snapshot)
        if scout.turn_remaining_rad:
            return self._continue_turn(scout)
        if snapshot.front_m <= self.safe_front_m:
            scout.blocked_count += 1
            return self._obstacle_escape_command(scout, snapshot)
        if min(snapshot.left_m, snapshot.right_m) < self.turn_side_clearance_m:
            return self._begin_clear_side_turn(
                scout, snapshot, "RETURN_LOCAL_SIDE_CLEARANCE_ESCAPE_45"
            )
        if scout.rng.random() < 0.012:
            direction = 1.0 if scout.rng.random() < 0.5 else -1.0
            self._start_turn(scout, direction, "RETURN_LOCAL_TURN_45")
            return self._continue_turn(scout)
        if not self._forward_body_clearance_safe(snapshot, sensor):
            scout.blocked_count += 1
            return self._begin_clear_side_turn(scout, snapshot, "RETURN_LOCAL_ESCAPE_45")
        return self.linear_speed_mps, 0.0, "RETURN_LOCAL_FORWARD"

    def _environment_nest_reached(self, pose: RobotPose) -> bool:
        """Environment-only physical Nest entry plus RSSI confirmation."""
        physical_entry = math.hypot(
            pose.x_m - self._nest_beacon.nest_x_m,
            pose.y_m - self._nest_beacon.nest_y_m,
        ) <= self.nest_delivery_radius_m
        # The scalar is confirmation-only and is never supplied to movement.
        return physical_entry and self._nest_beacon.sample(pose) >= 0.85

    def _command_for(
        self, scout: ScoutState, sensor: IRSimDirectionalRangeSensor,
    ) -> tuple[float, float, str, Any, Any]:
        snapshot = sensor.read()
        reading = self.energy_sensor.read(snapshot.pose, sensor)
        if scout.phase == "EXPLORE":
            linear, angular, action = self._explore_command(scout, snapshot, reading, sensor)
        elif scout.phase == "HARVEST":
            # The endpoint identity is environment/logger data only. The
            # controller neither ranks nor navigates by rate or position.
            endpoint = next((item for item in self.energy_sensor.endpoints
                             if item.endpoint_id == scout.harvest_resource_id), None)
            if endpoint is None or not reading.detected or reading.endpoint_id != endpoint.endpoint_id:
                linear, angular, action = 0.0, 0.0, "HARVEST_PAUSED"
            else:
                increment = endpoint.relative_harvest_rate * self.env.step_time
                scout.carried_harvest_energy = min(
                    self.harvest_payload_target, scout.carried_harvest_energy + increment
                )
                scout.total_harvested_energy += increment
                scout.harvest_elapsed_s += self.env.step_time
                if scout.carried_harvest_energy >= self.harvest_payload_target - 1e-12:
                    scout.collection_count += 1
                    scout.return_attempt_count += 1
                    scout.collected_at_s = float(self.env.time)
                    scout.phase = "RETURN_HOME"
                    linear, angular, action = 0.0, 0.0, "HARVEST_COMPLETE"
                else:
                    linear, angular, action = 0.0, 0.0, "HARVEST_ACTIVE"
        elif scout.phase == "RETURN_HOME":
            if self._environment_nest_reached(snapshot.pose):
                scout.phase = "DELIVER"
                linear, angular, action = 0.0, 0.0, "NEST_REACHED"
            else:
                linear, angular, action = self._return_command(scout, snapshot, sensor)
        elif scout.phase == "DELIVER":
            scout.delivery_count += 1
            scout.completed_cycle_count += 1
            scout.trip_rows.append({
                "trip_id": scout.trip_id, "cycle_id": scout.cycle_id, "outcome": "SUCCESS", "collection_s": scout.collected_at_s,
                "delivery_s": float(self.env.time), "trip_distance_m": scout.trip_distance_m,
            })
            scout.trip_distance_m = 0.0
            scout.collected_at_s = None
            scout.last_delivered_energy = scout.carried_harvest_energy
            scout.delivered_harvest_energy += scout.last_delivered_energy
            scout.carried_harvest_energy = 0.0
            scout.harvest_resource_id = None
            scout.harvest_start_s = None
            scout.phase = (
                "COMPLETE"
                if self.mission_mode == "trip_limited" and scout.trip_id >= self.trip_count
                else "EXPLORE"
            )
            scout.trip_id += 1
            if scout.phase == "EXPLORE":
                scout.started_trip_count += 1
                scout.cycle_id += 1
            linear, angular, action = 0.0, 0.0, "DELIVER"
        else:
            linear, angular, action = 0.0, 0.0, "MISSION_COMPLETE"
        # Reuse this exact current sensor frame for passive trajectory
        # logging.  The previous second read occurred at the same simulated
        # instant and did not affect control; removing it reduces wall-clock
        # overhead without skipping any controller/sensor timestep.
        return linear, angular, action, reading, snapshot

    @staticmethod
    def _behavioral_outcome(scout: ScoutState) -> str:
        if scout.phase == "RETURN_HOME":
            return "TIME_LIMIT_REACHED"
        if scout.delivery_count:
            return "SUCCESS" if scout.phase == "COMPLETE" else "TIME_LIMIT_REACHED"
        if scout.return_attempt_count:
            return "RETURN_FAILED"
        if scout.resource_found_count:
            return "NO_SUCCESSFUL_DELIVERY"
        return "RESOURCE_NOT_FOUND"

    def _depleted_scout_can_be_restored(self, scout: ScoutState) -> bool:
        """Whether the currently physical C1 Nest mechanism can revive Scout.

        This is a termination predicate, not a controller/navigation input.
        A zero-energy body at the Nest is not stranded while common Nest
        Energy can still perform the fixed maintenance recharge.
        """
        return (
            scout.phase == "DEPLETED"
            and self.nest_energy > 1e-12
            and self._environment_nest_reached(self._pose(self.env, scout.scout_id))
        )

    def _nest_target_reached(self) -> bool:
        """Numerically stable research-target comparison."""
        return self.nest_energy + 1e-12 >= float(self.nest_energy_target)

    def _colony_failure_all_depleted(self) -> bool:
        """True only when no Scout has any valid future energy-changing action."""
        for scout in self.scouts:
            if scout.phase not in {"DEPLETED", "COMPLETE"}:
                # An active Scout can still explore, return with payload, or
                # deliver; another Scout at zero energy does not end Colony.
                return False
            if self._depleted_scout_can_be_restored(scout):
                return False
        return True

    def _termination_state_snapshot(
        self,
        last_meaningful_event_time_s: float,
        last_active_scout_id: int | None,
    ) -> dict[str, Any]:
        return {
            "nest_energy": self.nest_energy,
            "last_meaningful_event_time_s": last_meaningful_event_time_s,
            "last_active_scout_id": last_active_scout_id,
            "scouts": [{
                "scout_id": scout.scout_id, "phase": scout.phase,
                "internal_energy": scout.internal_energy,
                "carried_payload": scout.carried_harvest_energy,
                "last_active": scout.phase not in {"DEPLETED", "COMPLETE"},
            } for scout in self.scouts],
        }

    def run(self) -> dict[str, Any]:
        trajectory = (self.run_dir / "swarm_trajectory.csv").open("w", newline="", encoding="utf-8")
        event_file = (self.run_dir / "swarm_events.csv").open("w", newline="", encoding="utf-8")
        trip_file = (self.run_dir / "swarm_trip_summary.csv").open("w", newline="", encoding="utf-8")
        energy_timeline_file = (self.run_dir / "nest_energy_timeline.csv").open(
            "w", newline="", encoding="utf-8"
        )
        robot_energy_file = (self.run_dir / "robot_energy_timeline.csv").open("w", newline="", encoding="utf-8")
        trajectory_writer = csv.DictWriter(trajectory, fieldnames=[
            "sim_time_s", "scout_id", "trip_id", "cycle_id", "phase", "x_m", "y_m", "heading_deg", "action",
            "linear_velocity_mps", "angular_velocity_radps", "front_m", "left_m", "right_m", "solar_max",
            "cumulative_distance_m", "trip_distance_m", "diagonal_turn_count",
        ])
        event_writer = csv.DictWriter(event_file, fieldnames=["sim_time_s", "scout_id", "trip_id", "event", "detail"])
        trip_writer = csv.DictWriter(trip_file, fieldnames=["scout_id", "trip_id", "cycle_id", "outcome", "collection_s", "delivery_s", "trip_distance_m"])
        energy_timeline_writer = csv.DictWriter(
            energy_timeline_file,
            fieldnames=[
                "run_id", "seed", "timestamp", "scout_id", "event_type",
                "previous_energy", "delivered_energy", "withdrawal_energy",
                "new_energy", "gross_delivered_energy", "target",
            ],
        )
        robot_energy_writer = csv.DictWriter(robot_energy_file, fieldnames=["sim_time_s", "scout_id", "internal_energy", "phase"])
        trajectory_writer.writeheader(); event_writer.writeheader(); trip_writer.writeheader(); energy_timeline_writer.writeheader(); robot_energy_writer.writeheader()
        coverage: dict[int, set[tuple[int, int]]] = {i: set() for i in range(self.scout_count)}
        for scout in self.scouts:
            scout.previous_pose = self._pose(self.env, scout.scout_id)
            scout.trip_start_s = 0.0
            event_writer.writerow({"sim_time_s": 0.0, "scout_id": scout.scout_id, "trip_id": 1,
                                   "event": "SCOUT_START", "detail": "independent local-reactive baseline"})
            robot_energy_writer.writerow({"sim_time_s": 0.0, "scout_id": scout.scout_id,
                                         "internal_energy": scout.internal_energy, "phase": scout.phase})

        maximum_steps = int(math.ceil(self.duration_s / self.env.step_time))
        mission_complete = False
        target_reached_time_s: float | None = None
        termination_time_s: float | None = None
        last_meaningful_event_time_s = 0.0
        last_active_scout_id: int | None = None
        termination_reason = "TIME_LIMIT_REACHED"
        for step in range(maximum_steps):
            # The completed colony target is absorbing and has priority over
            # recovery/depletion handling in the same state.
            if self.mission_mode == "research" and self._nest_target_reached():
                mission_complete = True
                target_reached_time_s = round(float(self.env.time), 6)
                termination_time_s = target_reached_time_s
                termination_reason = "NEST_ENERGY_TARGET_REACHED"
                event_writer.writerow({"sim_time_s": target_reached_time_s, "scout_id": "COLONY",
                                       "trip_id": "", "event": "MISSION_COMPLETE",
                                       "detail": f"nest_energy={self.nest_energy:.6f}; target={self.nest_energy_target}; termination_reason=NEST_ENERGY_TARGET_REACHED"})
                break
            for scout in self.scouts:
                if (
                    scout.internal_energy <= 1e-12
                    and scout.phase not in {"COMPLETE", "CONTACT_STALLED", "DEPLETED", "DELIVER"}
                    and not (
                        scout.phase == "RETURN_HOME"
                        and scout.carried_harvest_energy > 0.0
                        and self._environment_nest_reached(self._pose(self.env, scout.scout_id))
                    )
                ):
                    scout.depleted = True
                    scout.phase = "DEPLETED"
            # A depleted Scout exactly inside the physical Nest region may be
            # restored by the fixed common recharge mechanism.  This is not a
            # strategic decision and prevents a false ALL_DEPLETED outcome.
            for scout in self.scouts:
                if not self._depleted_scout_can_be_restored(scout):
                    continue
                withdrawal = min(
                    self.internal_energy_capacity - scout.internal_energy,
                    self.nest_energy,
                )
                if withdrawal <= 0.0:
                    continue
                before = self.nest_energy
                self.nest_energy -= withdrawal
                self.total_nest_withdrawal += withdrawal
                scout.internal_energy += withdrawal
                scout.nest_withdrawn_energy += withdrawal
                scout.depleted = False
                scout.phase = "EXPLORE"
                now = round(float(self.env.time), 6)
                event_writer.writerow({"sim_time_s": now, "scout_id": scout.scout_id,
                                       "trip_id": scout.trip_id, "event": "NEST_ENERGY_WITHDRAWAL",
                                       "detail": f"withdrawal={withdrawal:.6f}; net_nest_energy={self.nest_energy:.6f}; robot_energy={scout.internal_energy:.6f}; restored_from_depleted=true"})
                energy_timeline_writer.writerow({
                    "run_id": self.run_dir.name, "seed": self.seed, "timestamp": now,
                    "scout_id": scout.scout_id, "event_type": "ROBOT_RECHARGE_WITHDRAWAL",
                    "previous_energy": before, "delivered_energy": 0.0,
                    "withdrawal_energy": withdrawal, "new_energy": self.nest_energy,
                    "gross_delivered_energy": self.gross_delivered_energy,
                    "target": self.nest_energy_target,
                })
                last_meaningful_event_time_s = now
            commands, rows = [], []
            for scout, sensor in zip(self.scouts, self.sensors, strict=True):
                linear, angular, action, reading, snapshot = self._command_for(scout, sensor)
                commands.append([linear, angular])
                rows.append((
                    scout, snapshot, reading, action, linear, angular,
                    scout.recovery_stage,
                ))
                if scout.phase not in {"DEPLETED", "COMPLETE"}:
                    last_active_scout_id = scout.scout_id
            action_ids = [self.env.objects.index(self.env.robot_list[i]) for i in range(self.scout_count)]
            self.env.step(commands, action_id=action_ids)
            for scout, snapshot, reading, action, linear, angular, recovery_stage in rows:
                contact_stall_started = False
                pose = self._pose(self.env, scout.scout_id)
                moved = math.hypot(pose.x_m - scout.previous_pose.x_m, pose.y_m - scout.previous_pose.y_m)
                turned = abs(_wrap(pose.theta_rad - scout.previous_pose.theta_rad)) > 1e-7
                # Wheel-path proxy from the executed differential command:
                # linear path plus in-place wheel travel. This is common
                # energy physics and never feeds a strategic C1 decision.
                wheel_path_delta = moved + 0.07 * abs(_wrap(pose.theta_rad - scout.previous_pose.theta_rad))
                scout.internal_energy = max(0.0, scout.internal_energy - self.energy_cost_per_encoder_distance * wheel_path_delta)
                scout.minimum_internal_energy = min(scout.minimum_internal_energy, scout.internal_energy)
                robot_depleted_started = False
                if scout.internal_energy <= 1e-12 and scout.phase not in {"COMPLETE", "CONTACT_STALLED", "DEPLETED", "DELIVER"}:
                    scout.depleted = True
                    scout.phase = "DEPLETED"
                    robot_depleted_started = True
                commanded_motion = abs(linear) > 1e-9 or abs(angular) > 1e-9
                if recovery_stage:
                    scout.recovery_translation_m += moved
                    scout.recovery_rotation_rad += abs(
                        _wrap(pose.theta_rad - scout.previous_pose.theta_rad)
                    )
                if action == "CONTACT_RECOVERY_VERIFY":
                    if self._recovery_physically_succeeded(scout):
                        scout.recovery_stage = ""
                        scout.contact_stall_steps = 0
                        scout.recovery_departure_steps = self.bypass_departure_step_count
                        # The recovery back-off itself has travelled the
                        # body-safe clearance.  It has therefore left the
                        # original contact geometry; a later physical contact
                        # is a genuinely new bounded safety episode.
                        if scout.recovery_translation_m >= self.safe_front_m:
                            scout.contact_recovery_episode_count = 0
                        action = "CONTACT_RECOVERY_COMPLETE"
                    elif scout.contact_recovery_episode_count < 2:
                        # The first bounded maneuver made real motion but a
                        # current collision remains (for example at a wall
                        # corner while another physical Scout is nearby).
                        # This is not yet a stalled actuator.  Take exactly
                        # one further fresh-sensor recovery maneuver before
                        # classifying the run as an engineering failure.
                        # The counter is current contact-actuator state only;
                        # it is cleared after a proven departure and never
                        # records a place, peer identity, or route.
                        scout.contact_recovery_episode_count += 1
                        scout.contact_recovery_count += 1
                        scout.recovery_stage = "BACK_OFF"
                        scout.recovery_steps_remaining = self.bypass_departure_step_count
                        scout.recovery_translation_m = 0.0
                        scout.recovery_rotation_rad = 0.0
                        action = "CONTACT_RECOVERY_RETRY"
                    else:
                        # This recovery episode itself failed to move the body
                        # or rotate it out of contact.  That is a genuine
                        # controller/physics failure, unlike a later and
                        # separate contact after a proven departure.
                        scout.recovery_stage = ""
                        robot = self.env.robot_list[scout.scout_id]
                        scout.recovery_failure_detail = (
                            "translation_m="
                            f"{scout.recovery_translation_m:.6f}; "
                            "rotation_rad="
                            f"{scout.recovery_rotation_rad:.6f}; "
                            f"collision={bool(robot.collision)}; "
                            f"stop_flag={bool(robot.stop_flag)}"
                        )
                        scout.contact_stalled = True
                        scout.phase = "CONTACT_STALLED"
                        contact_stall_started = True
                self._record_physical_stationary_rotation(
                    scout, moved_m=moved, turned=turned,
                    angular_velocity_radps=angular,
                )
                if (
                    commanded_motion and moved < 1e-7 and not turned
                    and not scout.recovery_stage
                ):
                    scout.contact_stall_steps += 1
                else:
                    scout.contact_stall_steps = 0
                if (
                    scout.contact_stall_steps >= 3
                    and scout.phase not in {"COMPLETE", "CONTACT_STALLED"}
                ):
                    if scout.contact_recovery_episode_count < 2:
                        scout.contact_recovery_episode_count += 1
                        scout.contact_recovery_count += 1
                        scout.contact_stall_steps = 0
                        scout.recovery_stage = "BACK_OFF"
                        # Retreat by the already defined body-safe clearance
                        # before reorienting.  Eight 0.1 s ticks (0.176 m)
                        # could leave the circular body inside the same corner
                        # even when all three directional beams looked clear.
                        scout.recovery_steps_remaining = self.bypass_departure_step_count
                        scout.recovery_translation_m = 0.0
                        scout.recovery_rotation_rad = 0.0
                        action = "CONTACT_RECOVERY_START"
                    else:
                        scout.contact_stalled = True
                        scout.phase = "CONTACT_STALLED"
                        contact_stall_started = True
                scout.distance_m += moved
                scout.trip_distance_m += moved
                scout.previous_pose = pose
                # Passive research metric only.  Restore the historical
                # maze-scale 0.50 m reporting bin; this never feeds control.
                coverage[scout.scout_id].add((math.floor(pose.x_m / 0.5), math.floor(pose.y_m / 0.5)))
                trajectory_writer.writerow({
                    "sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                    "trip_id": (scout.trip_id if self.mission_mode == "research" else min(scout.trip_id, self.trip_count)),
                    "cycle_id": scout.cycle_id, "phase": scout.phase,
                    "x_m": pose.x_m, "y_m": pose.y_m, "heading_deg": math.degrees(pose.theta_rad),
                    "action": action, "linear_velocity_mps": linear, "angular_velocity_radps": angular,
                    "front_m": snapshot.front_m, "left_m": snapshot.left_m, "right_m": snapshot.right_m,
                    "solar_max": reading.solar_max, "cumulative_distance_m": scout.distance_m,
                    "trip_distance_m": scout.trip_distance_m, "diagonal_turn_count": scout.diagonal_turn_count,
                })
                robot_energy_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                             "internal_energy": scout.internal_energy, "phase": scout.phase})
                if action == "RESOURCE_DETECTED":
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": scout.trip_id, "event": "RESOURCE_DETECTED",
                                           "detail": self.energy_sensor.active_endpoint.endpoint_id})
                elif action == "RESOURCE_LIGHT_DETECTED":
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": scout.trip_id, "event": "RESOURCE_LIGHT_DETECTED",
                                           "detail": scout.harvest_resource_id or "UNKNOWN"})
                elif action == "HARVEST_ACTIVE":
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": scout.trip_id, "event": "HARVEST_ACTIVE",
                                           "detail": f"resource_id={scout.harvest_resource_id}; carried_energy={scout.carried_harvest_energy:.6f}"})
                elif action == "HARVEST_COMPLETE":
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": scout.trip_id, "event": "HARVEST_COMPLETE",
                                           "detail": f"resource_id={scout.harvest_resource_id}; carried_energy={scout.carried_harvest_energy:.6f}; harvest_elapsed_s={scout.harvest_elapsed_s:.6f}"})
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": scout.trip_id, "event": "RETURN_HOME_START",
                                           "detail": "stateless_local_reactive_return; rssi_confirmation_only"})
                elif action == "NEST_REACHED":
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": scout.trip_id, "event": "NEST_REACHED",
                                           "detail": "within_nest_delivery_radius"})
                elif action == "DELIVER":
                    delivered_trip_id = scout.trip_id - 1
                    nest_energy_before = self.nest_energy
                    delivered_energy = scout.last_delivered_energy
                    self.gross_delivered_energy += delivered_energy
                    self.nest_energy += delivered_energy
                    nest_energy_after = self.nest_energy
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": delivered_trip_id, "event": "DELIVER",
                                           "detail": (
                                               f"nest_energy_before={nest_energy_before}; "
                                               f"nest_energy_after={nest_energy_after}; "
                                               f"delivered_harvest_energy={delivered_energy:.6f}"
                                           )})
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": delivered_trip_id, "event": "NEST_ENERGY_UPDATED",
                                           "detail": f"previous_energy={nest_energy_before:.6f}; delivered_energy={delivered_energy:.6f}; new_energy={nest_energy_after:.6f}; target={self.nest_energy_target}"})
                    energy_timeline_writer.writerow({
                        "run_id": self.run_dir.name, "seed": self.seed,
                        "timestamp": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                        "event_type": "DELIVERY",
                        "previous_energy": nest_energy_before, "delivered_energy": delivered_energy,
                        "withdrawal_energy": 0.0, "new_energy": nest_energy_after,
                        "gross_delivered_energy": self.gross_delivered_energy,
                        "target": self.nest_energy_target,
                    })
                    # Delivery has priority. Only if the target remains
                    # unreached may this no-AIH Scout refill from the common
                    # Nest for its next exploratory cycle.
                    if not self._nest_target_reached():
                        required = max(0.0, self.internal_energy_capacity - scout.internal_energy)
                        withdrawal = min(required, self.nest_energy)
                        if withdrawal > 0.0:
                            self.nest_energy -= withdrawal
                            self.total_nest_withdrawal += withdrawal
                            scout.internal_energy += withdrawal
                            scout.nest_withdrawn_energy += withdrawal
                            event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                                   "trip_id": scout.trip_id, "event": "NEST_ENERGY_WITHDRAWAL",
                                                   "detail": f"withdrawal={withdrawal:.6f}; net_nest_energy={self.nest_energy:.6f}; robot_energy={scout.internal_energy:.6f}"})
                            energy_timeline_writer.writerow({
                                "run_id": self.run_dir.name, "seed": self.seed,
                                "timestamp": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                "event_type": "ROBOT_RECHARGE_WITHDRAWAL",
                                "previous_energy": nest_energy_after, "delivered_energy": 0.0,
                                "withdrawal_energy": withdrawal, "new_energy": self.nest_energy,
                                "gross_delivered_energy": self.gross_delivered_energy,
                                "target": self.nest_energy_target,
                            })
                    if scout.phase == "EXPLORE" and not self._nest_target_reached():
                        event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                               "trip_id": scout.trip_id, "event": "NEXT_CYCLE_START",
                                               "detail": f"cycle_id={scout.cycle_id}; memory_free_reactive_explore"})
                if robot_depleted_started:
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": scout.trip_id, "event": "ROBOT_DEPLETED",
                                           "detail": "internal_energy_reached_zero"})
                if contact_stall_started:
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": scout.trip_id, "event": "CONTACT_STALLED",
                                           "detail": scout.recovery_failure_detail or "three commanded steps produced no translation or rotation"})
                elif action == "CONTACT_RECOVERY_START":
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": scout.trip_id, "event": "CONTACT_RECOVERY_START",
                                           "detail": "bounded back-off and fresh-LiDAR reorientation"})
                elif action == "CONTACT_RECOVERY_RETRY":
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": scout.trip_id, "event": "CONTACT_RECOVERY_RETRY",
                                           "detail": "first recovery moved but collision persisted; one final fresh-LiDAR maneuver"})
                if action in {
                    "RESOURCE_LIGHT_DETECTED", "HARVEST_COMPLETE", "NEST_REACHED", "DELIVER",
                    "CONTACT_RECOVERY_START", "CONTACT_RECOVERY_RETRY", "CONTACT_RECOVERY_COMPLETE",
                } or robot_depleted_started:
                    last_meaningful_event_time_s = round(float(self.env.time), 6)
            if self.render_enabled and step % 3 == 0:
                self.env.render()
                self._draw_energy_marker()
                self._draw_scout_heading_markers()
            if self.mission_mode == "research" and self._nest_target_reached():
                mission_complete = True
                target_reached_time_s = round(float(self.env.time), 6)
                termination_time_s = target_reached_time_s
                termination_reason = "NEST_ENERGY_TARGET_REACHED"
                event_writer.writerow({"sim_time_s": target_reached_time_s, "scout_id": "COLONY",
                                       "trip_id": "", "event": "MISSION_COMPLETE",
                                       "detail": f"nest_energy={self.nest_energy:.6f}; target={self.nest_energy_target}; termination_reason=NEST_ENERGY_TARGET_REACHED"})
                break
            if self.mission_mode == "research" and self._colony_failure_all_depleted():
                mission_complete = True
                termination_time_s = round(float(self.env.time), 6)
                termination_reason = "COLONY_FAILURE_ALL_DEPLETED"
                state = self._termination_state_snapshot(last_meaningful_event_time_s, last_active_scout_id)
                event_writer.writerow({"sim_time_s": termination_time_s, "scout_id": "COLONY",
                                       "trip_id": "", "event": "COLONY_FAILURE_ALL_DEPLETED",
                                       "detail": json.dumps(state, sort_keys=True)})
                break
            if self.mission_mode == "trip_limited" and all(s.phase == "COMPLETE" for s in self.scouts):
                mission_complete = True
                termination_reason = "TRIP_LIMIT_REACHED"
                break

        if self.mission_mode == "research" and not mission_complete:
            termination_time_s = round(float(self.env.time), 6)
            event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": "COLONY",
                                   "trip_id": "", "event": "EXPERIMENT_TERMINATED",
                                   "detail": f"reason=TIME_LIMIT_REACHED; nest_energy={self.nest_energy:.6f}; target={self.nest_energy_target}"})
        for scout in self.scouts:
            for row in scout.trip_rows:
                trip_writer.writerow({"scout_id": scout.scout_id, **row})
        trajectory.close(); event_file.close(); trip_file.close(); energy_timeline_file.close(); robot_energy_file.close()

        delivered = self.nest_energy
        all_complete = all(s.phase == "COMPLETE" for s in self.scouts)
        has_controller_contact_failure = any(s.contact_stalled for s in self.scouts)
        has_stationary_turn_deadlock = any(
            s.persistent_stationary_turn_deadlock for s in self.scouts
        )
        if self.mission_mode == "research" and not mission_complete:
            termination_reason = "TIME_LIMIT_REACHED"
        result = {
            "status": "COMPLETED",
            "engineering_status": "COMPLETED",
            "mission_outcome": (
                "MISSION_SUCCESS" if self.mission_mode == "research" and termination_reason == "NEST_ENERGY_TARGET_REACHED"
                else "COLONY_FAILURE_ALL_DEPLETED" if self.mission_mode == "research" and termination_reason == "COLONY_FAILURE_ALL_DEPLETED"
                else "TIME_LIMIT_REACHED" if self.mission_mode == "research"
                else "SUCCESS" if all_complete else ("NO_SUCCESSFUL_DELIVERY" if delivered == 0 else "TIME_LIMIT_REACHED")
            ),
            # Resource-not-found and a time horizon are legitimate baseline
            # outcomes.  A controller contact stall is not: it must remain
            # visibly invalid until the engineering defect is removed.
            "experimental_validity": (
                "INVALID_CONTROLLER_CONTACT_FAILURE"
                if has_controller_contact_failure or has_stationary_turn_deadlock
                else "VALID"
            ),
            "experiment": "CONDITION_1_BASELINE_MULTI_SCOUT_LOCAL_REACTIVE",
            "scout_count": self.scout_count, "requested_trips_per_scout": self.trip_count,
            "simulation_time_s": round(float(self.env.time), 6), "nest_energy_units": delivered,
            "gross_delivered_energy": self.gross_delivered_energy,
            "total_robot_nest_withdrawal": self.total_nest_withdrawal,
            "net_nest_energy": self.nest_energy,
            "nest_energy_target": self.nest_energy_target,
            "target_reached": termination_reason == "NEST_ENERGY_TARGET_REACHED" if self.mission_mode == "research" else None,
            "target_reached_time_s": target_reached_time_s,
            "termination_reason": termination_reason,
            "termination_time_s": termination_time_s,
            "last_meaningful_event_time_s": last_meaningful_event_time_s,
            "termination_state": self._termination_state_snapshot(last_meaningful_event_time_s, last_active_scout_id),
            "mission_mode": self.mission_mode,
            "working_memory_enabled": False, "experience_memory_enabled": False,
            "hormone_enabled": False, "exchange_enabled": False, "shared_map_created": False,
            "return_navigation": "STATELESS_LOCAL_REACTIVE_NO_RSSI_STEERING",
            "nest_cue_definition": (
                "RSSI confirmation only with physical Nest-entry validation; "
                "not navigation, bearing, distance, route, map, or planner"
            ),
            "local_45_degree_turn_enabled": True,
            "isolation_assertions": {
                "visited_branch_memory": False, "route_breadcrumbs": False,
                "cross_trip_preference": False, "message_bus": False, "global_planner": False,
            },
            "scouts": [{
                "scout_id": s.scout_id, "phase_at_termination": s.phase, "completed_trip_count": s.delivery_count, "started_trip_count": s.started_trip_count,
                "completed_cycle_count": s.completed_cycle_count, "active_cycle_id": s.cycle_id,
                "behavioral_outcome": self._behavioral_outcome(s), "resource_found_count": s.resource_found_count,
                "collection_count": s.collection_count, "delivery_count": s.delivery_count,
                "internal_energy_final": s.internal_energy, "internal_energy_min": s.minimum_internal_energy,
                "nest_withdrawn_energy": s.nest_withdrawn_energy, "depleted": s.depleted,
                "distance_m": s.distance_m, "coverage_cells_0_5m": len(coverage[s.scout_id]),
                "diagonal_turn_count": s.diagonal_turn_count,
                "blocked_turn_count": s.obstacle_turn_count,
                "blocked_sensor_samples": s.blocked_count,
                "contact_stalled": s.contact_stalled,
                "contact_recovery_count": s.contact_recovery_count,
                "persistent_stationary_turn_deadlock": s.persistent_stationary_turn_deadlock,
                "max_consecutive_stationary_rotation_steps": s.max_stationary_rotation_steps,
                "reactive_oscillation_warning": s.obstacle_turn_count >= 20 and s.obstacle_turn_count / max(1, s.diagonal_turn_count) >= 0.80,
            } for s in self.scouts],
        }
        (self.run_dir / "swarm_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
