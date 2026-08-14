"""Controlled resource-relocation acceptance test.

Pass criteria:
1. the active resource can move without recreating the sensor;
2. an unsuccessful old-route attempt lowers confidence but retains memory;
3. a later success restores confidence.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "swarm_simulate"))

from energy_sensor import EnergyEndpoint, RandomEndpointEnergySensor
from experience_memory import ExperienceMemory
from working_memory import JunctionRecord, WorkingMemory


def route_memory() -> WorkingMemory:
    memory = WorkingMemory()
    memory.start_route(x_m=1.0, y_m=1.0, theta_rad=0.0)
    memory.add_junction(JunctionRecord("D001", 0, "TURN_LEFT", "TEST", ["TURN_LEFT", "MOVE_FORWARD"], ["TURN_LEFT", "MOVE_FORWARD"], 0, 0))
    return memory


def main() -> None:
    sensor = RandomEndpointEnergySensor(
        endpoints=[EnergyEndpoint("E_MOVING", 2.0, 2.0), EnergyEndpoint("E_MOVED", 10.0, 10.0)],
        detection_radius_m=0.20, random_seed=1,
    )
    assert sensor.active_endpoint.endpoint_id == "E_MOVING"
    assert sensor.activate_endpoint("E_MOVED").x_m == 10.0

    experience = ExperienceMemory()
    memory = route_memory()
    experience.commit_success(source_id="E_MOVING", working_memory=memory, outbound_distance_m=2.0, total_trip_distance_m=4.0, trip_id=1)
    experience.record_failure(source_id="E_MOVING", trip_id=2, reason="Resource relocated")
    route = experience.routes["E_MOVING"]
    assert route.confidence == 0.30 and route.failure_count == 1 and route.decision_sequence
    experience.commit_success(source_id="E_MOVING", working_memory=memory, outbound_distance_m=2.0, total_trip_distance_m=4.0, trip_id=3)
    assert experience.routes["E_MOVING"].confidence == 0.40
    print("PASS: relocation changes active resource and preserves reversible adaptation")


if __name__ == "__main__":
    main()
