from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import json
from pathlib import Path
from typing import Any

from working_memory import WorkingMemory


@dataclass
class RouteExperience:
    source_id: str
    decision_sequence: list[str]
    decision_contexts: list[dict[str, Any]]
    outbound_distance_m: float
    total_trip_distance_m: float
    energy_cost: float
    resource_score: float
    success_count: int = 1
    failure_count: int = 0
    confidence: float = 0.50
    last_trip_id: int = 1


class ExperienceMemory:
    """Persistent memory of successful food-finding decisions.

    The memory stores a sequence of local decision contexts and the actions
    that previously led to food. It never stores a world map, Node/Edge graph,
    loop closure, global coordinates, or executable motor commands.
    """

    def __init__(
        self,
        *,
        energy_cost_per_meter: float = 1.0,
        resource_reward_units: float = 100.0,
        **_legacy: Any,
    ) -> None:
        self.energy_cost_per_meter = float(energy_cost_per_meter)
        self.resource_reward_units = float(resource_reward_units)
        self.routes: dict[str, RouteExperience] = {}
        self.completed_trip_count = 0
        self.current_trip_id = 0
        self.update_history: list[dict[str, Any]] = []

    def clear_persistent_routes(self) -> None:
        self.routes.clear()
        self.completed_trip_count = 0
        self.update_history.clear()

    def start_trip(self, trip_id: int) -> None:
        self.current_trip_id = int(trip_id)

    def has_successful_route(self, *, source_id: str) -> bool:
        route = self.routes.get(source_id)
        return bool(route is not None and route.decision_sequence)

    @staticmethod
    def _normalized_actions(actions: list[str]) -> list[str]:
        order = {
            "TURN_LEFT": 0,
            "MOVE_FORWARD": 1,
            "TURN_RIGHT": 2,
        }
        return sorted(actions, key=lambda item: order.get(item, 99))

    def recalled_action(
        self,
        *,
        source_id: str,
        decision_ordinal: int,
        arrival_heading_quadrant: int,
        candidate_actions: list[str],
    ) -> str | None:
        """Recall one successful local decision when its context still matches.

        Context matching is deliberately limited to data already inside the
        thesis scope:
        - decision order in the successful route,
        - arrival heading class,
        - locally open choices measured by ToF.

        This is not localization and does not identify a global maze position.
        """
        route = self.routes.get(source_id)
        if route is None:
            return None
        context = next(
            (
                item
                for item in route.decision_contexts
                if int(item["decision_ordinal"]) == int(decision_ordinal)
            ),
            None,
        )
        if context is None:
            return None
        current_actions = self._normalized_actions(candidate_actions)
        remembered_actions = self._normalized_actions(
            list(context["open_actions"])
        )

        if current_actions != remembered_actions:
            return None
        if (
            int(context["arrival_heading_quadrant"]) % 4
            != int(arrival_heading_quadrant) % 4
        ):
            return None

        action = str(context["chosen_action"])
        return action if action in candidate_actions else None

    # Compatibility wrapper for older analysis scripts. The actual controller
    # uses recalled_action() with context checking.
    def preferred_action(
        self,
        *,
        source_id: str,
        decision_ordinal: int,
        candidate_actions: list[str],
    ) -> str | None:
        route = self.routes.get(source_id)
        if route is None:
            return None
        if decision_ordinal < 0 or decision_ordinal >= len(route.decision_sequence):
            return None
        action = route.decision_sequence[decision_ordinal]
        return action if action in candidate_actions else None

    def commit_success(
        self,
        *,
        source_id: str,
        working_memory: WorkingMemory,
        outbound_distance_m: float,
        total_trip_distance_m: float,
        trip_id: int,
    ) -> dict[str, Any]:
        energy_cost = (
            float(total_trip_distance_m)
            * self.energy_cost_per_meter
        )
        resource_score = (
            self.resource_reward_units
            / max(energy_cost, 1e-9)
        )

        contexts = [
            {
                "decision_ordinal": int(item.decision_ordinal),
                "arrival_heading_quadrant": (
                    int(item.arrival_heading_quadrant) % 4
                ),
                "open_actions": self._normalized_actions(
                    list(item.open_actions)
                ),
                "chosen_action": str(item.chosen_action),
            }
            for item in working_memory.junctions
        ]

        candidate = RouteExperience(
            source_id=source_id,
            decision_sequence=list(
                working_memory.decision_sequence
            ),
            decision_contexts=contexts,
            outbound_distance_m=float(outbound_distance_m),
            total_trip_distance_m=float(total_trip_distance_m),
            energy_cost=energy_cost,
            resource_score=resource_score,
            success_count=1,
            confidence=0.50,
            last_trip_id=int(trip_id),
        )

        previous = self.routes.get(source_id)
        replaced = False
        if previous is None:
            self.routes[source_id] = candidate
            replaced = True
        else:
            previous.success_count += 1
            previous.last_trip_id = int(trip_id)
            previous.confidence = min(
                1.0,
                previous.confidence + 0.10,
            )

            # Keep the best validated successful decision sequence.
            if (
                candidate.outbound_distance_m
                < previous.outbound_distance_m - 1e-9
                or candidate.resource_score
                > previous.resource_score + 1e-9
            ):
                candidate.success_count = previous.success_count
                candidate.confidence = previous.confidence
                self.routes[source_id] = candidate
                replaced = True

        self.completed_trip_count += 1
        active = self.routes[source_id]
        update = {
            "trip_id": int(trip_id),
            "source_id": source_id,
            "success": True,
            "route_replaced": replaced,
            "candidate_outbound_distance_m": float(
                outbound_distance_m
            ),
            "best_outbound_distance_m": (
                active.outbound_distance_m
            ),
            "energy_cost": energy_cost,
            "resource_score": resource_score,
            "confidence": active.confidence,
            "decision_sequence": list(
                working_memory.decision_sequence
            ),
        }
        self.update_history.append(update)
        return update

    def record_failure(self, *, source_id: str, trip_id: int, reason: str) -> dict[str, Any]:
        """Temporarily reduce stale route confidence; never blacklist it."""
        route = self.routes.get(source_id)
        if route is not None:
            route.failure_count += 1
            route.confidence = max(0.10, route.confidence - 0.20)
        update = {"trip_id": int(trip_id), "source_id": source_id,
                  "success": False, "reason": str(reason),
                  "confidence": route.confidence if route is not None else 0.0}
        self.update_history.append(update)
        return update

    def snapshot(self) -> dict[str, Any]:
        return {
            "memory_type": "EXPERIENCE_MEMORY",
            "scope": "PERSISTENT_ACROSS_TRIPS",
            "biological_role": (
                "REMEMBER_SUCCESSFUL_DECISION_SEQUENCE_TO_FOOD"
            ),
            "world_map_created": False,
            "motor_command_replay_enabled": False,
            "completed_trip_count": self.completed_trip_count,
            "current_trip_id": self.current_trip_id,
            "routes": {
                key: asdict(value)
                for key, value in self.routes.items()
            },
            "update_history": list(self.update_history),
        }

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                self.snapshot(),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def save_updates_csv(self, path: Path) -> None:
        fields = [
            "trip_id",
            "source_id",
            "success",
            "reason",
            "route_replaced",
            "candidate_outbound_distance_m",
            "best_outbound_distance_m",
            "energy_cost",
            "resource_score",
            "confidence",
            "decision_sequence",
        ]
        with path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=fields,
            )
            writer.writeheader()
            for row in self.update_history:
                cooked = dict(row)
                cooked["decision_sequence"] = "|".join(
                    cooked.get("decision_sequence", [])
                )
                writer.writerow(cooked)
