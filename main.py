from __future__ import annotations

from pathlib import Path
import json
import os
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PROJECT_ROOT / "src" / "swarm_simulate"
sys.path.insert(0, str(SOURCE_ROOT))

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
from swarm_baseline import BaselineSwarmRunner


BASE_WORLD_FILE = PROJECT_ROOT / "config" / "robot_world.yaml"
RUNTIME_WORLD_FILE = (
    PROJECT_ROOT / "config" / "robot_world_runtime.yaml"
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
    fast_headless_research_mode = _env_bool(
        "FAST_HEADLESS_RESEARCH_MODE", False
    )
    # Fast headless mode changes wall-clock overhead only.  It never changes
    # dt, command cadence, physics, sensor reads, RNG, or simulated horizon.
    render_enabled = (
        False if fast_headless_research_mode else _env_bool("IRSIM_RENDER", True)
    )
    experiment_mode = resolve_experiment_mode()
    trip_count = int(
        os.environ.get("FORAGING_TRIPS", "5")
    )
    if trip_count < 1:
        raise ValueError(
            "FORAGING_TRIPS must be at least 1"
        )
    scout_count = int(os.environ.get("SWARM_SCOUT_COUNT", "1"))
    swarm_duration_s = float(os.environ.get("SWARM_SIM_DURATION_S", "300"))
    swarm_mission_mode = os.environ.get("SWARM_MISSION_MODE", "trip_limited").strip().lower()
    nest_energy_target_raw = os.environ.get("NEST_ENERGY_TARGET", "").strip()
    nest_energy_target = int(nest_energy_target_raw) if nest_energy_target_raw else None
    if swarm_mission_mode not in {"research", "trip_limited"}:
        raise ValueError("SWARM_MISSION_MODE must be 'research' or 'trip_limited'")
    if swarm_mission_mode == "research" and (nest_energy_target is None or nest_energy_target < 1):
        raise ValueError("Research mission mode requires NEST_ENERGY_TARGET >= 1")
    if scout_count < 1 or scout_count > 4:
        raise ValueError("SWARM_SCOUT_COUNT must be between 1 and 4")
    if swarm_duration_s <= 0.0:
        raise ValueError("SWARM_SIM_DURATION_S must be greater than 0")
    if scout_count > 1 and experiment_mode.mode.value != "baseline":
        raise ValueError("Multi-Scout runs currently require SWARM_EXPERIMENT_MODE=baseline")
    batch_results_root_raw = os.environ.get("SWARM_RESULTS_ROOT", "").strip()
    batch_results_root = (
        Path(batch_results_root_raw).resolve()
        if batch_results_root_raw
        else PROJECT_ROOT / "results" / experiment_mode.mode.value
    )
    batch_run_id = os.environ.get("SWARM_RUN_ID", "").strip() or None
    # Research-batch provenance is supplied by the immutable freeze procedure.
    # It is metadata only and is never read by a controller or sensor.
    freeze_commit = os.environ.get("SWARM_FREEZE_COMMIT", "").strip() or "UNSPECIFIED"
    freeze_tag = os.environ.get("SWARM_FREEZE_TAG", "").strip() or "UNSPECIFIED"
    canonical_seed_set_sha256 = os.environ.get(
        "SWARM_CANONICAL_SEED_SET_SHA256", ""
    ).strip() or "UNSPECIFIED"
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
        # A successful current-project route should be a strong but still
        # bounded preference when a later Trip faces the same local choice.
        # It remains subordinate to the win-shift eligibility filter.
        experience_action_bonus=10.0,
    )

    resource_config_path = PROJECT_ROOT / "config" / "resource_harvesting_config.json"
    resource_config = json.loads(resource_config_path.read_text(encoding="utf-8"))
    # Common infrastructure: persistent sources. Their pilot-normalized
    # harvest rates are environment properties, never controller inputs.
    endpoints = tuple(
        EnergyEndpoint(
            item["resource_id"], float(item["x_m"]), float(item["y_m"]),
            float(item["relative_harvest_rate"]),
        )
        for item in resource_config["sources"]
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
        PROJECT_ROOT / "config" / f"robot_world_runtime_{batch_run_id}.yaml"
        if batch_run_id
        else RUNTIME_WORLD_FILE
    )
    build_runtime_world(
        base_world_path=BASE_WORLD_FILE,
        runtime_world_path=runtime_world_file,
        active_energy=energy_sensor.active_endpoint,
    )

    # Startup proof: make the active behavioral-testbed configuration visible
    # in every terminal log so a mixed spatial scale cannot be mistaken for a
    # valid research run.
    print(
        "STARTUP_CONFIG "
        "arena=14x14m; robot_radius=0.25m; wall_thickness=0.18m; "
        f"scouts={scout_count}; mission_mode={swarm_mission_mode}; "
        f"nest_energy_target={nest_energy_target}; horizon_s={swarm_duration_s}; "
        f"WM={experiment_mode.memory_enabled}; "
        f"EM={experiment_mode.experience_memory_enabled}; "
        "Exchange=False; AIH=False; "
        f"world_config={BASE_WORLD_FILE}; runner=BaselineSwarmRunner; "
        f"fast_headless={fast_headless_research_mode}; "
        f"git_commit={freeze_commit}; git_tag={freeze_tag}"
    )

    run_config = {
        "test_name": "controlled_behavioral_foraging_environment_v1",
        "mission_mode": swarm_mission_mode,
        "trip_limit_applies": swarm_mission_mode == "trip_limited",
        "mission_termination": (
            "NEST_ENERGY_TARGET_OR_HORIZON"
            if swarm_mission_mode == "research"
            else "FORAGING_TRIPS_OR_HORIZON"
        ),
        "canonical_summary_file": "swarm_summary.json",
        "legacy_summary_file_classification": "NOT_APPLICABLE_LEGACY_SINGLE_ROBOT_LOGGER",
        "experiment_mode": experiment_mode.snapshot(),
        "experiment_mode_matrix": all_mode_snapshots(),
        "experiment_mode_environment_variable": "SWARM_EXPERIMENT_MODE",
        "trip_count": trip_count,
        "swarm_baseline": {
            "enabled": scout_count > 1,
            "scout_count": scout_count,
            "trip_count_per_scout": trip_count,
            "trip_count_role": (
                "development_tooling_only" if swarm_mission_mode == "research"
                else "trip_termination_limit"
            ),
            "duration_s": swarm_duration_s,
            "policy": "LOCAL_REACTIVE_45_DEGREE_FULL_FORAGING_CYCLE",
            "working_memory_enabled": False,
            "experience_memory_enabled": False,
            "hormone_enabled": False,
            "exchange_enabled": False,
            "shared_map_created": False,
            "return_navigation": "STATELESS_LOCAL_REACTIVE_RSSI_CONFIRMATION_ONLY",
        },
        "trip_control_environment_variable": (
            "FORAGING_TRIPS"
        ),
        "energy_reselection_between_trips": "NOT_APPLICABLE_PERSISTENT_MULTI_SOURCE_C1",
        "fixed_energy_source": False,
        "working_memory_reset_each_trip": False,
        "experience_memory_persists_across_trips": False,
        "world_map_created": False,
        "navigation_model": "MEMORY_FREE_LOCAL_REACTIVE_BASELINE",
        "nest_energy_accumulates": True,
        "base_world_file": BASE_WORLD_FILE.name,
        "runtime_world_file": runtime_world_file.name,
        "decision_route_predefined": False,
        "decision_policy": "CURRENT_TOF_LOCAL_AVOIDANCE_AND_STRICT_LOS_SOLAR; SEEDED_REACTIVE_EXPLORATION",
        "energy_location": "THREE_CONFIGURED_PERSISTENT_SOURCES",
        "energy_source_control": {
            "mode": "THREE_PERSISTENT_LIGHT_ENERGY_SOURCES",
            "sources": [{"resource_id": item.endpoint_id, "x_m": item.x_m, "y_m": item.y_m, "relative_harvest_rate": item.relative_harvest_rate} for item in endpoints],
            "pilot_normalized_rates": True,
            "concurrent_harvesting_allowed": True,
            "resource_depletion_enabled": False,
        },
        "maze_design": {
            "name": "original_selected_validated_maze",
            "topology": "HISTORICAL_FIXED_WALL_TOPOLOGY",
            "corridor_width_definition": "geometry_derived",
            "corridor_width_nominal_m": None,
            "world_width_m": 14.0,
            "world_height_m": 14.0,
            "robot_radius_m": 0.25,
            "wall_thickness_m": 0.18,
            "generation_seed": None,
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
            "collection_mode": "PERSISTENT_NEAR_FIELD_HARVEST_RATE_X_DT",
        },
        "energy_minimum_reachable_center_distance_m": (
            exploration_config.wall_stop_distance_m
            + energy_sensor.visible_marker_radius_m
        ),
        "energy_marker": {
            "visible": True,
            "shape": "persistent_source_circles",
            "radius_m": 0.12,
            "sources": [{"resource_id": item.endpoint_id, "x_m": item.x_m, "y_m": item.y_m} for item in endpoints],
        },
        "energy_random_seed": seed ^ 0x5A17,
        "decision_random_seed": seed,
        "render_enabled": render_enabled,
        "fast_headless_research_mode": fast_headless_research_mode,
        "execution_semantics": (
            "FAST_HEADLESS_NO_GUI_OR_REDRAW; identical physics/control/sensor/RNG steps"
            if fast_headless_research_mode
            else "STANDARD_EXECUTION"
        ),
        "batch_run_id": batch_run_id,
        "research_provenance": {
            "freeze_commit": freeze_commit,
            "freeze_tag": freeze_tag,
            "canonical_seed_set_sha256": canonical_seed_set_sha256,
        },
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

    # Metadata is evidence for a specific runtime condition.  Do not describe
    # the memory-capable controller as if it were active in a multi-Scout
    # Baseline run.
    if scout_count > 1 and experiment_mode.mode.value == "baseline":
        run_config.update({
            "navigation_model": "MEMORY_FREE_LOCAL_REACTIVE_BASELINE",
            "decision_policy": (
                "CURRENT_TOF_LOCAL_AVOIDANCE; STRICT_LOS_SOLAR; "
                "RSSI_CONFIRMATION_ONLY_AT_PHYSICAL_NEST_ENTRY"
            ),
            "working_memory_reset_each_trip": False,
            "experience_memory_persists_across_trips": False,
            "condition_specific_capabilities": {
                "working_memory": False,
                "experience_memory": False,
                "exchange": False,
                "artificial_internal_hormone": False,
                "route_breadcrumbs": False,
                "reactive_exploration": True,
                "nest_cue": "PHYSICAL_NEST_ENTRY_PLUS_RSSI_CONFIRMATION_ONLY",
                "nest_cue_definition": (
                    "PHYSICAL_NEST_ENTRY_PLUS_RSSI_CONFIRMATION_ONLY; no RSSI steering, "
                    "position, distance, bearing, route, map, or planner"
                ),
            },
            "available_system_capabilities": {
                "working_memory": True,
                "experience_memory": True,
                "exchange": True,
                "artificial_internal_hormone": True,
            },
        })
        run_config["fixes"] = [
            "ORIGINAL_VALIDATED_MAZE_TOPOLOGY",
            "THREE_PERSISTENT_ENERGY_SOURCES_A_B_C",
            "PILOT_NORMALIZED_HARVEST_RATE_X_DT",
            "STRICT_LOS_SOLAR_FIELD",
            "CURRENT_TOF_LOCAL_COLLISION_SAFETY",
            "STATELESS_45_DEGREE_REACTIVE_EXPLORATION",
            "RSSI_CONFIRMATION_ONLY_AT_PHYSICAL_NEST_ENTRY",
            "COMMON_INTERNAL_ROBOT_ENERGY_ACCOUNTING",
            "NEST_ENERGY_GROSS_WITHDRAWAL_NET_LEDGER",
            "NO_WM_EM_EXCHANGE_AIH",
        ]

    env = backend = logger = trace = hud = None
    memory = WorkingMemory(
        # Adjacent maze corridors can be roughly 0.3 m apart at the robot
        # centre line.  A 0.38 m loop radius therefore merged distinct
        # corridors and discarded a breadcrumb suffix that was still needed
        # for physical backtracking.  Keep pruning, but only for a true
        # revisit of the same local route.
        loop_closure_radius_m=0.12,
    )
    experience = ExperienceMemory()
    if not experiment_mode.experience_memory_enabled:
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

        if scout_count > 1:
            logger.snapshot_sources([
                PROJECT_ROOT / "main.py", BASE_WORLD_FILE,
                runtime_world_file, SOURCE_ROOT / "swarm_baseline.py",
                resource_config_path,
                SOURCE_ROOT / "irsim_range_sensor.py",
                SOURCE_ROOT / "energy_sensor.py",
                SOURCE_ROOT / "result_logger.py",
            ])
            logger.log_event(
                "SWARM_BASELINE_START",
                f"seed={seed}; scouts={scout_count}; duration_s={swarm_duration_s}; "
                "WM=off; EM=off; hormone=off; exchange=off",
            )
            result = BaselineSwarmRunner(
                env=env, run_dir=logger.run_dir, energy_sensor=energy_sensor,
                seed=seed, scout_count=scout_count,
                duration_s=swarm_duration_s, trip_count=trip_count,
                harvest_payload_target=float(resource_config["harvest_payload_target"]),
                internal_energy_capacity=float(resource_config["robot_internal_energy_capacity"]),
                initial_internal_energy=float(resource_config["robot_initial_internal_energy"]),
                energy_cost_per_encoder_distance=float(resource_config["energy_cost_per_encoder_distance"]),
                render_enabled=render_enabled, mission_mode=swarm_mission_mode,
                nest_energy_target=nest_energy_target,
            ).run()
            logger.log_event(
                "SWARM_BASELINE_COMPLETE",
                f"scouts={scout_count}; engineering={result['engineering_status']}; "
                f"mission={result['mission_outcome']}; "
                f"nest_energy={result['nest_energy_units']}",
            )
            if render_enabled:
                logger.save_final_figure()
            logger.mark_completed(
                mission_outcome=result["mission_outcome"],
                experimental_validity=result["experimental_validity"],
            )
            print(
                "Baseline multi-Scout simulation completed: "
                f"engineering={result['engineering_status']}; "
                f"mission={result['mission_outcome']}; "
                f"validity={result['experimental_validity']}"
            )
            print(logger.run_dir)
            return 0

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

        logger.snapshot_sources(
            [
                PROJECT_ROOT / "main.py",
                BASE_WORLD_FILE,
                runtime_world_file,
            ]
            + [
                SOURCE_ROOT / name
                for name in [
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
            ]
        )

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
