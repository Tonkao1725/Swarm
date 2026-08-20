"""Passive common-metric aggregation for any Condition run directory.

Usage: python scripts/aggregate_common_metrics.py <runs_root> <output_dir>
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def f(value: str | float | int | None) -> float:
    return float(value or 0.0)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: aggregate_common_metrics.py <runs_root> <output_dir>")
    root, output = Path(sys.argv[1]), Path(sys.argv[2])
    output.mkdir(parents=True, exist_ok=True)
    research, scouts, episodes, returns, energy, funnel, coverage, trips, rates, repetition = ([] for _ in range(10))
    resource_utilization: list[dict] = []

    for run_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        summary_path = run_dir / "swarm_summary.json"
        if not summary_path.exists():
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        run_id = run_dir.name
        metadata_path = run_dir / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
        seed = metadata.get("configuration", {}).get("decision_random_seed", run_id)
        duration = f(summary.get("simulation_time_s"))
        events = read_csv(run_dir / "swarm_events.csv")
        trajectory = read_csv(run_dir / "swarm_trajectory.csv")
        event_counts = Counter(row["event"] for row in events)
        for row in events:
            if row["event"] in {"RESOURCE_LIGHT_DETECTED", "HARVEST_COMPLETE"}:
                resource_id = row["detail"].split(";")[0].replace("resource_id=", "")
                resource_utilization.append({"run_id": run_id, "seed": seed, "scout_id": row["scout_id"], "trip_id": row["trip_id"], "resource_id": resource_id, "event": row["event"], "sim_time_s": row["sim_time_s"], "detail": row["detail"]})
        research.append({"run_id": run_id, "seed": seed, "engineering_status": summary.get("engineering_status"), "experimental_validity": summary.get("experimental_validity"), "mission_outcome": summary.get("mission_outcome"), "termination_reason": summary.get("termination_reason"), "actual_runtime_s": duration, "gross_delivered_energy": summary.get("gross_delivered_energy"), "total_robot_nest_withdrawal": summary.get("total_robot_nest_withdrawal"), "net_nest_energy": summary.get("net_nest_energy"), "nest_energy_target": summary.get("nest_energy_target"), "target_reached": summary.get("target_reached"), "target_reached_time_s": summary.get("target_reached_time_s"), "resource_detections": event_counts["RESOURCE_LIGHT_DETECTED"], "harvest_completions": event_counts["HARVEST_COMPLETE"], "deliveries": event_counts["DELIVER"]})
        rates.append({"run_id": run_id, "seed": seed, "actual_runtime_s": duration, "deliveries_per_1000s": 1000 * event_counts["DELIVER"] / duration if duration else 0.0, "net_nest_energy_gain_per_1000s": 1000 * f(summary.get("net_nest_energy")) / duration if duration else 0.0})
        energy.extend(read_csv(run_dir / "nest_energy_timeline.csv"))

        by_scout: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in trajectory:
            by_scout[row["scout_id"]].append(row)
        # Condition 1 uses one common Nest cue and one common physical nest.
        homes = defaultdict(lambda: (1.0, 1.0))
        contributing = 0
        for item in summary.get("scouts", []):
            sid = str(item["scout_id"])
            rows = by_scout[sid]
            cells, revisits, repeated_decisions = set(), 0, 0
            previous = None
            for row in rows:
                cell = (math.floor(f(row["x_m"]) / 0.5), math.floor(f(row["y_m"]) / 0.5))
                if cell in cells:
                    revisits += 1
                cells.add(cell)
                if previous and previous[0] == cell and previous[1] == row["action"]:
                    repeated_decisions += 1
                previous = (cell, row["action"])
            active_time = f(rows[-1]["sim_time_s"]) - f(rows[0]["sim_time_s"]) if len(rows) > 1 else 0.0
            distance = f(item.get("distance_m"))
            scoped_events = [row["event"] for row in events if row["scout_id"] == sid]
            scouts.append({"run_id": run_id, "seed": seed, "scout_id": sid, "behavioral_outcome": item.get("behavioral_outcome"), "phase_at_termination": item.get("phase_at_termination"), "started_cycle_count": item.get("started_trip_count"), "completed_cycle_count": item.get("completed_cycle_count", item.get("completed_trip_count")), "resource_found_count": item.get("resource_found_count"), "collection_count": item.get("collection_count"), "return_attempt_count": item.get("return_attempt_count"), "nest_reached_count": scoped_events.count("NEST_REACHED"), "delivery_count": item.get("delivery_count"), "internal_energy_final": item.get("internal_energy_final"), "internal_energy_min": item.get("internal_energy_min"), "nest_withdrawn_energy": item.get("nest_withdrawn_energy"), "depleted": item.get("depleted"), "total_distance_m": distance, "coverage_cells": len(cells), "actual_active_time_s": active_time, "contact_stalled": item.get("contact_stalled"), "persistent_stationary_turn_deadlock": item.get("persistent_stationary_turn_deadlock"), "wm_enabled": False, "em_enabled": False, "exchange_mode": "off", "aih_enabled": False})
            coverage.append({"run_id": run_id, "seed": seed, "scout_id": sid, "total_distance_m": distance, "coverage_cells": len(cells), "coverage_cells_per_meter": len(cells) / distance if distance else 0.0, "coverage_gain_per_minute": 60 * len(cells) / active_time if active_time else 0.0})
            trips.append({"run_id": run_id, "seed": seed, "scout_id": sid, "started_cycle_count": item.get("started_trip_count"), "completed_cycle_count": item.get("completed_cycle_count", item.get("completed_trip_count")), "resource_detection_count": scoped_events.count("RESOURCE_LIGHT_DETECTED"), "harvest_completion_count": scoped_events.count("HARVEST_COMPLETE"), "return_attempt_count": item.get("return_attempt_count"), "nest_reached_count": scoped_events.count("NEST_REACHED"), "delivery_count": item.get("delivery_count")})
            repetition.append({"run_id": run_id, "seed": seed, "scout_id": sid, "revisit_count": revisits, "repeated_decision_count": repeated_decisions, "local_cycle_episode_count": 0, "repeated_local_behavior_duration_s": 0.0})
            if f(item.get("delivery_count")) > 0:
                contributing += 1
        rates[-1]["contributing_scouts"] = contributing
        for sid, start in ((row["scout_id"], row) for row in events if row["event"] == "RETURN_HOME_START"):
            rows = [row for row in by_scout[sid] if f(row["sim_time_s"]) >= f(start["sim_time_s"])]
            if not rows:
                continue
            hx, hy = homes[sid]
            distances = [(f(row["sim_time_s"]), math.hypot(f(row["x_m"]) - hx, f(row["y_m"]) - hy)) for row in rows]
            minimum_t, minimum = min(distances, key=lambda item: item[1])
            delivered = any(row["event"] == "DELIVER" and row["scout_id"] == sid and row["trip_id"] == start["trip_id"] for row in events)
            reached = any(row["event"] == "NEST_REACHED" and row["scout_id"] == sid and row["trip_id"] == start["trip_id"] for row in events)
            end_time = next((row["sim_time_s"] for row in events if row["event"] == "DELIVER" and row["scout_id"] == sid and row["trip_id"] == start["trip_id"]), distances[-1][0])
            returns.append({"run_id": run_id, "seed": seed, "scout_id": sid, "trip_id": start["trip_id"], "return_start_time_s": start["sim_time_s"], "return_end_time_s": end_time, "return_duration_s": f(end_time) - f(start["sim_time_s"]), "start_distance_to_nest_m": distances[0][1], "minimum_distance_to_nest_m": minimum, "time_of_minimum_distance_s": minimum_t, "final_distance_to_nest_m": distances[-1][1], "distance_reduction_m": distances[0][1] - distances[-1][1], "relative_return_progress": (distances[0][1] - distances[-1][1]) / distances[0][1] if distances[0][1] else 0.0, "nest_reached": reached, "delivered": delivered, "return_status": "DELIVERED" if delivered else "RETURN_IN_PROGRESS_AT_HORIZON"})
        episode_events: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for row in events:
            if row["scout_id"] != "COLONY" and row["trip_id"]:
                episode_events[(row["scout_id"], row["trip_id"])].append(row)
        for (sid, trip_id), event_rows in episode_events.items():
            names = [row["event"] for row in event_rows]
            if "SCOUT_START" not in names and "NEXT_CYCLE_START" not in names and not any(name in names for name in ("RESOURCE_LIGHT_DETECTED", "HARVEST_COMPLETE", "RETURN_HOME_START", "NEST_REACHED", "DELIVER")):
                continue
            first_time = lambda event: next((row["sim_time_s"] for row in event_rows if row["event"] == event), "")
            trajectory_rows = [
                row for row in by_scout[sid] if row.get("trip_id") == trip_id
            ]
            trip_start = first_time("SCOUT_START") or first_time("NEXT_CYCLE_START") or event_rows[0]["sim_time_s"]
            delivered = "DELIVER" in names
            if delivered:
                status = "DELIVERED"
            elif "RETURN_HOME_START" in names:
                status = "RETURN_IN_PROGRESS_AT_HORIZON"
            elif "HARVEST_COMPLETE" in names:
                status = "HARVESTED_NOT_RETURNED_AT_HORIZON"
            elif "RESOURCE_LIGHT_DETECTED" in names:
                status = "RESOURCE_DETECTED_NOT_HARVESTED_AT_HORIZON"
            else:
                status = "RESOURCE_NOT_FOUND_AT_HORIZON"
            episodes.append({
                "run_id": run_id, "seed": seed, "scout_id": sid, "trip_id": trip_id,
                "trip_start_time_s": trip_start,
                "resource_detected": "RESOURCE_LIGHT_DETECTED" in names,
                "resource_detected_time_s": first_time("RESOURCE_LIGHT_DETECTED"),
                "harvest_completed": "HARVEST_COMPLETE" in names,
                "harvest_complete_time_s": first_time("HARVEST_COMPLETE"),
                "return_started": "RETURN_HOME_START" in names,
                "return_start_time_s": first_time("RETURN_HOME_START"),
                "nest_reached": "NEST_REACHED" in names,
                "nest_reached_time_s": first_time("NEST_REACHED"),
                "delivered": delivered,
                "delivery_time_s": first_time("DELIVER"),
                "episode_status": status,
                "episode_end_time_s": (first_time("DELIVER") if delivered else (trajectory_rows[-1]["sim_time_s"] if trajectory_rows else duration)),
                "trip_distance_m": (trajectory_rows[-1]["trip_distance_m"] if trajectory_rows else 0.0),
                "phase_at_episode_end": (trajectory_rows[-1]["phase"] if trajectory_rows else "NOT_OBSERVED"),
                "actual_episode_duration_s": f(first_time("DELIVER") if delivered else (trajectory_rows[-1]["sim_time_s"] if trajectory_rows else duration)) - f(trip_start),
            })
            funnel.append({"run_id": run_id, "seed": seed, "scout_id": sid, "cycle_id": trip_id, "cycle_started": int("SCOUT_START" in names or "NEXT_CYCLE_START" in names), "resource_detected": int("RESOURCE_LIGHT_DETECTED" in names), "harvest_completed": int("HARVEST_COMPLETE" in names), "return_started": int("RETURN_HOME_START" in names), "nest_reached": int("NEST_REACHED" in names), "delivered": int("DELIVER" in names)})

    specs = [("research_summary.csv", research), ("scout_summary.csv", scouts), ("foraging_episode_summary.csv", episodes), ("return_episode_summary.csv", returns), ("nest_energy_timeline.csv", energy), ("outcome_funnel_by_episode.csv", funnel), ("coverage_distance_by_scout.csv", coverage), ("trip_delivery_by_scout.csv", trips), ("foraging_rate_by_run.csv", rates), ("repetition_diagnostics.csv", repetition), ("resource_utilization_by_source.csv", resource_utilization)]
    for name, rows in specs:
        write_csv(output / name, rows, list(rows[0]) if rows else [])
    (output / "baseline_research_summary.json").write_text(json.dumps({"run_count": len(research), "valid_run_count": sum(row["experimental_validity"] == "VALID" for row in research), "mission_success_count": sum(row["mission_outcome"] == "MISSION_SUCCESS" for row in research)}, indent=2), encoding="utf-8")
    definitions = PROJECT_ROOT / "docs" / "metric_definitions.json"
    (output / "metric_definitions.json").write_text(
        definitions.read_text(encoding="utf-8"), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
