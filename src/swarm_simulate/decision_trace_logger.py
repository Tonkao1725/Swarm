from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


class ForagingTraceLogger:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self._decision_count = 0
        self._energy_count = 0
        self._return_count = 0
        self._recovery_count = 0
        self._debug_count = 0
        self._action_audit_count = 0
        self._trail_audit_count = 0
        self._stream_time_counts: dict[
            tuple[str, float], int
        ] = {}
        self._suppressed_repetitive_rows = 0
        self.final_result: dict[str, Any] = {}

        self._decision_file = (run_dir / "decision.csv").open(
            "w", newline="", encoding="utf-8"
        )
        self._energy_file = (run_dir / "energy.csv").open(
            "w", newline="", encoding="utf-8"
        )
        self._return_file = (run_dir / "return_navigation.csv").open(
            "w", newline="", encoding="utf-8"
        )
        self._recovery_file = (run_dir / "collision_recovery.csv").open(
            "w", newline="", encoding="utf-8"
        )
        self._debug_file = (run_dir / "navigation_debug.csv").open(
            "w", newline="", encoding="utf-8"
        )
        self._action_audit_file = (
            run_dir / "navigation_action_audit.csv"
        ).open("w", newline="", encoding="utf-8")
        self._trail_audit_file = (
            run_dir / "trail_audit.csv"
        ).open("w", newline="", encoding="utf-8")

        self._decision_writer = csv.DictWriter(
            self._decision_file,
            fieldnames=[
                "decision_index", "sim_time_s", "phase",
                "junction_key", "x_m", "y_m", "heading_deg",
                "trip_id", "decision_ordinal", "anchor_distance_m",
                "branch_visit_counts", "branch_global_directions",
                "left_m", "front_m", "right_m",
                "open_actions", "unvisited_actions",
                "chosen_action", "reason", "random_seed",
                "working_memory_route",
                "solar_left", "solar_center", "solar_right",
                "solar_max", "strongest_light_direction",
                "light_guidance_active",
            ],
        )
        self._energy_writer = csv.DictWriter(
            self._energy_file,
            fieldnames=[
                "sample_index", "sim_time_s", "phase",
                "x_m", "y_m", "detected", "endpoint_id",
                "distance_to_active_source_m", "signal_strength",
                "relative_bearing_deg", "inside_sensor_fov",
                "beam_hit_valid",
                "wall_distance_on_energy_ray_m",
                "line_of_sight_clear", "blocked_by_wall",
                "within_detection_radius",
                "acquisition_clearance_m",
                "solar_left", "solar_center", "solar_right",
                "solar_max", "solar_mean",
                "strongest_direction",
                "guidance_active",
                "collect_threshold_reached",
                "approach_active", "light_state",
                "light_path_factor",
            ],
        )
        self._return_writer = csv.DictWriter(
            self._return_file,
            fieldnames=[
                "return_index", "sim_time_s", "command",
                "value", "x_m", "y_m", "heading_deg",
            ],
        )
        self._recovery_writer = csv.DictWriter(
            self._recovery_file,
            fieldnames=[
                "recovery_index", "sim_time_s", "phase",
                "reason", "requested_distance_m",
                "actual_distance_m", "x_m", "y_m",
                "heading_deg", "working_memory_route",
            ],
        )


        self._action_audit_writer = csv.DictWriter(
            self._action_audit_file,
            fieldnames=[
                "audit_index", "sim_time_s", "stage",
                "junction_id", "x_m", "y_m",
                "heading_deg", "heading_quadrant",
                "left_m", "front_m", "right_m",
                "requested_action", "requested_global_direction",
                "requested_clearance_m", "open_actions",
                "safe_actions", "selected_action",
                "selected_global_direction",
                "action_rejected", "rejection_reason",
                "working_memory_route",
            ],
        )
        self._trail_audit_writer = csv.DictWriter(
            self._trail_audit_file,
            fieldnames=[
                "audit_index", "sim_time_s", "event",
                "x_m", "y_m", "previous_x_m", "previous_y_m",
                "displacement_m", "heading_deg", "note",
            ],
        )

        self._debug_writer = csv.DictWriter(
            self._debug_file,
            fieldnames=[
                "debug_index", "sim_time_s", "state", "x_m", "y_m",
                "heading_deg", "left_m", "front_m", "right_m",
                "previous_left_m", "previous_right_m",
                "opening_transition", "estimated_half_width_m",
                "centering_target_m", "nearest_junction",
                "nearest_junction_distance_m", "active_junction",
                "pending_redecision", "open_actions", "note",
            ],
        )

        self._decision_writer.writeheader()
        self._energy_writer.writeheader()
        self._return_writer.writeheader()
        self._recovery_writer.writeheader()
        self._debug_writer.writeheader()
        self._action_audit_writer.writeheader()
        self._trail_audit_writer.writeheader()

    def log_decision(self, row: dict[str, Any]) -> None:
        self._decision_count += 1
        self._decision_writer.writerow({
            "decision_index": self._decision_count,
            **row,
        })
        self._decision_file.flush()

    def _allow_log_row(
        self,
        stream: str,
        row: dict[str, Any],
        *,
        maximum_rows_per_sim_time: int = 100,
    ) -> bool:
        """
        Bound repeated rows at one simulation timestamp.

        Normal simulation advances time, so this has no effect on valid logs.
        It only prevents a zero-progress controller loop from generating
        hundreds of megabytes before the watchdog raises an exception.
        """
        sim_time = round(
            float(row.get("sim_time_s", -1.0)),
            6,
        )
        key = (stream, sim_time)
        count = self._stream_time_counts.get(key, 0)
        if count >= maximum_rows_per_sim_time:
            self._suppressed_repetitive_rows += 1
            return False
        self._stream_time_counts[key] = count + 1
        return True

    def log_energy(self, row: dict[str, Any]) -> None:
        if not self._allow_log_row("energy", row):
            return
        self._energy_count += 1
        self._energy_writer.writerow({
            "sample_index": self._energy_count,
            **row,
        })
        self._energy_file.flush()

    def log_return(self, row: dict[str, Any]) -> None:
        self._return_count += 1
        self._return_writer.writerow({
            "return_index": self._return_count,
            **row,
        })
        self._return_file.flush()

    def log_recovery(self, row: dict[str, Any]) -> None:
        self._recovery_count += 1
        self._recovery_writer.writerow({
            "recovery_index": self._recovery_count,
            **row,
        })
        self._recovery_file.flush()

    def log_debug(self, row: dict[str, Any]) -> None:
        if not self._allow_log_row("debug", row):
            return
        self._debug_count += 1
        self._debug_writer.writerow({"debug_index": self._debug_count, **row})
        self._debug_file.flush()

    def log_action_audit(self, row: dict[str, Any]) -> None:
        self._action_audit_count += 1
        self._action_audit_writer.writerow({
            "audit_index": self._action_audit_count,
            **row,
        })
        self._action_audit_file.flush()

    def log_trail_audit(self, row: dict[str, Any]) -> None:
        self._trail_audit_count += 1
        self._trail_audit_writer.writerow({
            "audit_index": self._trail_audit_count,
            **row,
        })
        self._trail_audit_file.flush()

    def set_result(self, result: dict[str, Any]) -> None:
        self.final_result = result

    def close(self) -> None:
        self._decision_file.close()
        self._energy_file.close()
        self._return_file.close()
        self._recovery_file.close()
        self._debug_file.close()
        self._action_audit_file.close()
        self._trail_audit_file.close()

        summary = {
            "decision_count": self._decision_count,
            "energy_samples": self._energy_count,
            "return_command_count": self._return_count,
            "collision_recovery_count": self._recovery_count,
            "navigation_debug_count": self._debug_count,
            "navigation_action_audit_count": (
                self._action_audit_count
            ),
            "trail_audit_count": self._trail_audit_count,
            "suppressed_repetitive_log_rows": (
                self._suppressed_repetitive_rows
            ),
            **self.final_result,
        }
        (self.run_dir / "foraging_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
