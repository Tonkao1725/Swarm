from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import json
from pathlib import Path
from typing import Any


@dataclass
class PathCommand:
    command: str
    value: float
    source: str


@dataclass
class Breadcrumb:
    """Sparse pose sample belonging only to the current Trip."""

    x_m: float
    y_m: float
    theta_rad: float
    cumulative_distance_m: float
    path_index: int
    junction_count: int
    # Unlike a translation sample, this pose marks the exact place where the
    # outbound route changed direction.  Return uses it only to recognise a
    # segment that was physically traversed during this current Trip.
    is_turn_anchor: bool = False


@dataclass
class JunctionRecord:
    """One local decision made during the current Trip.

    decision_point_key is a trip-local landmark label. It is not a map node and
    is never persisted as a world graph.
    """
    decision_point_key: str
    arrival_heading_quadrant: int
    chosen_action: str
    reason: str
    open_actions: list[str]
    candidate_actions: list[str]
    path_index_before_decision: int
    decision_ordinal: int

    @property
    def junction_key(self) -> str:
        return self.decision_point_key

    @property
    def unvisited_actions(self) -> list[str]:
        return self.candidate_actions


class WorkingMemory:
    """Rat-inspired mission-local memory.

    Stores only what happened in the current foraging Trip:
    executed route, breadcrumbs, local decision records, and local branch-use
    counts. It does not build a global map or connect decision points by edges.
    """

    INVERSE_TURN = {
        "TURN_LEFT": "TURN_RIGHT",
        "TURN_RIGHT": "TURN_LEFT",
        "TURN_BACK": "TURN_BACK",
    }

    def __init__(
        self,
        *,
        breadcrumb_spacing_m: float = 0.22,
        loop_closure_radius_m: float = 0.38,
        minimum_loop_points: int = 6,
        minimum_loop_distance_m: float = 1.20,
        maximum_breadcrumbs: int = 1200,
    ) -> None:
        self.path: list[PathCommand] = []
        self.junctions: list[JunctionRecord] = []
        self.decision_port_visits: dict[str, int] = {}

        self.breadcrumb_spacing_m = float(
            breadcrumb_spacing_m
        )
        self.loop_closure_radius_m = float(
            loop_closure_radius_m
        )
        self.minimum_loop_points = int(
            minimum_loop_points
        )
        self.minimum_loop_distance_m = float(
            minimum_loop_distance_m
        )
        self.maximum_breadcrumbs = int(
            maximum_breadcrumbs
        )

        self.breadcrumbs: list[Breadcrumb] = []
        self.cumulative_distance_m = 0.0
        self.loop_erasures = 0
        self.pruned_breadcrumbs = 0
        self.pruned_path_commands = 0
        self.pruned_decisions = 0

    def start_route(
        self,
        *,
        x_m: float,
        y_m: float,
        theta_rad: float,
    ) -> None:
        self.breadcrumbs.clear()
        self.cumulative_distance_m = 0.0
        self.breadcrumbs.append(
            Breadcrumb(
                x_m=float(x_m),
                y_m=float(y_m),
                theta_rad=float(theta_rad),
                cumulative_distance_m=0.0,
                path_index=0,
                junction_count=0,
            )
        )

    def _loop_closure_index(
        self,
        *,
        x_m: float,
        y_m: float,
    ) -> int | None:
        if len(self.breadcrumbs) <= self.minimum_loop_points:
            return None

        newest_eligible = (
            len(self.breadcrumbs)
            - self.minimum_loop_points
        )
        best_index = None
        best_distance = math.inf

        for index in range(newest_eligible):
            candidate = self.breadcrumbs[index]
            # Turn anchors preserve a corner for return only.  They have no
            # translation of their own, so using one as a loop-closure cut
            # point can truncate the outbound command suffix at the wrong
            # route state for backtracking.
            if candidate.is_turn_anchor:
                continue
            spatial_distance = math.hypot(
                float(x_m) - candidate.x_m,
                float(y_m) - candidate.y_m,
            )
            if spatial_distance > self.loop_closure_radius_m:
                continue

            travelled = (
                self.cumulative_distance_m
                - candidate.cumulative_distance_m
            )
            if travelled < self.minimum_loop_distance_m:
                continue

            if spatial_distance < best_distance:
                best_distance = spatial_distance
                best_index = index

        return best_index

    def record_pose(
        self,
        *,
        x_m: float,
        y_m: float,
        theta_rad: float,
        distance_delta_m: float,
    ) -> bool:
        """Record sparse breadcrumb and erase completed local loops.

        Returns True only when a loop was pruned.
        """
        self.cumulative_distance_m += max(
            0.0,
            float(distance_delta_m),
        )

        if not self.breadcrumbs:
            self.start_route(
                x_m=x_m,
                y_m=y_m,
                theta_rad=theta_rad,
            )
            return False

        last = self.breadcrumbs[-1]
        spacing = math.hypot(
            float(x_m) - last.x_m,
            float(y_m) - last.y_m,
        )
        if spacing < self.breadcrumb_spacing_m:
            return False

        closure = self._loop_closure_index(
            x_m=x_m,
            y_m=y_m,
        )
        pruned = False

        if closure is not None:
            candidate = self.breadcrumbs[closure]

            removed_breadcrumbs = (
                len(self.breadcrumbs) - closure - 1
            )
            old_path_count = len(self.path)
            old_junction_count = len(self.junctions)

            del self.breadcrumbs[closure + 1 :]
            self.truncate_path(candidate.path_index)
            del self.junctions[candidate.junction_count :]

            self.loop_erasures += 1
            self.pruned_breadcrumbs += removed_breadcrumbs
            self.pruned_path_commands += (
                old_path_count - len(self.path)
            )
            self.pruned_decisions += (
                old_junction_count - len(self.junctions)
            )
            pruned = True

        self.breadcrumbs.append(
            Breadcrumb(
                x_m=float(x_m),
                y_m=float(y_m),
                theta_rad=float(theta_rad),
                cumulative_distance_m=(
                    self.cumulative_distance_m
                ),
                path_index=len(self.path),
                junction_count=len(self.junctions),
            )
        )

        if len(self.breadcrumbs) > self.maximum_breadcrumbs:
            # Preserve HOME and the newest route tail.
            overflow = (
                len(self.breadcrumbs)
                - self.maximum_breadcrumbs
            )
            del self.breadcrumbs[1 : 1 + overflow]

        return pruned

    def record_turn_pose(
        self,
        *,
        x_m: float,
        y_m: float,
        theta_rad: float,
    ) -> None:
        """Preserve a current-trip corner for breadcrumb return.

        A turn can change the route direction without translating the robot.
        Omitting that pose makes the next sparse breadcrumb form a diagonal
        chord across the corner during the return trip.
        """
        if not self.breadcrumbs:
            self.start_route(x_m=x_m, y_m=y_m, theta_rad=theta_rad)
            return
        self.breadcrumbs.append(Breadcrumb(
            x_m=float(x_m), y_m=float(y_m), theta_rad=float(theta_rad),
            cumulative_distance_m=self.cumulative_distance_m,
            path_index=len(self.path), junction_count=len(self.junctions),
            is_turn_anchor=True,
        ))
        if len(self.breadcrumbs) > self.maximum_breadcrumbs:
            overflow = len(self.breadcrumbs) - self.maximum_breadcrumbs
            del self.breadcrumbs[1:1 + overflow]

    def reverse_breadcrumbs(self) -> list[Breadcrumb]:
        return list(reversed(self.breadcrumbs))

    def append_move(self, distance_m: float, source: str) -> None:
        if distance_m <= 0:
            return
        if self.path and self.path[-1].command == "MOVE_FORWARD" and self.path[-1].source == source:
            self.path[-1].value += float(distance_m)
            return
        self.path.append(PathCommand("MOVE_FORWARD", float(distance_m), source))

    def append_turn(self, action: str, source: str) -> None:
        if action not in {"TURN_LEFT", "TURN_RIGHT", "TURN_BACK"}:
            raise ValueError(f"Unsupported turn action: {action}")
        angle = {"TURN_LEFT": 90.0, "TURN_RIGHT": 90.0, "TURN_BACK": 180.0}[action]
        self.path.append(PathCommand(action, angle, source))

    @staticmethod
    def _port_key(decision_point_key: str, global_direction: int) -> str:
        return f"{decision_point_key}|D{int(global_direction) % 4}"

    def current_trip_port_visits(self, *, decision_point_key: str, global_direction: int) -> int:
        return int(self.decision_port_visits.get(self._port_key(decision_point_key, global_direction), 0))

    def record_decision_port(self, *, decision_point_key: str, global_direction: int) -> int:
        key = self._port_key(decision_point_key, global_direction)
        self.decision_port_visits[key] = self.decision_port_visits.get(key, 0) + 1
        return self.decision_port_visits[key]

    def add_junction(self, record: JunctionRecord) -> None:
        self.junctions.append(record)

    def truncate_path(self, index: int) -> None:
        if index < 0 or index > len(self.path):
            raise ValueError("Invalid Working Memory path index")
        del self.path[index:]

    def return_commands(self) -> list[PathCommand]:
        result=[]
        for item in reversed(self.path):
            if item.command == "MOVE_FORWARD":
                result.append(PathCommand("MOVE_FORWARD", item.value, "RETURN_REPLAY"))
            else:
                result.append(PathCommand(self.INVERSE_TURN[item.command], item.value, "RETURN_REPLAY"))
        return result

    @property
    def route_string(self) -> str:
        symbol={"TURN_LEFT":"L","TURN_RIGHT":"R","TURN_BACK":"B","MOVE_FORWARD":"F"}
        return "-".join(symbol[item.command] for item in self.path)

    @property
    def decision_sequence(self) -> list[str]:
        return [item.chosen_action for item in self.junctions]

    def snapshot(self) -> dict[str, Any]:
        return {
            "memory_type":"WORKING_MEMORY",
            "scope":"CURRENT_TRIP_ONLY",
            "biological_role":"REMEMBER_VISITED_CHOICES_AND_CURRENT_ROUTE",
            "world_map_created":False,
            "path_command_count":len(self.path),
            "route_string":self.route_string,
            "path":[asdict(item) for item in self.path],
            "decision_records":[asdict(item) for item in self.junctions],
            "decision_sequence":self.decision_sequence,
            "decision_port_visits":dict(self.decision_port_visits),
            "breadcrumbs":[asdict(item) for item in self.breadcrumbs],
            "breadcrumb_count":len(self.breadcrumbs),
            "loop_erasures":self.loop_erasures,
            "pruned_breadcrumbs":self.pruned_breadcrumbs,
            "pruned_path_commands":self.pruned_path_commands,
            "pruned_decisions":self.pruned_decisions,
            "return_commands":[asdict(item) for item in self.return_commands()],
        }

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.snapshot(),ensure_ascii=False,indent=2),encoding='utf-8')

    def clear(self) -> None:
        self.path.clear()
        self.junctions.clear()
        self.decision_port_visits.clear()
        self.breadcrumbs.clear()
        self.cumulative_distance_m = 0.0
        self.loop_erasures = 0
        self.pruned_breadcrumbs = 0
        self.pruned_path_commands = 0
        self.pruned_decisions = 0
