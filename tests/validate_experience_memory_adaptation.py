"""Validate reversible Experience Memory adaptation without a world map."""

from pathlib import Path
import sys

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src" / "swarm_simulate"),
)

from experience_memory import ExperienceMemory
from working_memory import JunctionRecord, WorkingMemory


def successful_memory() -> WorkingMemory:
    memory = WorkingMemory()
    memory.start_route(x_m=1.0, y_m=1.0, theta_rad=0.0)
    memory.add_junction(
        JunctionRecord(
            decision_point_key="D001",
            arrival_heading_quadrant=0,
            chosen_action="TURN_LEFT",
            reason="TEST",
            open_actions=["TURN_LEFT", "MOVE_FORWARD"],
            candidate_actions=["TURN_LEFT", "MOVE_FORWARD"],
            path_index_before_decision=0,
            decision_ordinal=0,
        )
    )
    return memory


def main() -> None:
    experience = ExperienceMemory()
    memory = successful_memory()
    experience.commit_success(
        source_id="E_TEST",
        working_memory=memory,
        outbound_distance_m=2.0,
        total_trip_distance_m=4.0,
        trip_id=1,
    )
    route = experience.routes["E_TEST"]
    assert route.confidence == 0.50

    experience.record_failure(
        source_id="E_TEST",
        trip_id=2,
        reason="Energy source not found",
    )
    route = experience.routes["E_TEST"]
    assert route.failure_count == 1
    assert route.confidence == 0.30
    assert route.decision_sequence == ["TURN_LEFT"]

    experience.commit_success(
        source_id="E_TEST",
        working_memory=memory,
        outbound_distance_m=2.0,
        total_trip_distance_m=4.0,
        trip_id=3,
    )
    route = experience.routes["E_TEST"]
    assert route.failure_count == 1
    assert route.confidence == 0.40
    print("PASS: Experience Memory failure penalty is reversible")


if __name__ == "__main__":
    main()
