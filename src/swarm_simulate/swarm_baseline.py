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
from matplotlib.patches import Circle

from energy_sensor import RandomEndpointEnergySensor
from irsim_range_sensor import IRSimDirectionalRangeSensor
from motion_types import RobotPose


def _wrap(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


@dataclass
class ScoutState:
    scout_id: int
    rng: random.Random
    home: RobotPose
    phase: str = "EXPLORE"
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
    resource_departure_steps: int = 0
    # Current obstacle-bypass maneuver only. Cleared as soon as a fresh scan
    # says that the nest cue can be pursued through a turn-safe local opening.
    bypass_active: bool = False
    bypass_departure_steps: int = 0
    # Reporting-only detection of a controller pathology.  It never feeds a
    # navigation choice and therefore cannot create a memory advantage.
    return_stationary_turn_steps: int = 0
    return_arbitration_pathology: bool = False
    previous_pose: RobotPose | None = None
    trip_start_s: float = 0.0
    collected_at_s: float | None = None
    trip_rows: list[dict[str, Any]] = field(default_factory=list)


class BaselineSwarmRunner:
    """Run Condition 1 without any learning or inter-Scout communication."""

    def __init__(
        self, *, env, run_dir: Path, energy_sensor: RandomEndpointEnergySensor,
        seed: int, scout_count: int, duration_s: float, trip_count: int,
        render_enabled: bool, mission_mode: str = "trip_limited",
        nest_energy_target: int | None = None,
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
        # A resource is a shared physical object: only one body can carry one
        # unit at a time. This is environment state, not a Scout message or
        # learned information. Delivery makes the controlled source available
        # again for a later independent trip.
        self.resource_carrier_id: int | None = None
        # Display-only marker for visual replay.  It has no IR-SIM body and
        # never participates in collision, sensing, or controller state.
        self._display_energy_marker = None
        self._add_scouts()
        self.sensors = [
            IRSimDirectionalRangeSensor(env=env, range_max_m=5.0, robot_id=i)
            for i in range(self.scout_count)
        ]
        self.scouts = [
            ScoutState(
                scout_id=i,
                rng=random.Random(self.seed + 104729 * i),
                home=self._pose(env, i),
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
                plot={"show_trail": False, "show_sensor": False, "show_goal": False},
            ))
        if extras:
            self.env.add_objects(extras)

    def _draw_energy_marker(self) -> None:
        """Keep the fixed source visible in a rendered Baseline replay."""
        if not self.render_enabled:
            return
        import matplotlib.pyplot as plt

        figure = plt.gcf()
        if not figure.axes:
            return
        axes = figure.axes[0]
        if self._display_energy_marker is None:
            self._display_energy_marker = Circle(
                (self.energy_sensor.active_endpoint.x_m, self.energy_sensor.active_endpoint.y_m),
                self.energy_sensor.visible_marker_radius_m,
                facecolor="yellow", edgecolor="goldenrod", linewidth=1.5, zorder=100,
            )
        if self._display_energy_marker not in axes.patches:
            axes.add_patch(self._display_energy_marker)

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
        self._start_turn(scout, scout.escape_direction, "OBSTACLE_ESCAPE_TURN_45")
        return self._continue_turn(scout)

    def _begin_clear_side_turn(self, scout: ScoutState, snapshot, reason: str) -> tuple[float, float, str]:
        direction = 1.0 if snapshot.left_m >= snapshot.right_m else -1.0
        scout.escape_direction = direction
        scout.escape_turn_count += 1
        self._start_turn(scout, direction, reason)
        return self._continue_turn(scout)

    def _return_bypass_command(self, scout: ScoutState, snapshot, sensor) -> tuple[float, float, str] | None:
        """Arbitrate current nest bearing against current free space only."""
        if not scout.bypass_active:
            return None
        if scout.turn_remaining_rad:
            return self._continue_turn(scout)
        if scout.escape_direction != 0.0:
            # A local turn whose front is still body-unsafe has not completed
            # its maneuver.  Continue around the same currently selected
            # side rather than re-score the home cue and immediately reverse
            # the preceding 45-degree turn.
            if snapshot.front_m <= self.safe_front_m:
                self._start_turn(
                    scout,
                    scout.escape_direction,
                    "RETURN_LOCAL_ARBITRATION_TURN_45",
                )
                return self._continue_turn(scout)
            scout.escape_direction = 0.0
        if scout.bypass_departure_steps:
            if snapshot.front_m > self.safe_front_m:
                scout.bypass_departure_steps -= 1
                return self.linear_speed_mps, 0.0, "RETURN_BYPASS_DEPART_FORWARD"
            scout.bypass_departure_steps = 0

        pose = snapshot.pose
        desired = math.atan2(scout.home.y_m - pose.y_m, scout.home.x_m - pose.x_m)
        error = _wrap(desired - pose.theta_rad)
        candidates: list[tuple[float, float]] = []
        for offset in (0.0, -math.pi / 4.0, math.pi / 4.0, -math.pi / 2.0, math.pi / 2.0):
            ray, _, inside, valid = sensor.ray_distance(offset)
            if not (inside and valid and ray > self.safe_front_m):
                continue
            # ``front_m`` is deliberately the minimum of the ±20 degree
            # body-leading beams.  A clear centre ray alone can pass a corner
            # that the 0.25 m circular body will clip, so it must never
            # authorize a straight recovery/bypass departure by itself.
            if abs(offset) < 1e-9 and snapshot.front_m <= self.safe_front_m:
                continue
            if offset < 0.0 and snapshot.right_m < self.turn_side_clearance_m:
                continue
            if offset > 0.0 and snapshot.left_m < self.turn_side_clearance_m:
                continue
            candidates.append((abs(_wrap(error - offset)), offset))
        if not candidates:
            scout.blocked_count += 1
            scout.bypass_departure_steps = max(
                scout.bypass_departure_steps, self.bypass_departure_step_count
            )
            return self._begin_clear_side_turn(
                scout, snapshot, "RETURN_LOCAL_ARBITRATION_TURN_45"
            )
        _, offset = min(candidates, key=lambda item: item[0])
        if abs(offset) < 1e-9:
            if abs(error) <= math.radians(22.5):
                scout.bypass_active = False
                scout.escape_direction = 0.0
                return None
            return self.linear_speed_mps, 0.0, "RETURN_BYPASS_FORWARD"
        direction = 1.0 if offset > 0.0 else -1.0
        scout.escape_direction = direction
        self._start_turn(
            scout, direction,
            "RETURN_LOCAL_ARBITRATION_TURN_45",
        )
        # Finish this one locally safe maneuver before asking the nest cue to
        # arbitrate again.  Without a bounded departure, two adjacent
        # headings can each nominate the other 45-degree heading and create
        # an in-place -90/-135 degree flip-flop.  This is current actuator
        # state, cleared after the departure, not obstacle or route memory.
        scout.bypass_departure_steps = max(
            scout.bypass_departure_steps, self.bypass_departure_step_count
        )
        return self._continue_turn(scout)

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
            scout.recovery_translation_m >= 0.01
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
        if scout.resource_departure_steps:
            if snapshot.front_m > self.safe_front_m:
                scout.resource_departure_steps -= 1
                return self.linear_speed_mps, 0.0, "RESOURCE_OCCUPIED_DEPART"
            scout.resource_departure_steps = 0
            scout.blocked_count += 1
            return self._obstacle_escape_command(scout, snapshot)
        if reading.detected:
            if self.resource_carrier_id is not None and self.resource_carrier_id != scout.scout_id:
                direction = 1.0 if scout.rng.random() < 0.5 else -1.0
                self._start_turn(scout, direction, "RESOURCE_OCCUPIED_TURN_45")
                scout.resource_departure_steps = 8
                return self._continue_turn(scout)
            scout.resource_found_count += 1
            scout.phase = "COLLECT"
            return 0.0, 0.0, "RESOURCE_DETECTED"
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

    def _return_command(self, scout: ScoutState, snapshot, sensor) -> tuple[float, float, str]:
        """Existing baseline's stateless home-vector policy, quantized to 45°.

        The fixed home pose is a common navigation infrastructure cue, not a
        remembered outbound route.  No previous branch, route, or trip result
        is consulted here.
        """
        pose = snapshot.pose
        if scout.recovery_stage:
            return self._contact_recovery_command(scout, snapshot)
        bypass = self._return_bypass_command(scout, snapshot, sensor)
        if bypass is not None:
            return bypass
        home_error = math.hypot(pose.x_m - scout.home.x_m, pose.y_m - scout.home.y_m)
        if home_error <= self.nest_delivery_radius_m:
            scout.phase = "DELIVER"
            return 0.0, 0.0, "NEST_REACHED"
        if scout.escape_direction != 0.0:
            return self._obstacle_escape_command(scout, snapshot)
        if scout.turn_remaining_rad:
            return self._continue_turn(scout)
        desired = math.atan2(scout.home.y_m - pose.y_m, scout.home.x_m - pose.x_m)
        heading_error = _wrap(desired - pose.theta_rad)
        if abs(heading_error) > math.radians(22.5):
            direction = 1.0 if heading_error > 0.0 else -1.0
            turn_side_clearance = snapshot.left_m if direction > 0.0 else snapshot.right_m
            home_ray, _, home_inside_fov, home_ray_valid = sensor.ray_distance(heading_error)
            if (
                turn_side_clearance < self.turn_side_clearance_m
                or not (home_inside_fov and home_ray_valid and home_ray > self.safe_front_m)
            ):
                scout.bypass_active = True
                scout.escape_direction = 0.0
                command = self._return_bypass_command(scout, snapshot, sensor)
                if command is not None:
                    return command
                return self.linear_speed_mps, 0.0, "RETURN_HOME_VECTOR"
            self._start_turn(scout, direction, "HOME_CUE_TURN_45")
            return self._continue_turn(scout)
        if snapshot.front_m <= self.safe_front_m:
            scout.blocked_count += 1
            scout.bypass_active = True
            scout.escape_direction = 0.0
            command = self._return_bypass_command(scout, snapshot, sensor)
            if command is not None:
                return command
            return self.linear_speed_mps, 0.0, "RETURN_HOME_VECTOR"
        if min(snapshot.left_m, snapshot.right_m) < self.turn_side_clearance_m:
            scout.bypass_active = True
            scout.escape_direction = 0.0
            scout.bypass_departure_steps = 10
            return self._begin_clear_side_turn(
                scout, snapshot, "RETURN_SIDE_CLEARANCE_ESCAPE_45"
            )
        return self.linear_speed_mps, 0.0, "RETURN_HOME_VECTOR"

    def _command_for(self, scout: ScoutState, sensor: IRSimDirectionalRangeSensor) -> tuple[float, float, str, Any]:
        snapshot = sensor.read()
        reading = self.energy_sensor.read(snapshot.pose, sensor)
        if scout.phase == "EXPLORE":
            linear, angular, action = self._explore_command(scout, snapshot, reading, sensor)
        elif scout.phase == "COLLECT":
            if self.resource_carrier_id is None:
                self.resource_carrier_id = scout.scout_id
                scout.collection_count += 1
                scout.return_attempt_count += 1
                scout.collected_at_s = float(self.env.time)
                scout.phase = "RETURN_HOME"
                linear, angular, action = 0.0, 0.0, "COLLECT"
            else:
                # The source is occupied by another physical carrier. Resume
                # independent exploration; no information is retained.
                scout.phase = "EXPLORE"
                linear, angular, action = 0.0, 0.0, "RESOURCE_OCCUPIED"
        elif scout.phase == "RETURN_HOME":
            linear, angular, action = self._return_command(scout, snapshot, sensor)
        elif scout.phase == "DELIVER":
            scout.delivery_count += 1
            scout.trip_rows.append({
                "trip_id": scout.trip_id, "outcome": "SUCCESS", "collection_s": scout.collected_at_s,
                "delivery_s": float(self.env.time), "trip_distance_m": scout.trip_distance_m,
            })
            scout.trip_distance_m = 0.0
            scout.collected_at_s = None
            if self.resource_carrier_id == scout.scout_id:
                self.resource_carrier_id = None
            scout.phase = (
                "COMPLETE"
                if self.mission_mode == "trip_limited" and scout.trip_id >= self.trip_count
                else "EXPLORE"
            )
            scout.trip_id += 1
            if scout.phase == "EXPLORE":
                scout.started_trip_count += 1
            linear, angular, action = 0.0, 0.0, "DELIVER"
        else:
            linear, angular, action = 0.0, 0.0, "MISSION_COMPLETE"
        return linear, angular, action, reading

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

    def run(self) -> dict[str, Any]:
        trajectory = (self.run_dir / "swarm_trajectory.csv").open("w", newline="", encoding="utf-8")
        event_file = (self.run_dir / "swarm_events.csv").open("w", newline="", encoding="utf-8")
        trip_file = (self.run_dir / "swarm_trip_summary.csv").open("w", newline="", encoding="utf-8")
        energy_timeline_file = (self.run_dir / "nest_energy_timeline.csv").open(
            "w", newline="", encoding="utf-8"
        )
        trajectory_writer = csv.DictWriter(trajectory, fieldnames=[
            "sim_time_s", "scout_id", "trip_id", "phase", "x_m", "y_m", "heading_deg", "action",
            "linear_velocity_mps", "angular_velocity_radps", "front_m", "left_m", "right_m", "solar_max",
            "cumulative_distance_m", "trip_distance_m", "diagonal_turn_count",
        ])
        event_writer = csv.DictWriter(event_file, fieldnames=["sim_time_s", "scout_id", "trip_id", "event", "detail"])
        trip_writer = csv.DictWriter(trip_file, fieldnames=["scout_id", "trip_id", "outcome", "collection_s", "delivery_s", "trip_distance_m"])
        energy_timeline_writer = csv.DictWriter(
            energy_timeline_file,
            fieldnames=["run_id", "seed", "timestamp", "scout_id", "previous_energy", "delivered_energy", "new_energy", "target"],
        )
        trajectory_writer.writeheader(); event_writer.writeheader(); trip_writer.writeheader(); energy_timeline_writer.writeheader()
        coverage: dict[int, set[tuple[int, int]]] = {i: set() for i in range(self.scout_count)}
        for scout in self.scouts:
            scout.previous_pose = self._pose(self.env, scout.scout_id)
            scout.trip_start_s = 0.0
            event_writer.writerow({"sim_time_s": 0.0, "scout_id": scout.scout_id, "trip_id": 1,
                                   "event": "SCOUT_START", "detail": "independent local-reactive baseline"})

        maximum_steps = int(math.ceil(self.duration_s / self.env.step_time))
        mission_complete = False
        target_reached_time_s: float | None = None
        termination_reason = "EXPERIMENT_HORIZON_REACHED"
        for step in range(maximum_steps):
            commands, rows = [], []
            for scout, sensor in zip(self.scouts, self.sensors, strict=True):
                linear, angular, action, reading = self._command_for(scout, sensor)
                commands.append([linear, angular])
                rows.append((
                    scout, sensor.read(), reading, action, linear, angular,
                    scout.recovery_stage,
                ))
            action_ids = [self.env.objects.index(self.env.robot_list[i]) for i in range(self.scout_count)]
            self.env.step(commands, action_id=action_ids)
            for scout, snapshot, reading, action, linear, angular, recovery_stage in rows:
                contact_stall_started = False
                pose = self._pose(self.env, scout.scout_id)
                moved = math.hypot(pose.x_m - scout.previous_pose.x_m, pose.y_m - scout.previous_pose.y_m)
                turned = abs(_wrap(pose.theta_rad - scout.previous_pose.theta_rad)) > 1e-7
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
                if (
                    action == "RETURN_LOCAL_ARBITRATION_TURN_45"
                    and moved < 1e-7
                ):
                    scout.return_stationary_turn_steps += 1
                    if scout.return_stationary_turn_steps >= self.return_stationary_turn_limit:
                        scout.return_arbitration_pathology = True
                else:
                    scout.return_stationary_turn_steps = 0
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
                coverage[scout.scout_id].add((math.floor(pose.x_m / 0.5), math.floor(pose.y_m / 0.5)))
                trajectory_writer.writerow({
                    "sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                    "trip_id": (scout.trip_id if self.mission_mode == "research" else min(scout.trip_id, self.trip_count)), "phase": scout.phase,
                    "x_m": pose.x_m, "y_m": pose.y_m, "heading_deg": math.degrees(pose.theta_rad),
                    "action": action, "linear_velocity_mps": linear, "angular_velocity_radps": angular,
                    "front_m": snapshot.front_m, "left_m": snapshot.left_m, "right_m": snapshot.right_m,
                    "solar_max": reading.solar_max, "cumulative_distance_m": scout.distance_m,
                    "trip_distance_m": scout.trip_distance_m, "diagonal_turn_count": scout.diagonal_turn_count,
                })
                if action == "RESOURCE_DETECTED":
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": scout.trip_id, "event": "RESOURCE_DETECTED",
                                           "detail": self.energy_sensor.active_endpoint.endpoint_id})
                elif action == "COLLECT":
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": scout.trip_id, "event": "COLLECT",
                                           "detail": "one_energy_unit"})
                    # COLLECT changes the state to RETURN_HOME in the same
                    # controller step.  This extra event is audit evidence;
                    # it does not feed back into any controller decision.
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": scout.trip_id, "event": "RETURN_HOME_START",
                                           "detail": "stateless_home_vector"})
                elif action == "NEST_REACHED":
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": scout.trip_id, "event": "NEST_REACHED",
                                           "detail": "within_nest_delivery_radius"})
                elif action == "DELIVER":
                    delivered_trip_id = scout.trip_id - 1
                    nest_energy_after = sum(item.delivery_count for item in self.scouts)
                    nest_energy_before = nest_energy_after - 1
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": delivered_trip_id, "event": "DELIVER",
                                           "detail": (
                                               f"nest_energy_before={nest_energy_before}; "
                                               f"nest_energy_after={nest_energy_after}; "
                                               "resource_carrier_released=true"
                                           )})
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": delivered_trip_id, "event": "NEST_ENERGY_UPDATED",
                                           "detail": f"previous_energy={nest_energy_before}; delivered_energy=1; new_energy={nest_energy_after}; target={self.nest_energy_target}"})
                    energy_timeline_writer.writerow({
                        "run_id": self.run_dir.name, "seed": self.seed,
                        "timestamp": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                        "previous_energy": nest_energy_before, "delivered_energy": 1,
                        "new_energy": nest_energy_after, "target": self.nest_energy_target,
                    })
                    if scout.phase == "EXPLORE":
                        event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                               "trip_id": scout.trip_id, "event": "NEXT_TRIP_START",
                                               "detail": "memory_free_reactive_explore"})
                elif action == "RESOURCE_OCCUPIED":
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": min(scout.trip_id, self.trip_count), "event": action,
                                           "detail": "held_by_another_scout"})
                if contact_stall_started:
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": scout.trip_id, "event": "CONTACT_STALLED",
                                           "detail": scout.recovery_failure_detail or "three commanded steps produced no translation or rotation"})
                elif action == "CONTACT_RECOVERY_START":
                    event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": scout.scout_id,
                                           "trip_id": scout.trip_id, "event": "CONTACT_RECOVERY_START",
                                           "detail": "bounded back-off and fresh-LiDAR reorientation"})
            if self.render_enabled and step % 3 == 0:
                self.env.render()
                self._draw_energy_marker()
            delivered_this_tick = sum(s.delivery_count for s in self.scouts)
            if self.mission_mode == "research" and delivered_this_tick >= self.nest_energy_target:
                mission_complete = True
                target_reached_time_s = round(float(self.env.time), 6)
                termination_reason = "NEST_ENERGY_TARGET_REACHED"
                event_writer.writerow({"sim_time_s": target_reached_time_s, "scout_id": "COLONY",
                                       "trip_id": "", "event": "MISSION_COMPLETE",
                                       "detail": f"nest_energy={delivered_this_tick}; target={self.nest_energy_target}; termination_reason=NEST_ENERGY_TARGET_REACHED"})
                break
            if self.mission_mode == "trip_limited" and all(s.phase == "COMPLETE" for s in self.scouts):
                mission_complete = True
                termination_reason = "TRIP_LIMIT_REACHED"
                break

        if self.mission_mode == "research" and not mission_complete:
            event_writer.writerow({"sim_time_s": round(float(self.env.time), 6), "scout_id": "COLONY",
                                   "trip_id": "", "event": "EXPERIMENT_TERMINATED",
                                   "detail": f"reason=EXPERIMENT_HORIZON_REACHED; nest_energy={sum(s.delivery_count for s in self.scouts)}; target={self.nest_energy_target}"})
        for scout in self.scouts:
            for row in scout.trip_rows:
                trip_writer.writerow({"scout_id": scout.scout_id, **row})
        trajectory.close(); event_file.close(); trip_file.close(); energy_timeline_file.close()

        delivered = sum(s.delivery_count for s in self.scouts)
        all_complete = all(s.phase == "COMPLETE" for s in self.scouts)
        has_controller_contact_failure = any(s.contact_stalled for s in self.scouts)
        has_return_arbitration_pathology = any(
            s.return_arbitration_pathology for s in self.scouts
        )
        if self.mission_mode == "research" and not mission_complete:
            termination_reason = "EXPERIMENT_HORIZON_REACHED"
        result = {
            "status": "COMPLETED",
            "engineering_status": "COMPLETED",
            "mission_outcome": (
                "MISSION_SUCCESS" if self.mission_mode == "research" and mission_complete
                else "TIME_LIMIT_REACHED" if self.mission_mode == "research"
                else "SUCCESS" if all_complete else ("NO_SUCCESSFUL_DELIVERY" if delivered == 0 else "TIME_LIMIT_REACHED")
            ),
            # Resource-not-found and a time horizon are legitimate baseline
            # outcomes.  A controller contact stall is not: it must remain
            # visibly invalid until the engineering defect is removed.
            "experimental_validity": (
                "INVALID_CONTROLLER_CONTACT_FAILURE"
                if has_controller_contact_failure or has_return_arbitration_pathology
                else "VALID"
            ),
            "experiment": "CONDITION_1_BASELINE_MULTI_SCOUT_LOCAL_REACTIVE",
            "scout_count": self.scout_count, "requested_trips_per_scout": self.trip_count,
            "simulation_time_s": round(float(self.env.time), 6), "nest_energy_units": delivered,
            "nest_energy_target": self.nest_energy_target,
            "target_reached": mission_complete if self.mission_mode == "research" else None,
            "target_reached_time_s": target_reached_time_s,
            "termination_reason": termination_reason,
            "mission_mode": self.mission_mode,
            "working_memory_enabled": False, "experience_memory_enabled": False,
            "hormone_enabled": False, "exchange_enabled": False, "shared_map_created": False,
            "return_navigation": "STATELESS_HOME_VECTOR_COMMON_INFRASTRUCTURE",
            "nest_cue_definition": (
                "IDEALIZED_COMMON_STATELESS_NEST_HOMING_CUE; "
                "instantaneous nest direction only; no route, history, map, or planner"
            ),
            "local_45_degree_turn_enabled": True,
            "isolation_assertions": {
                "visited_branch_memory": False, "route_breadcrumbs": False,
                "cross_trip_preference": False, "message_bus": False, "global_planner": False,
            },
            "scouts": [{
                "scout_id": s.scout_id, "phase_at_termination": s.phase, "completed_trip_count": s.delivery_count, "started_trip_count": s.started_trip_count,
                "behavioral_outcome": self._behavioral_outcome(s), "resource_found_count": s.resource_found_count,
                "collection_count": s.collection_count, "delivery_count": s.delivery_count,
                "distance_m": s.distance_m, "coverage_cells_0_5m": len(coverage[s.scout_id]),
                "diagonal_turn_count": s.diagonal_turn_count,
                "blocked_turn_count": s.obstacle_turn_count,
                "blocked_sensor_samples": s.blocked_count,
                "contact_stalled": s.contact_stalled,
                "contact_recovery_count": s.contact_recovery_count,
                "return_arbitration_pathology": s.return_arbitration_pathology,
                "reactive_oscillation_warning": s.obstacle_turn_count >= 20 and s.obstacle_turn_count / max(1, s.diagonal_turn_count) >= 0.80,
            } for s in self.scouts],
        }
        (self.run_dir / "swarm_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
