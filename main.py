from __future__ import annotations

from pathlib import Path
import os
import time

import irsim

from autonomous_foraging_controller import (
    AutonomousForagingConfig,
    AutonomousForagingController,
)
from decision_trace_logger import ForagingTraceLogger
from encoder_model import EncoderConfig, EncoderSimulator
from energy_sensor import (
    EnergyEndpoint,
    RandomEndpointEnergySensor,
)
from experience_memory import ExperienceMemory
from experiment_modes import (
    all_mode_snapshots,
    resolve_experiment_mode,
)
from imperfection_model import (
    ControlledImperfectionModel,
    ImperfectionConfig,
)
from irsim_backend import IRSimBackend
from irsim_range_sensor import IRSimDirectionalRangeSensor
from motion_controller import MotionConfig, MotionController
from motion_types import RobotPose
from odometry import DifferentialDriveOdometry
from result_logger import RunLogger
from wheel_model import (
    DifferentialDriveConfig,
    DifferentialDriveModel,
)
from working_memory import WorkingMemory
from world_builder import build_runtime_world
from sim_hud import SimulationHUD


PROJECT_ROOT = Path(__file__).resolve().parent
BASE_WORLD_FILE = PROJECT_ROOT / "robot_world.yaml"
RUNTIME_WORLD_FILE = (
    PROJECT_ROOT / "robot_world_runtime.yaml"
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def main() -> int:
    motion_config = MotionConfig(
        linear_speed_mps=0.25,
        angular_speed_radps=0.90,
        linear_acceleration_mps2=0.35,
        angular_acceleration_radps2=1.80,
        stop_duration_s=0.20,
    )
    drive_config = DifferentialDriveConfig(
        wheel_radius_m=0.0325,
        wheel_track_m=0.1400,
        max_wheel_angular_speed_radps=20.0,
    )
    encoder_config = EncoderConfig(
        ticks_per_revolution=600
    )
    imperfection_config = ImperfectionConfig(
        enabled=False
    )

    seed = int(
        os.environ.get(
            "FORAGING_SEED",
            str(time.time_ns() % 2_147_483_647),
        )
    )
    render_enabled = _env_bool("IRSIM_RENDER", True)
    experiment_mode = resolve_experiment_mode()
    trip_count = int(
        os.environ.get("FORAGING_TRIPS", "5")
    )
    if trip_count < 1:
        raise ValueError(
            "FORAGING_TRIPS must be at least 1"
        )
    batch_results_root_raw = os.environ.get("SWARM_RESULTS_ROOT", "").strip()
    batch_results_root = (
        Path(batch_results_root_raw).resolve()
        if batch_results_root_raw
        else PROJECT_ROOT / "results" / experiment_mode.mode.value
    )
    batch_run_id = os.environ.get("SWARM_RUN_ID", "").strip() or None
    exploration_config = AutonomousForagingConfig(
        movement_step_m=0.10,
        # The ±20° front beams can clear a wall corner while the 0.25 m
        # radius body still clips it.  A 0.70 m stop distance leaves the
        # measured 0.12 m corner margin seen necessary in regression seed
        # 2118334751, while remaining below the 1.0 m corridor half-width.
        wall_stop_distance_m=0.70,
        endpoint_tolerance_m=0.025,
        open_threshold_m=0.95,
        minimum_centering_m=0.18,
        maximum_centering_m=0.60,
        junction_cluster_radius_m=0.48,
        junction_exit_radius_m=0.82,
        minimum_progress_m=0.015,
        movement_error_tolerance_m=0.02,
        home_tolerance_m=0.08,
        maximum_distance_m=320.0,
        random_seed=seed,
        trip_count=trip_count,
        memory_enabled=experiment_mode.memory_enabled,
        route_experience_enabled=experiment_mode.route_experience_enabled,
    )

    # Controlled experiment: one fixed source at the upper-right corner.
    # Keeping the source constant isolates learning effects across trips.
    endpoints = (
        EnergyEndpoint("E_FIXED_NE", 11.875, 11.875),
    )
    # Fixed-source pickup zone.
    # The Energy marker is display-only and does not collide with the robot,
    # so the robot can reach its centre. Use a small near-field radius instead
    # of the previous 0.80 m radius. This prevents collection from more than a
    # metre away while ensuring a 0.10 m motion step cannot skip the source.
    energy_detection_radius_m = 0.20

    energy_sensor = RandomEndpointEnergySensor(
        endpoints=endpoints,
        detection_radius_m=energy_detection_radius_m,
        random_seed=seed ^ 0x5A17,
        line_of_sight_margin_m=0.03,
        visible_marker_radius_m=0.12,
        # Memory-only phase: any reliable non-zero directional light
        # activates guidance immediately. AIH-based explore/exploit gating is
        # intentionally not applied yet.
        guidance_threshold=0.001,
        collect_threshold=0.90,
        light_range_scale_m=4.50,
        blocked_light_factor=0.0,
        diffuse_guidance_threshold=0.003,
        maximum_diffuse_guidance_distance_m=7.0,
        angular_exponent=2.0,
        ambient_light=0.0,
    )

    runtime_world_file = (
        PROJECT_ROOT / f"robot_world_runtime_{batch_run_id}.yaml"
        if batch_run_id
        else RUNTIME_WORLD_FILE
    )
    build_runtime_world(
        base_world_path=BASE_WORLD_FILE,
        runtime_world_path=runtime_world_file,
        active_energy=energy_sensor.active_endpoint,
    )

    run_config = {
        "test_name": "five_mode_collective_foraging_v1",
        "experiment_mode": experiment_mode.snapshot(),
        "experiment_mode_matrix": all_mode_snapshots(),
        "experiment_mode_environment_variable": "SWARM_EXPERIMENT_MODE",
        "trip_count": trip_count,
        "trip_control_environment_variable": (
            "FORAGING_TRIPS"
        ),
        "energy_reselection_between_trips": False,
        "fixed_energy_source": True,
        "working_memory_reset_each_trip": True,
        "experience_memory_persists_across_trips": True,
        "world_map_created": False,
        "navigation_model": "RAT_INSPIRED_DECISION_MEMORY_WITH_BREADCRUMB_PRUNING",
        "nest_energy_accumulates": True,
        "base_world_file": BASE_WORLD_FILE.name,
        "runtime_world_file": runtime_world_file.name,
        "decision_route_predefined": False,
        "decision_policy": (
            "STRICT_LOS_LIGHT_WHEN_VISIBLE; "
            "BOUNDED_EXPERIENCE_BIAS_WHEN_CONTEXT_MATCHES; "
            "OTHERWISE_RAT_WEIGHTED_WIN_SHIFT"
        ),
        "energy_location": "FIXED_UPPER_RIGHT",
        "energy_source_control": {
            "mode": "FIXED_CONTROLLED_SOURCE",
            "endpoint_id": energy_sensor.active_endpoint.endpoint_id,
            "x_m": energy_sensor.active_endpoint.x_m,
            "y_m": energy_sensor.active_endpoint.y_m,
            "reason": "Hold environment constant while measuring learning",
        },
        "maze_design": {
            "name": "compact_complex_perfect_maze_v2",
            "generation_seed": 10777,
            "topology": "CONNECTED_ACYCLIC_TREE",
            "logical_cells": [5, 5],
            "physical_grid": [11, 11],
            "cell_size_m": 1.25,
            "corridor_width_m": 1.25,
            "world_width_m": 13.75,
            "world_height_m": 13.75,
            "logical_junction_count": 6,
            "dead_end_count": 7,
            "energy_dead_end_count": 6,
            "multi_robot_spatial_preparation": True,
            "graph_loops_enabled": False,
        },
        "energy_detection_radius_m": (
            energy_sensor.detection_radius_m
        ),
        "solar_light_field": {
            "sensor_layout": [
                "LEFT_+90_DEG",
                "CENTER_0_DEG",
                "RIGHT_-90_DEG",
            ],
            "guidance_threshold": (
                energy_sensor.guidance_threshold
            ),
            "collect_threshold": (
                energy_sensor.collect_threshold
            ),
            "light_range_scale_m": (
                energy_sensor.light_range_scale_m
            ),
            "blocked_light_factor": (
                energy_sensor.blocked_light_factor
            ),
            "diffuse_guidance_threshold": (
                energy_sensor.diffuse_guidance_threshold
            ),
            "maximum_diffuse_guidance_distance_m": (
                energy_sensor.maximum_diffuse_guidance_distance_m
            ),
            "angular_exponent": (
                energy_sensor.angular_exponent
            ),
            "decision_mode": "DETERMINISTIC_STRONGEST_OPEN_DIRECTION",
            "optical_model": "STRICT_LINE_OF_SIGHT",
            "guidance_requires_line_of_sight": True,
            "wall_blocked_solar_values_forced_to_zero": True,
            "diffuse_light_enabled": False,
            "collection_mode": "NEAR_FIELD_DISTANCE_0_20_M",
        },
        "energy_minimum_reachable_center_distance_m": (
            exploration_config.wall_stop_distance_m
            + energy_sensor.visible_marker_radius_m
        ),
        "energy_marker": {
            "visible": True,
            "shape": "yellow_circle",
            "radius_m": 0.12,
            "endpoint_id": (
                energy_sensor.active_endpoint.endpoint_id
            ),
            "x_m": energy_sensor.active_endpoint.x_m,
            "y_m": energy_sensor.active_endpoint.y_m,
        },
        "energy_random_seed": seed ^ 0x5A17,
        "decision_random_seed": seed,
        "render_enabled": render_enabled,
        "batch_run_id": batch_run_id,
        "motion": vars(motion_config),
        "drive": vars(drive_config),
        "encoder": vars(encoder_config),
        "imperfection": vars(imperfection_config),
        "exploration": vars(exploration_config),
        "endpoint_ids": [
            item.endpoint_id for item in endpoints
        ],
        "fixes": [
            "SPATIAL_JUNCTION_CLUSTERING",
            "ONE_DECISION_PER_JUNCTION_ENTRY",
            "FORCED_CORNER_NOT_COUNTED_AS_JUNCTION",
            "FLOATING_POINT_ENDPOINT_TOLERANCE",
            "VISIBLE_FIXED_ENERGY_MARKER",
            "REACHABLE_ENERGY_PICKUP_RADIUS",
            "ENERGY_COLLECTED_STATE_BEFORE_RETURN",
            "ENERGY_LINE_OF_SIGHT_REQUIRED",
            "ACTUAL_TRANSLATION_PROGRESS_VALIDATION",
            "COLLISION_BRANCH_RECOVERY",
            "SENSOR_CENTERED_JUNCTION_FROM_OPENING_EDGE",
            "REVERSE_DRIVE_BACKTRACK_WITHOUT_ENDPOINT_180_TURN",
            "FIRST_LIDAR_FRAME_WARMUP",
            "BACKTRACK_RETURNS_TO_KNOWN_JUNCTION_WITHOUT_RECENTER",
            "ENERGY_MARKER_RADIUS_COMPENSATED_IN_LOS",
            "LIDAR_FOV_SEPARATED_FROM_BEAM_HIT_VALID",
            "NAVIGATION_DEBUG_TRACE",
            "MOTION_EARLY_COLLISION_ABORT",
            "LIVE_STATUS_HUD",
            "NON_PHYSICAL_ENERGY_MARKER",
            "ENERGY_MARKER_HIDDEN_AFTER_CARRY",
            "THREE_SOLAR_CELL_LIGHT_FIELD",
            "STRICT_LOS_SOLAR_FIELD",
            "ZERO_SOLAR_SIGNAL_BEHIND_WALL",
            "NO_DIFFUSE_LIGHT_GUIDANCE",
            "DETERMINISTIC_STRONGEST_LIGHT_FOLLOWING",
            "COLLECT_BY_SOLAR_INTENSITY_THRESHOLD",
            "SEPARATE_LIGHT_GUIDANCE_AND_COLLECTION",
            "MULTI_ROBOT_READY_1_8M_CORRIDORS",
            "THROTTLED_RENDER_AND_HUD",
            "BUFFERED_STEP_LOG_FLUSH",
            "LIVE_ROBOT_TRAIL",
            "HUD_SEED_AND_ENERGY_ENDPOINT",
            "CENTERED_FORCED_CORNER_HANDLING",
            "COMPACT_COMPLEX_PERFECT_MAZE_V2",
            "FIXED_UPPER_RIGHT_ENERGY_SOURCE",
            "MULTI_ROBOT_1_25M_CORRIDORS",
            "FRESH_SENSOR_ACTION_SAFETY_GATE",
            "PHYSICS_TIME_TRAIL_SAMPLING",
            "FALSE_DIAGONAL_TRAIL_BREAK",
            "NAVIGATION_ACTION_AUDIT_LOG",
            "SIDE_FACING_SOLAR_CELL_GEOMETRY",
            "IMMEDIATE_DIRECT_LIGHT_GUIDANCE",
            "LIGHT_TURN_RANGE_SAFETY_GATE",
            "LIDAR_EDGE_FOV_TOLERANCE",
            "NEAR_FIELD_ENERGY_COLLECTION",
            "COLLECTION_INDEPENDENT_OF_SOLAR_BEARING",
            "PER_TRIP_TRAIL_COLOR",
            "MULTI_TRIP_FORAGING_LOOP",
            "SAME_SOURCE_ACROSS_TRIPS",
            "PER_TRIP_WORKING_MEMORY_ARTIFACTS",
            "PER_TRIP_EXPERIENCE_MEMORY_ARTIFACTS",
            "WORKING_EXPERIENCE_MEMORY_SEPARATION",
            "RAT_INSPIRED_DECISION_MEMORY_WITH_BREADCRUMB_PRUNING",
            "NO_SLAM_NO_WORLD_GRAPH",
            "SUCCESSFUL_ROUTE_EXPERIENCE_ONLY",
            "ROUTE_DISTANCE_ENERGY_COST_RESOURCE_SCORE",
            "NEST_ENERGY_ACCUMULATION",
        ],
    }

    env = backend = logger = trace = hud = None
    memory = WorkingMemory()
    experience = ExperienceMemory()
    if not experiment_mode.memory_enabled:
        experience.clear_persistent_routes()

    try:
        env = irsim.make(str(runtime_world_file))
        logger = RunLogger(
            PROJECT_ROOT,
            env,
            run_config,
            results_root=batch_results_root,
            run_id=batch_run_id,
        )

        initial = env.get_robot_state().reshape(-1)
        initial_pose = RobotPose(
            float(initial[0]),
            float(initial[1]),
            float(initial[2]),
        )
        wheel_model = DifferentialDriveModel(
            drive_config
        )
        hud = SimulationHUD(
            energy_x_m=energy_sensor.active_endpoint.x_m,
            energy_y_m=energy_sensor.active_endpoint.y_m,
            energy_radius_m=energy_sensor.visible_marker_radius_m,
            decision_seed=seed,
            energy_endpoint_id=(
                energy_sensor.active_endpoint.endpoint_id
            ),
            enabled=render_enabled,
            trail_minimum_spacing_m=0.04,
            trail_maximum_points=12000,
        )

        backend = IRSimBackend(
            env=env,
            wheel_model=wheel_model,
            imperfection_model=(
                ControlledImperfectionModel(
                    wheel_model,
                    imperfection_config,
                )
            ),
            encoder_simulator=EncoderSimulator(
                encoder_config
            ),
            odometry=DifferentialDriveOdometry(
                drive_config,
                encoder_config.ticks_per_revolution,
                initial_pose,
            ),
            on_step=logger.log_step,
            render_enabled=render_enabled,
            render_overlay=hud.render,
            render_every_n_steps=3,
        )
        motion = MotionController(
            backend=backend,
            config=motion_config,
            on_command_complete=(
                logger.log_movement
            ),
        )
        range_sensor = IRSimDirectionalRangeSensor(
            env=env,
            range_max_m=5.0,
        )
        trace = ForagingTraceLogger(
            logger.run_dir
        )

        controller = AutonomousForagingController(
            motion=motion,
            sensor=range_sensor,
            energy_sensor=energy_sensor,
            trace=trace,
            memory=memory,
            experience=experience,
            experiment_mode=experiment_mode,
            config=exploration_config,
            hud=hud,
        )

        logger.snapshot_sources([
            PROJECT_ROOT / name
            for name in [
                "main.py",
                "robot_world.yaml",
                runtime_world_file.name,
                "world_builder.py",
                "sim_hud.py",
                "autonomous_foraging_controller.py",
                "experience_memory.py",
                "experiment_modes.py",
                "energy_sensor.py",
                "working_memory.py",
                "decision_trace_logger.py",
                "motion_controller.py",
                "motion_types.py",
                "motion_profile.py",
                "wheel_model.py",
                "imperfection_model.py",
                "encoder_model.py",
                "odometry.py",
                "irsim_backend.py",
                "irsim_range_sensor.py",
                "sensor_types.py",
                "result_logger.py",
            ]
        ])

        backend.render()
        logger.log_event(
            "FORAGING_START",
            (
                f"decision_seed={seed}; "
                "route_predefined=false; "
                f"visible_energy_marker="
                f"{energy_sensor.active_endpoint.endpoint_id}"
            ),
        )

        result = controller.run()
        memory.save(logger.run_dir / "working_memory.json")
        experience.save(logger.run_dir / "experience_memory.json")
        experience.save_updates_csv(
            logger.run_dir / "experience_updates.csv"
        )
        logger.log_event(
            "MULTI_TRIP_EXPERIMENT_COMPLETE",
            (
                f"fixed_source={result['fixed_source_id']}; "
                f"completed={result['completed_trip_count']}/"
                f"{result['requested_trip_count']}; "
                f"nest_energy={result['nest_energy_units']}; "
                f"status={result['status']}"
            ),
        )
        if render_enabled:
            logger.save_final_figure()
        logger.mark_success()

        print("SUCCESS: Multi-trip experiment completed.")
        print(f"Experiment mode: {experiment_mode.mode.value}")
        print(f"Decision seed: {seed}")
        print(
            "Fixed Energy source: "
            f"{result['fixed_source_id']} at upper-right"
        )
        print(
            f"Trips: {result['completed_trip_count']}/"
            f"{result['requested_trip_count']}"
        )
        print(f"Nest Energy: {result['nest_energy_units']}")
        print(logger.run_dir)
        return 0

    except Exception as exc:
        if logger is not None:
            memory.save(
                logger.run_dir / "working_memory.json"
            )
            if "controller" in locals():
                experience.save(
                    logger.run_dir / "experience_memory.json"
                )
                experience.save_updates_csv(
                    logger.run_dir / "experience_updates.csv"
                )
            logger.mark_failure(exc)
            if render_enabled:
                logger.save_final_figure()
            print("FAILED: Diagnostics saved to:")
            print(logger.run_dir)
        print(f"{type(exc).__name__}: {exc}")
        return 1

    finally:
        if trace is not None:
            trace.close()
        if logger is not None:
            logger.close()
        if backend is not None:
            backend.close()
        elif env is not None:
            env.end()

        if batch_run_id and runtime_world_file.exists():
            try:
                runtime_world_file.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
