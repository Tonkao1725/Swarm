from __future__ import annotations

from dataclasses import dataclass
import csv
import json
import math
import random

from decision_trace_logger import ForagingTraceLogger
from energy_sensor import RandomEndpointEnergySensor
from motion_controller import MotionController
from working_memory import JunctionRecord, WorkingMemory
from experience_memory import ExperienceMemory
from experiment_modes import ExperimentModeConfig


@dataclass(frozen=True)
class AutonomousForagingConfig:
    movement_step_m: float = 0.10
    wall_stop_distance_m: float = 0.58
    endpoint_tolerance_m: float = 0.025
    open_threshold_m: float = 0.95
    minimum_centering_m: float = 0.18
    maximum_centering_m: float = 0.60
    junction_cluster_radius_m: float = 0.48
    junction_exit_radius_m: float = 0.82
    minimum_progress_m: float = 0.015
    movement_error_tolerance_m: float = 0.02
    home_tolerance_m: float = 0.08
    maximum_distance_m: float = 320.0
    minimum_post_turn_side_clearance_m: float = 0.32
    random_seed: int = 20260731
    trip_count: int = 5
    maximum_zero_progress_control_loops: int = 200
    memory_enabled: bool = True
    route_experience_enabled: bool = True
    current_trip_visit_penalty: float = 4.0

    # Experience is a bounded preference, never a forced replay.
    # 3.0 gives roughly 60/20/20 for one preferred option among three
    # equally unvisited choices.
    experience_action_bonus: float = 3.0
    minimum_action_weight: float = 0.02

    # Light-following stabilization. A light-guided turn must be followed by
    # real forward progress before another light turn is permitted.
    light_turn_release_distance_m: float = 0.25

    # Return-home breadcrumb follower. Used only after Energy collection.
    return_waypoint_tolerance_m: float = 0.16
    # A wider shortcut turn can cut into an inside wall corner even when the
    # current front beam is clear.  Keep shortcuts nearly collinear with the
    # breadcrumb segment; larger direction changes follow the recorded
    # current-trip breadcrumb instead.
    return_shortcut_heading_limit_deg: float = 5.0
    return_shortcut_clearance_margin_m: float = 0.48
    return_shortcut_side_clearance_m: float = 0.36
    return_shortcut_max_lookahead: int = 30
    return_recovery_max_attempts: int = 12
    return_recovery_turn_step_deg: float = 8.0
    return_recovery_forward_step_m: float = 0.10
    return_recovery_progress_epsilon_m: float = 0.03


@dataclass
class DecisionPoint:
    key: str
    x_m: float
    y_m: float
    observations: int = 1

    def distance_to(self,x:float,y:float)->float:
        return math.hypot(x-self.x_m,y-self.y_m)

    def update(self,x:float,y:float)->None:
        # Keep the first current-trip observation as this local landmark's
        # anchor.  Moving the centroid lets a chain of individually-close
        # observations drift one ID across neighbouring corridors, merging
        # their port-visit counts and defeating win-shift.
        self.observations += 1


class AutonomousForagingController:
    """Rat-inspired foraging controller without SLAM or world mapping.

    A DecisionPoint is only a trip-local landmark used to remember which exits
    have already been sampled. No edges are connected and no global maze graph
    is created. Successful choice sequences are summarized into Experience
    Memory after returning HOME.
    """

    def __init__(self, *, motion:MotionController, sensor,
                 energy_sensor:RandomEndpointEnergySensor,
                 trace:ForagingTraceLogger, memory:WorkingMemory,
                 experience:ExperienceMemory,
                 experiment_mode:ExperimentModeConfig,
                 config:AutonomousForagingConfig, hud=None)->None:
        self.motion=motion; self.sensor=sensor; self.energy_sensor=energy_sensor
        self.trace=trace; self.memory=memory; self.experience=experience
        self.experiment_mode=experiment_mode; self.config=config; self.hud=hud
        self.rng=random.Random(config.random_seed)
        self.total_distance_m=0.0
        self.decision_points:list[DecisionPoint]=[]
        self.active_decision_key:str|None=None
        self.previous_snapshot=None
        self.pending_redecision=False
        self.latest_energy_reading=None

        # Hybrid light-following state:
        # False = light may request a turn
        # True  = keep the chosen heading until enough forward progress occurs
        self.light_turn_locked = False
        self.light_progress_since_turn_m = 0.0

        # Experience is recalled only at actual Decision Points.
        self.experience_decision_recall_count = 0
        self.experience_decision_fallback_count = 0
        # This is deliberately independent of Working Memory's live junction
        # stack.  Loop pruning removes reversible route state, but it must not
        # make a later, unrelated junction reuse an Experience ordinal.
        self.trip_decision_ordinal = 0
        self.current_trip_id = 0

        self._zero_progress=0; self._last_signature=None

    @staticmethod
    def _heading_quadrant(theta:float)->int:
        return int(round(theta/(math.pi/2)))%4

    @staticmethod
    def _global_direction(heading:int,action:str)->int:
        return (heading+{"MOVE_FORWARD":0,"TURN_LEFT":1,"TURN_RIGHT":-1}[action])%4

    def _open_actions(self,s)->list[str]:
        out=[]
        if getattr(s,'left_valid',True) and s.left_m>self.config.open_threshold_m: out.append('TURN_LEFT')
        if getattr(s,'front_valid',True) and s.front_m>self.config.open_threshold_m: out.append('MOVE_FORWARD')
        if getattr(s,'right_valid',True) and s.right_m>self.config.open_threshold_m: out.append('TURN_RIGHT')
        return out

    def _nearest_point(self,pose)->tuple[DecisionPoint|None,float]:
        if not self.decision_points: return None,math.inf
        p=min(self.decision_points,key=lambda q:q.distance_to(pose.x_m,pose.y_m))
        return p,p.distance_to(pose.x_m,pose.y_m)

    def _resolve_decision_point(self,s)->DecisionPoint:
        p,d=self._nearest_point(s.pose)
        if p is not None and d<=self.config.junction_cluster_radius_m:
            p.update(s.pose.x_m,s.pose.y_m); return p
        p=DecisionPoint(f"D{len(self.decision_points)+1:03d}",s.pose.x_m,s.pose.y_m)
        self.decision_points.append(p)
        return p

    def _release_latch(self,pose)->None:
        if self.active_decision_key is None:return
        p=next((x for x in self.decision_points if x.key==self.active_decision_key),None)
        if p is None or p.distance_to(pose.x_m,pose.y_m)>self.config.junction_exit_radius_m:
            self.active_decision_key=None

    def _sample_energy(self,phase:str):
        pose=self.motion.backend.read_pose()
        reading=self.energy_sensor.read(pose,self.sensor)
        self.latest_energy_reading=reading
        if self.hud is not None:
            self.hud.update(phase=phase,activity=('Following light' if reading.guidance_active else 'Exploring maze'),
                energy_detected=reading.detected,energy_distance_m=reading.distance_m,
                line_of_sight_clear=reading.line_of_sight_clear,inside_sensor_fov=reading.inside_sensor_fov,
                sim_time_s=self.motion.backend.time_s,working_memory_route=self.memory.route_string or '-',
                solar_left=reading.solar_left,solar_center=reading.solar_center,solar_right=reading.solar_right,
                solar_max=reading.solar_max,strongest_direction=reading.strongest_direction,
                light_guidance_active=reading.guidance_active,collect_threshold_reached=reading.collect_threshold_reached,
                light_approach_active=reading.approach_active,light_state=reading.light_state)
        self.trace.log_energy({"sim_time_s":self.motion.backend.time_s,"phase":phase,"x_m":pose.x_m,"y_m":pose.y_m,
            "detected":reading.detected,"endpoint_id":reading.endpoint_id or '',"distance_to_active_source_m":reading.distance_m,
            "signal_strength":reading.signal_strength,"relative_bearing_deg":math.degrees(reading.relative_bearing_rad),
            "inside_sensor_fov":reading.inside_sensor_fov,"beam_hit_valid":reading.beam_hit_valid,
            "wall_distance_on_energy_ray_m":reading.wall_distance_m,"line_of_sight_clear":reading.line_of_sight_clear,
            "blocked_by_wall":reading.blocked_by_wall,"within_detection_radius":reading.within_detection_radius,
            "acquisition_clearance_m":reading.acquisition_clearance_m,"solar_left":reading.solar_left,
            "solar_center":reading.solar_center,"solar_right":reading.solar_right,"solar_max":reading.solar_max,
            "solar_mean":reading.solar_mean,"strongest_direction":reading.strongest_direction,
            "guidance_active":reading.guidance_active,"collect_threshold_reached":reading.collect_threshold_reached,
            "approach_active":reading.approach_active,"light_state":reading.light_state,"light_path_factor":reading.light_path_factor})
        return reading

    def _execute_turn(self,action:str,*,record:bool,source:str)->None:
        if action=='MOVE_FORWARD': return
        if action=='TURN_BACK':
            self._execute_turn('TURN_LEFT',record=False,source=source+'_1')
            self._execute_turn('TURN_LEFT',record=False,source=source+'_2')
            if record:self.memory.append_turn('TURN_BACK',source)
            return
        result=self.motion.turn_left(90.0) if action=='TURN_LEFT' else self.motion.turn_right(90.0)
        self.motion.stop()
        if abs(result.actual_value)<math.radians(70): raise RuntimeError(f'{action} failed')
        if record:
            self.memory.append_turn(action,source)
            pose = self.motion.backend.read_pose()
            self.memory.record_turn_pose(
                x_m=pose.x_m,
                y_m=pose.y_m,
                theta_rad=pose.theta_rad,
            )

    def _u_turn(self,source:str)->None:
        # A 180-degree turn at a dead end is physically asymmetric near maze
        # corners.  Try both rotational directions before treating the
        # current-trip backtrack as impossible.
        for action in ('TURN_LEFT', 'TURN_RIGHT'):
            try:
                self._execute_turn(action,record=False,source=source+'_1')
                self._execute_turn(action,record=False,source=source+'_2')
                return
            except RuntimeError:
                self.motion.stop()
        raise RuntimeError(f'{source} U-turn failed in both directions')

    def _move(self,d:float,*,record:bool,source:str,phase:str)->tuple[float,bool]:
        if d<=0:return 0.0,False
        r=self.motion.move_forward(d); self.motion.stop(0.0); actual=abs(r.actual_value)
        self.total_distance_m+=actual

        if actual > 0.0 and self.light_turn_locked:
            self.light_progress_since_turn_m += actual
            if (
                self.light_progress_since_turn_m
                >= self.config.light_turn_release_distance_m
            ):
                self.light_turn_locked = False
                self.light_progress_since_turn_m = 0.0

        if record and actual>1e-9:
            self.memory.append_move(actual,source)
            pose = self.motion.backend.read_pose()
            loop_pruned = self.memory.record_pose(
                x_m=pose.x_m,
                y_m=pose.y_m,
                theta_rad=pose.theta_rad,
                distance_delta_m=actual,
            )
            if loop_pruned:
                self.trace.log_action_audit({
                    "sim_time_s":self.motion.backend.time_s,
                    "stage":"WORKING_MEMORY_LOOP_PRUNED",
                    "junction_id":"",
                    "x_m":pose.x_m,
                    "y_m":pose.y_m,
                    "heading_deg":math.degrees(pose.theta_rad),
                    "heading_quadrant":self._heading_quadrant(
                        pose.theta_rad
                    ),
                    "left_m":"",
                    "front_m":"",
                    "right_m":"",
                    "requested_action":"",
                    "requested_global_direction":"",
                    "requested_clearance_m":"",
                    "open_actions":"",
                    "safe_actions":"",
                    "selected_action":"",
                    "selected_global_direction":"",
                    "action_rejected":False,
                    "rejection_reason":(
                        f"loops={self.memory.loop_erasures};"
                        f"pruned_breadcrumbs="
                        f"{self.memory.pruned_breadcrumbs};"
                        f"pruned_decisions="
                        f"{self.memory.pruned_decisions}"
                    ),
                    "working_memory_route":(
                        self.memory.route_string
                    ),
                })
        stuck=actual<self.config.minimum_progress_m or d-actual>self.config.movement_error_tolerance_m
        if stuck:
            p=self.motion.backend.read_pose(); self.trace.log_recovery({"sim_time_s":self.motion.backend.time_s,
                "phase":phase,"reason":"PARTIAL_OR_NO_PROGRESS","requested_distance_m":d,"actual_distance_m":actual,
                "x_m":p.x_m,"y_m":p.y_m,"heading_deg":math.degrees(p.theta_rad),"working_memory_route":self.memory.route_string})
        return actual,stuck

    def _guard(self,s)->None:
        sig=(round(s.sim_time_s,6),round(s.pose.x_m,5),round(s.pose.y_m,5),round(s.pose.theta_rad,5),self.active_decision_key,self.pending_redecision)
        self._zero_progress=self._zero_progress+1 if sig==self._last_signature else 0
        self._last_signature=sig
        if self._zero_progress>self.config.maximum_zero_progress_control_loops:
            raise RuntimeError('Controller made no simulation progress')

    def _side_opening_transition(self,c)->tuple[bool,float,str]:
        p=self.previous_snapshot
        if p is None:return False,0.0,''
        lo=p.left_m<=self.config.open_threshold_m<c.left_m
        ro=p.right_m<=self.config.open_threshold_m<c.right_m
        vals=[];names=[]
        if lo:vals.append(max(0.0,p.left_m));names.append('LEFT')
        if ro:vals.append(max(0.0,p.right_m));names.append('RIGHT')
        return (bool(vals),sum(vals)/len(vals) if vals else 0.0,'|'.join(names))

    def _centre_on_opening(self,half:float,s)->bool:
        target=min(self.config.maximum_centering_m,max(self.config.minimum_centering_m,half))
        safe=min(target,max(0.0,s.front_m-self.config.wall_stop_distance_m))
        if safe<=self.config.minimum_progress_m:return True
        _,stuck=self._move(safe,record=True,source='DECISION_POINT_CENTER',phase='EXPLORE')
        return not stuck

    @staticmethod
    def _solar(reading,action):
        return {'TURN_LEFT':reading.solar_left,'MOVE_FORWARD':reading.solar_center,'TURN_RIGHT':reading.solar_right}[action]

    def _weighted_choice(
        self,
        actions: list[str],
        point: DecisionPoint,
        heading: int,
        ordinal: int,
    ):
        """
        Strict rat-inspired win-shift with bounded Experience bias.

        First select only the least-visited locally available choices in the
        current Trip. If several choices are equally least visited, avoid the
        action used on the previous visit to this Decision Point when another
        option exists. Experience changes probability only inside this eligible
        set and can never force a repeatedly visited branch.
        """
        preferred = self._recalled_experience_action(
            actions=actions,
            heading=heading,
            ordinal=ordinal,
        )

        visit_counts = {}
        global_directions = {}
        for action in actions:
            global_direction = self._global_direction(
                heading,
                action,
            )
            global_directions[action] = global_direction
            visit_counts[action] = (
                self.memory.current_trip_port_visits(
                    decision_point_key=point.key,
                    global_direction=global_direction,
                )
            )

        minimum_visits = min(visit_counts.values())
        eligible = [
            action
            for action in actions
            if visit_counts[action] == minimum_visits
        ]

        previous_action = None
        for record in reversed(self.memory.junctions):
            if record.decision_point_key == point.key:
                previous_action = record.chosen_action
                break

        if (
            len(eligible) > 1
            and previous_action in eligible
        ):
            alternatives = [
                action
                for action in eligible
                if action != previous_action
            ]
            if alternatives:
                eligible = alternatives

        weights = []
        details = {}
        for action in actions:
            is_eligible = action in eligible
            experience_preferred = (
                is_eligible
                and preferred is not None
                and action == preferred
            )
            multiplier = (
                self.config.experience_action_bonus
                if experience_preferred
                else 1.0
            )
            weight = multiplier if is_eligible else 0.0

            details[action] = {
                "trip_visits": visit_counts[action],
                "minimum_visits": minimum_visits,
                "eligible": is_eligible,
                "last_action_avoided": (
                    previous_action is not None
                    and action == previous_action
                    and action not in eligible
                ),
                "experience_preferred": experience_preferred,
                "experience_multiplier": multiplier,
                "weight": weight,
            }
            weights.append(weight)

        total = sum(weights)
        if total <= 0.0:
            raise RuntimeError(
                "Strict win-shift produced no eligible action"
            )

        for action, weight in zip(actions, weights):
            details[action]["probability"] = weight / total

        chosen = self.rng.choices(
            actions,
            weights=weights,
            k=1,
        )[0]
        return chosen, details


    def _recalled_experience_action(
        self,
        *,
        actions: list[str],
        heading: int,
        ordinal: int,
    ) -> str | None:
        if not (
            self.config.memory_enabled
            and self.config.route_experience_enabled
        ):
            return None

        return self.experience.recalled_action(
            source_id=(
                self.energy_sensor
                .active_endpoint
                .endpoint_id
            ),
            decision_ordinal=ordinal,
            arrival_heading_quadrant=heading,
            candidate_actions=actions,
        )

    def _select_at_decision_point(self, s) -> bool:
        actions = self._open_actions(s)
        if len(actions) < 2:
            return False

        point = self._resolve_decision_point(s)
        heading = self._heading_quadrant(
            s.pose.theta_rad
        )
        ordinal = self.trip_decision_ordinal
        light = self._sample_energy(
            "JUNCTION_DECISION"
        )
        if light.guidance_active:
            if (
                light.strongest_direction == "CENTER"
                and "MOVE_FORWARD" not in actions
            ):
                chosen, details = self._weighted_choice(
                    actions,
                    point,
                    heading,
                    ordinal,
                )
                reason = (
                    "LIGHT_BLOCKED_MEMORY_WEIGHTED_BYPASS:"
                    + "|".join(
                        f"{action}:"
                        f"trip={values['trip_visits']},"
                        f"eligible={int(values['eligible'])},"
                        f"avoid_last={int(values['last_action_avoided'])},"
                        f"exp={int(values['experience_preferred'])},"
                        f"p={values['probability']*100:.1f}%"
                        for action, values
                        in details.items()
                    )
                )
                if any(
                    values["experience_preferred"]
                    for values in details.values()
                ):
                    self.experience_decision_recall_count += 1
            else:
                chosen = max(
                    actions,
                    key=lambda action: (
                        self._solar(light, action),
                        {
                            "MOVE_FORWARD": 2,
                            "TURN_LEFT": 1,
                            "TURN_RIGHT": 0,
                        }[action],
                    ),
                )
                reason = "VISIBLE_LIGHT_DIRECTION"
                details = {}
        else:
            chosen, details = self._weighted_choice(
                actions,
                point,
                heading,
                ordinal,
            )
            reason = (
                "RAT_EXPERIENCE_WEIGHTED_CHOICE:"
                + "|".join(
                    f"{action}:"
                    f"trip={values['trip_visits']},"
                    f"exp={int(values['experience_preferred'])},"
                    f"p={values['probability']*100:.1f}%"
                    for action, values
                    in details.items()
                )
            )
            if any(
                values["experience_preferred"]
                for values in details.values()
            ):
                self.experience_decision_recall_count += 1
            elif self.experience.has_successful_route(
                source_id=(
                    self.energy_sensor
                    .active_endpoint
                    .endpoint_id
                )
            ):
                self.experience_decision_fallback_count += 1

        path_index = len(self.memory.path)
        chosen_global_direction = self._global_direction(
            heading,
            chosen,
        )
        try:
            self._execute_turn(
                chosen,
                record=True,
                source="DECISION_POINT",
            )
        except RuntimeError as exc:
            # A ToF-open port may still be unavailable to the circular body at
            # a corner.  Count the failed attempt in current-trip WM so the
            # next decision cannot immediately choose the same port again.
            self.memory.record_decision_port(
                decision_point_key=point.key,
                global_direction=chosen_global_direction,
            )
            pose = self.motion.backend.read_pose()
            self.trace.log_recovery({
                "sim_time_s": self.motion.backend.time_s,
                "phase": "EXPLORE",
                "reason": "DECISION_TURN_REJECTED",
                "requested_distance_m": 0.0,
                "actual_distance_m": 0.0,
                "x_m": pose.x_m,
                "y_m": pose.y_m,
                "heading_deg": math.degrees(pose.theta_rad),
                "working_memory_route": self.memory.route_string,
            })
            self.previous_snapshot = self.sensor.read()
            return False

        if (
            light.guidance_active
            and chosen in {
                "TURN_LEFT",
                "TURN_RIGHT",
            }
        ):
            self.light_turn_locked = True
            self.light_progress_since_turn_m = 0.0

        post = self.sensor.read()
        if (
            post.front_m
            <= self.config.wall_stop_distance_m
        ):
            inverse = (
                "TURN_RIGHT"
                if chosen == "TURN_LEFT"
                else "TURN_LEFT"
                if chosen == "TURN_RIGHT"
                else None
            )
            if inverse:
                self._execute_turn(
                    inverse,
                    record=False,
                    source="DECISION_ABORT",
                )
            if (
                self.memory.path
                and self.memory.path[-1].command
                in {
                    "TURN_LEFT",
                    "TURN_RIGHT",
                }
            ):
                self.memory.path.pop()
            self.light_turn_locked = False
            self.light_progress_since_turn_m = 0.0
            return False

        self.memory.record_decision_port(
            decision_point_key=point.key,
            global_direction=chosen_global_direction,
        )
        self.memory.add_junction(
            JunctionRecord(
                point.key,
                heading,
                chosen,
                reason,
                list(actions),
                list(actions),
                path_index,
                ordinal,
            )
        )
        self.trip_decision_ordinal += 1
        self.trace.log_decision({
            "sim_time_s": s.sim_time_s,
            "phase": "EXPLORE",
            "junction_key": point.key,
            "x_m": s.pose.x_m,
            "y_m": s.pose.y_m,
            "heading_deg": math.degrees(
                s.pose.theta_rad
            ),
            "trip_id": self.current_trip_id,
            "decision_ordinal": ordinal,
            "anchor_distance_m": point.distance_to(
                s.pose.x_m, s.pose.y_m
            ),
            "branch_visit_counts": "|".join(
                f"{action}={details[action]['trip_visits']}"
                for action in actions
            ),
            "branch_global_directions": "|".join(
                f"{action}=D{self._global_direction(heading, action)}"
                for action in actions
            ),
            "left_m": s.left_m,
            "front_m": s.front_m,
            "right_m": s.right_m,
            "open_actions": "|".join(actions),
            "unvisited_actions": "|".join(actions),
            "chosen_action": chosen,
            "reason": reason,
            "random_seed": self.config.random_seed,
            "working_memory_route": (
                self.memory.route_string
            ),
            "solar_left": light.solar_left,
            "solar_center": light.solar_center,
            "solar_right": light.solar_right,
            "solar_max": light.solar_max,
            "strongest_light_direction": (
                light.strongest_direction
            ),
            "light_guidance_active": (
                light.guidance_active
            ),
        })
        self.active_decision_key = point.key
        if self.hud is not None:
            self.hud.update(
                junction_id=point.key,
                last_action=chosen,
                working_memory_route=(
                    self.memory.route_string or "-"
                ),
            )
        self.previous_snapshot = post
        return True

    def _backtrack(self)->None:
        if not self.memory.junctions:raise RuntimeError('All sampled branches exhausted without finding Energy')
        rec=self.memory.junctions[-1]; suffix=self.memory.path[rec.path_index_before_decision:]
        pose=self.motion.backend.read_pose(); self.trace.log_recovery({"sim_time_s":self.motion.backend.time_s,"phase":"BACKTRACK","reason":f"BACKTRACK_START:{rec.decision_point_key}","requested_distance_m":sum(cmd.value for cmd in suffix if cmd.command=='MOVE_FORWARD'),"actual_distance_m":0.0,"x_m":pose.x_m,"y_m":pose.y_m,"heading_deg":math.degrees(pose.theta_rad),"working_memory_route":self.memory.route_string})
        if suffix:
            self._u_turn('BACKTRACK')
            for cmd in reversed(suffix):
                if cmd.command=='MOVE_FORWARD':
                    actual,stuck=self._move(cmd.value,record=False,source='BACKTRACK',phase='BACKTRACK')
                    if stuck or abs(actual-cmd.value)>self.config.movement_error_tolerance_m:raise RuntimeError('Backtrack failed')
                elif cmd.command=='TURN_LEFT':self._execute_turn('TURN_RIGHT',record=False,source='BACKTRACK')
                elif cmd.command=='TURN_RIGHT':self._execute_turn('TURN_LEFT',record=False,source='BACKTRACK')
            self._u_turn('BACKTRACK_RESTORE')
        self.memory.truncate_path(rec.path_index_before_decision)
        self.memory.junctions.pop()
        pose=self.motion.backend.read_pose(); self.trace.log_recovery({"sim_time_s":self.motion.backend.time_s,"phase":"BACKTRACK","reason":f"BACKTRACK_COMPLETE:{rec.decision_point_key}","requested_distance_m":0.0,"actual_distance_m":0.0,"x_m":pose.x_m,"y_m":pose.y_m,"heading_deg":math.degrees(pose.theta_rad),"working_memory_route":self.memory.route_string})
        self.active_decision_key=None; self.pending_redecision=True; self.previous_snapshot=self.sensor.read()

    def _resolve_redecision(self)->None:
        while self.pending_redecision:
            self.pending_redecision=False
            if self._select_at_decision_point(self.sensor.read()):return
            self._backtrack()

    def _follow_light(self,s,reading)->bool:
        if not reading.guidance_active or not reading.line_of_sight_clear:return False
        if self.light_turn_locked:return False
        if reading.strongest_direction not in {'LEFT','RIGHT'}:return False
        action='TURN_LEFT' if reading.strongest_direction=='LEFT' else 'TURN_RIGHT'
        if action not in self._open_actions(s):return False
        self._execute_turn(action,record=True,source='VISIBLE_LIGHT')
        post=self.sensor.read()
        if post.front_m<=self.config.wall_stop_distance_m:
            self._execute_turn('TURN_RIGHT' if action=='TURN_LEFT' else 'TURN_LEFT',record=False,source='LIGHT_ABORT')
            if self.memory.path and self.memory.path[-1].command in {'TURN_LEFT','TURN_RIGHT'}:self.memory.path.pop()
            return False
        self.light_turn_locked = True
        self.light_progress_since_turn_m = 0.0
        self.previous_snapshot=post
        return True

    @staticmethod
    def _wrap_angle(angle: float) -> float:
        return (
            angle + math.pi
        ) % (2.0 * math.pi) - math.pi

    def _turn_to_heading(
        self,
        target_heading_rad: float,
        *,
        source: str,
    ) -> None:
        pose = self.motion.backend.read_pose()
        error = self._wrap_angle(
            float(target_heading_rad) - pose.theta_rad
        )
        degrees = abs(math.degrees(error))
        if degrees <= 2.0:
            return

        requested_radians = abs(error)

        if error > 0.0:
            result = self.motion.turn_left(degrees)
        else:
            result = self.motion.turn_right(degrees)
        self.motion.stop()

        # Validate the resulting heading, not a fixed minimum turn angle.
        # Small legitimate corrections (for example 3.3 degrees) must not
        # fail merely because they are below the old 5-degree threshold.
        corrected_pose = self.motion.backend.read_pose()
        residual_error = abs(
            self._wrap_angle(
                float(target_heading_rad)
                - corrected_pose.theta_rad
            )
        )
        allowed_residual = max(
            math.radians(2.0),
            requested_radians * 0.40,
        )

        if residual_error > allowed_residual:
            raise RuntimeError(
                f"{source} heading correction failed: "
                f"requested_deg={degrees:.3f}; "
                f"actual_deg={math.degrees(abs(result.actual_value)):.3f}; "
                f"residual_deg={math.degrees(residual_error):.3f}"
            )

    def _choose_return_target(
        self,
        *,
        waypoint_index: int,
        pose,
        snapshot,
    ) -> int:
        """Skip only breadcrumbs directly visible through current ToF."""
        breadcrumbs = self.memory.breadcrumbs
        if waypoint_index <= 0:
            return 0

        if min(snapshot.left_m, snapshot.right_m) < (
            self.config.return_shortcut_side_clearance_m
        ):
            return waypoint_index

        usable_distance = max(
            0.0,
            snapshot.front_m
            - self.config.return_shortcut_clearance_margin_m,
        )
        if usable_distance <= (
            self.config.return_waypoint_tolerance_m
        ):
            return waypoint_index

        lowest = max(
            0,
            waypoint_index
            - self.config.return_shortcut_max_lookahead,
        )
        chosen = waypoint_index
        heading_limit = math.radians(
            self.config.return_shortcut_heading_limit_deg
        )

        for candidate_index in range(
            waypoint_index - 1,
            lowest - 1,
            -1,
        ):
            candidate = breadcrumbs[candidate_index]
            dx = candidate.x_m - pose.x_m
            dy = candidate.y_m - pose.y_m
            distance = math.hypot(dx, dy)
            if distance > usable_distance:
                continue

            target_heading = math.atan2(dy, dx)
            heading_error = abs(
                self._wrap_angle(
                    target_heading - pose.theta_rad
                )
            )
            if heading_error <= heading_limit:
                chosen = candidate_index

        return chosen

    def _recover_return_blockage(
        self,
        *,
        target,
    ) -> bool:
        """Bounded local ToF recovery around a blocked breadcrumb corner."""
        no_progress = 0

        for attempt in range(
            self.config.return_recovery_max_attempts
        ):
            pose = self.motion.backend.read_pose()
            before = math.hypot(
                target.x_m - pose.x_m,
                target.y_m - pose.y_m,
            )
            snapshot = self.sensor.read()

            turn_deg = (
                self.config.return_recovery_turn_step_deg
                if snapshot.left_m >= snapshot.right_m
                else -self.config.return_recovery_turn_step_deg
            )
            if attempt % 2 == 1:
                turn_deg = -turn_deg

            if turn_deg > 0.0:
                self.motion.turn_left(abs(turn_deg))
            else:
                self.motion.turn_right(abs(turn_deg))
            self.motion.stop()

            snapshot = self.sensor.read()
            safe = min(
                self.config.return_recovery_forward_step_m,
                max(
                    0.0,
                    snapshot.front_m
                    - self.config.wall_stop_distance_m,
                ),
            )

            if safe > self.config.minimum_progress_m:
                actual, stuck = self._move(
                    safe,
                    record=False,
                    source="RETURN_RECOVERY",
                    phase="RETURN_HOME",
                )
                if not stuck and actual > self.config.minimum_progress_m:
                    current = self.motion.backend.read_pose()
                    after = math.hypot(
                        target.x_m - current.x_m,
                        target.y_m - current.y_m,
                    )
                    self.trace.log_return({
                        "sim_time_s":self.motion.backend.time_s,
                        "command":"RETURN_LOCAL_RECOVERY",
                        "value":actual,
                        "x_m":current.x_m,
                        "y_m":current.y_m,
                        "heading_deg":math.degrees(
                            current.theta_rad
                        ),
                    })
                    if after < (
                        before
                        - self.config.return_recovery_progress_epsilon_m
                    ):
                        return True
                    no_progress += 1
                else:
                    no_progress += 1
            else:
                no_progress += 1

            if no_progress >= 4:
                pose = self.motion.backend.read_pose()
                desired = math.atan2(
                    target.y_m - pose.y_m,
                    target.x_m - pose.x_m,
                )
                try:
                    self._turn_to_heading(
                        desired,
                        source="RETURN_RECOVERY_REALIGN",
                    )
                except RuntimeError:
                    pass
                no_progress = 0

        return False

    def _return_home(self,home)->float:
        if len(self.memory.breadcrumbs) < 2:
            raise RuntimeError(
                "Working Memory has no breadcrumb return route"
            )

        waypoint_index = len(self.memory.breadcrumbs) - 2
        iterations = 0
        maximum_iterations = max(
            1000,
            len(self.memory.breadcrumbs) * 80,
        )
        shortcuts_enabled = True

        while waypoint_index >= 0:
            iterations += 1
            if iterations > maximum_iterations:
                raise RuntimeError(
                    "Breadcrumb return exceeded iteration guard"
                )

            pose = self.motion.backend.read_pose()
            target = self.memory.breadcrumbs[
                waypoint_index
            ]
            distance = math.hypot(
                target.x_m - pose.x_m,
                target.y_m - pose.y_m,
            )

            tolerance = (
                self.config.home_tolerance_m
                if waypoint_index == 0
                else self.config.return_waypoint_tolerance_m
            )
            if distance <= tolerance:
                waypoint_index -= 1
                continue

            snapshot = self.sensor.read()
            chosen_index = (
                self._choose_return_target(
                    waypoint_index=waypoint_index,
                    pose=pose,
                    snapshot=snapshot,
                )
                if shortcuts_enabled
                else waypoint_index
            )
            shortcut_from = waypoint_index
            waypoint_index = chosen_index
            target = self.memory.breadcrumbs[
                waypoint_index
            ]

            dx = target.x_m - pose.x_m
            dy = target.y_m - pose.y_m
            target_heading = math.atan2(dy, dx)
            try:
                self._turn_to_heading(
                    target_heading,
                    source="RETURN_BREADCRUMB",
                )
            except RuntimeError as exc:
                # A physical turn can finish with a larger-than-expected
                # residual error near a corner.  This is a recoverable
                # navigation condition, so use the existing bounded local
                # recovery before declaring the breadcrumb route unusable.
                current = self.motion.backend.read_pose()
                self.trace.log_recovery({
                    "sim_time_s": self.motion.backend.time_s,
                    "phase": "RETURN_HOME",
                    "reason": "BREADCRUMB_HEADING_CORRECTION_FAILED",
                    "requested_distance_m": 0.0,
                    "actual_distance_m": 0.0,
                    "x_m": current.x_m,
                    "y_m": current.y_m,
                    "heading_deg": math.degrees(current.theta_rad),
                    "working_memory_route": self.memory.route_string,
                })
                if self._recover_return_blockage(target=target):
                    continue
                if chosen_index < shortcut_from:
                    self.trace.log_return({
                        "sim_time_s": self.motion.backend.time_s,
                        "command": "SHORTCUT_FALLBACK_NEARER_BREADCRUMB",
                        "value": 0.0,
                        "x_m": pose.x_m,
                        "y_m": pose.y_m,
                        "heading_deg": math.degrees(pose.theta_rad),
                    })
                    waypoint_index = shortcut_from
                    shortcuts_enabled = False
                    continue
                raise RuntimeError(
                    "Breadcrumb return heading correction failed after "
                    "local recovery"
                ) from exc

            snapshot = self.sensor.read()
            pose = self.motion.backend.read_pose()
            remaining = math.hypot(
                target.x_m - pose.x_m,
                target.y_m - pose.y_m,
            )
            safe = min(
                self.config.movement_step_m,
                remaining,
                max(
                    0.0,
                    snapshot.front_m
                    - self.config.wall_stop_distance_m,
                ),
            )
            # A turn anchor is recorded at the pose where the outbound route
            # changed direction.  When returning to that anchor, the segment
            # from the anchor to our current pose was traversed in this same
            # Trip.  A forward ToF ray can see the adjacent corner and reject
            # that reverse segment before motion is attempted.  In this one
            # case, let the collision-checked motion command validate the
            # already-observed segment instead of treating the ToF margin as
            # a global obstacle.
            if (
                safe <= self.config.minimum_progress_m
                and chosen_index == shortcut_from
                and target.is_turn_anchor
            ):
                safe = min(self.config.movement_step_m, remaining)
            if safe <= self.config.minimum_progress_m:
                if self._recover_return_blockage(target=target):
                    continue
                if chosen_index < shortcut_from:
                    self.trace.log_return({
                        "sim_time_s": self.motion.backend.time_s,
                        "command": "SHORTCUT_FALLBACK_NEARER_BREADCRUMB",
                        "value": 0.0,
                        "x_m": pose.x_m,
                        "y_m": pose.y_m,
                        "heading_deg": math.degrees(pose.theta_rad),
                    })
                    waypoint_index = shortcut_from
                    shortcuts_enabled = False
                    continue
                raise RuntimeError(
                    "Breadcrumb return blocked after local recovery"
                )

            actual, stuck = self._move(
                safe,
                record=False,
                source="RETURN_BREADCRUMB",
                phase="RETURN_HOME",
            )
            if stuck:
                if self._recover_return_blockage(target=target):
                    continue
                if chosen_index < shortcut_from:
                    current = self.motion.backend.read_pose()
                    self.trace.log_return({
                        "sim_time_s": self.motion.backend.time_s,
                        "command": "SHORTCUT_FALLBACK_NEARER_BREADCRUMB",
                        "value": 0.0,
                        "x_m": current.x_m,
                        "y_m": current.y_m,
                        "heading_deg": math.degrees(current.theta_rad),
                    })
                    waypoint_index = shortcut_from
                    shortcuts_enabled = False
                    continue
                raise RuntimeError(
                    "Breadcrumb return made no progress after recovery"
                )

            current = self.motion.backend.read_pose()
            self.trace.log_return({
                "sim_time_s":self.motion.backend.time_s,
                "command":(
                    "SHORTCUT_BREADCRUMB"
                    if chosen_index < shortcut_from
                    else "FOLLOW_BREADCRUMB"
                ),
                "value":actual,
                "x_m":current.x_m,
                "y_m":current.y_m,
                "heading_deg":math.degrees(
                    current.theta_rad
                ),
            })

        # Restore the outward HOME orientation for the next Trip.
        self._turn_to_heading(
            home.theta_rad,
            source="HOME_DEPARTURE_ALIGNMENT",
        )
        pose = self.motion.backend.read_pose()
        return math.hypot(
            pose.x_m - home.x_m,
            pose.y_m - home.y_m,
        )

    def _run_single_trip(self)->dict:
        home=self.motion.backend.read_pose()
        self.motion.stop(
            self.motion.backend.control_period_s
        )
        self.memory.start_route(
            x_m=home.x_m,
            y_m=home.y_m,
            theta_rad=home.theta_rad,
        )
        self.previous_snapshot = self.sensor.read()
        energy = self._sample_energy("EXPLORE")

        while not energy.detected:
            if self.total_distance_m>self.config.maximum_distance_m:raise RuntimeError('Maximum exploration distance exceeded')
            if self.pending_redecision:self._resolve_redecision();energy=self._sample_energy('EXPLORE');continue
            s=self.sensor.read();self._guard(s);self._release_latch(s.pose)
            light=self._sample_energy('EXPLORE')
            if light.detected:energy=light;break
            if self._follow_light(s,light):energy=self._sample_energy('LIGHT_APPROACH');continue
            nearest,d=self._nearest_point(s.pose)
            if self.active_decision_key is None and nearest is not None and d<=self.config.junction_cluster_radius_m and len(self._open_actions(s))>=2:
                if not self._select_at_decision_point(s):
                    if self.memory.junctions:self._backtrack()
                    else:self.previous_snapshot=self.sensor.read()
                energy=self._sample_energy('EXPLORE');continue
            opening,half,_=self._side_opening_transition(s)
            if opening and self.active_decision_key is None:
                if not self._centre_on_opening(half,s):raise RuntimeError('Collision while centering decision point')
                c=self.sensor.read();actions=self._open_actions(c)
                if len(actions)>=2:
                    if not self._select_at_decision_point(c):
                        if self.memory.junctions:self._backtrack()
                        else:self.previous_snapshot=self.sensor.read()
                elif len(actions)==1 and actions[0]!='MOVE_FORWARD':self._execute_turn(actions[0],record=True,source='FORCED_CORNER')
                elif len(actions)==0:self._backtrack()
                self.previous_snapshot=self.sensor.read();energy=self._sample_energy('EXPLORE');continue
            front_blocked=s.front_m<=self.config.wall_stop_distance_m+self.config.endpoint_tolerance_m
            if front_blocked:
                e=self._sample_energy('AT_ENDPOINT')
                if e.detected:energy=e;break
                actions=self._open_actions(s)
                if len(actions)==0:self._backtrack()
                elif len(actions)==1 and actions[0]!='MOVE_FORWARD':self._execute_turn(actions[0],record=True,source='FORCED_CORNER')
                elif len(actions)>=2:
                    if not self._select_at_decision_point(s):
                        if self.memory.junctions:self._backtrack()
                        else:self.previous_snapshot=self.sensor.read()
            else:
                safe=min(self.config.movement_step_m,max(0.0,s.front_m-self.config.wall_stop_distance_m))
                if safe<=self.config.minimum_progress_m:self._backtrack()
                else:
                    _,stuck=self._move(safe,record=True,source='EXPLORE_CORRIDOR',phase='EXPLORE')
                    if stuck:
                        # The front-ToF guard can still be beaten by a body
                        # contact at a corner or a partial IR-SIM move.  When
                        # this happens after a recorded decision, return to
                        # that current-trip decision point and let the
                        # existing win-shift policy select another branch.
                        # This deliberately does not add a map or a planner.
                        if self.memory.junctions:
                            self._backtrack()
                            energy=self._sample_energy('EXPLORE')
                            continue
                        raise RuntimeError(
                            'Unexpected collision despite front guard with '
                            'no reversible current-trip decision'
                        )
            self.previous_snapshot=s;energy=self._sample_energy('EXPLORE')
        found=self.motion.backend.read_pose()
        if self.hud is not None:self.hud.collect_energy();self.hud.update(last_action='CARRY',working_memory_route=self.memory.route_string or '-')
        self.motion.stop(0.5)
        outbound=self.total_distance_m;error=self._return_home(home);reached=error<=self.config.home_tolerance_m
        result={"status":"PASS" if reached else "FAIL","experiment_mode":self.experiment_mode.mode.value,
            "memory_enabled":self.config.memory_enabled,"exchange_enabled":self.experiment_mode.exchange_enabled,
            "exchange_type":self.experiment_mode.exchange_type.value,"hormone_enabled":self.experiment_mode.hormone_enabled,
            "energy_found":True,"energy_collected":True,"carried_energy_units":1,"detected_endpoint_id":energy.endpoint_id,
            "active_endpoint_ground_truth":self.energy_sensor.active_endpoint.endpoint_id,"energy_detection_requires_line_of_sight":True,
            "decision_route_was_predefined":False,
            "motor_command_replay_enabled":False,
            "experience_decision_recall_count":(
                self.experience_decision_recall_count
            ),
            "experience_decision_fallback_count":(
                self.experience_decision_fallback_count
            ),
            "navigation_model":(
                "RAT_INSPIRED_DECISION_MEMORY_"
                "NO_WORLD_MAP"
            ),
            "decision_point_count":len(self.decision_points),"world_map_created":False,"working_memory_route":self.memory.route_string,
            "working_memory_command_count":len(self.memory.path),
            "breadcrumb_count":len(self.memory.breadcrumbs),
            "working_memory_loop_erasures":self.memory.loop_erasures,
            "working_memory_pruned_breadcrumbs":self.memory.pruned_breadcrumbs,
            "working_memory_pruned_decisions":self.memory.pruned_decisions,
            "return_navigation":"PRUNED_BREADCRUMB_WITH_TOF_SHORTCUT",
            "found_pose":{"x_m":found.x_m,"y_m":found.y_m,"theta_rad":found.theta_rad},
            "home_position_error_m":error,"home_position_tolerance_m":self.config.home_tolerance_m,"home_reached":reached,
            "outbound_distance_m":outbound,"total_actual_distance_m":self.total_distance_m}
        if not reached:raise RuntimeError('Pruned breadcrumb return did not reach HOME')
        return result

    def _reset_trip(self,trip_id:int)->None:
        self.memory.clear();self.total_distance_m=0.0;self.decision_points.clear();self.active_decision_key=None
        self.previous_snapshot=None;self.pending_redecision=False;self.latest_energy_reading=None
        self.light_turn_locked=False
        self.light_progress_since_turn_m=0.0
        self.experience_decision_recall_count=0
        self.experience_decision_fallback_count=0
        self.trip_decision_ordinal=0
        self.current_trip_id=int(trip_id)
        self.experience.start_trip(trip_id)

    def _save_trip(self,trip_id:int,result:dict)->None:
        suffix=f'trip_{trip_id:02d}'
        self.memory.save(self.trace.run_dir/f'working_memory_{suffix}.json')
        self.experience.save(self.trace.run_dir/f'experience_memory_{suffix}.json')
        (self.trace.run_dir/f'result_{suffix}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')

    def _append_summary(self,trip_id:int,result:dict,start:float,nest:int)->None:
        path=self.trace.run_dir/'trip_summary.csv';header=not path.exists()
        fields=['trip_id','status','endpoint_id','simulation_start_s','simulation_end_s','trip_duration_s','trip_distance_m','home_reached','home_error_m','working_memory_commands','decision_points','world_map_created','nest_energy_after_trip']
        with path.open('a',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=fields)
            if header:w.writeheader()
            w.writerow({'trip_id':trip_id,'status':result['status'],'endpoint_id':result['detected_endpoint_id'],'simulation_start_s':start,
                'simulation_end_s':self.motion.backend.time_s,'trip_duration_s':self.motion.backend.time_s-start,'trip_distance_m':result['total_actual_distance_m'],
                'home_reached':result['home_reached'],'home_error_m':result['home_position_error_m'],'working_memory_commands':result['working_memory_command_count'],
                'decision_points':result['decision_point_count'],'world_map_created':False,'nest_energy_after_trip':nest})

    def run(self)->dict:
        results=[];nest=0;start_all=self.motion.backend.time_s
        for trip_id in range(1,self.config.trip_count+1):
            self._reset_trip(trip_id);start=self.motion.backend.time_s
            if self.hud is not None:
                endpoint = self.energy_sensor.active_endpoint
                self.hud.start_trip(
                    trip_id=trip_id,
                    trip_target=self.config.trip_count,
                    endpoint_id=endpoint.endpoint_id,
                    energy_x_m=endpoint.x_m,
                    energy_y_m=endpoint.y_m,
                    nest_energy_units=nest,
                )
            result=self._run_single_trip();result['trip_id']=trip_id
            if result['home_reached']:
                nest+=1
                if self.config.memory_enabled:
                    result['experience_update']=self.experience.commit_success(source_id=result['detected_endpoint_id'],working_memory=self.memory,
                        outbound_distance_m=result['outbound_distance_m'],total_trip_distance_m=result['total_actual_distance_m'],trip_id=trip_id)
            result['nest_energy_after_trip']=nest;results.append(result);self._save_trip(trip_id,result);self._append_summary(trip_id,result,start,nest)
        final={'status':'PASS','requested_trip_count':self.config.trip_count,'completed_trip_count':len(results),'all_trips_completed':len(results)==self.config.trip_count,
            'nest_energy_units':nest,'carried_energy_units':0,'simulation_start_s':start_all,'simulation_end_s':self.motion.backend.time_s,
            'total_simulation_duration_s':self.motion.backend.time_s-start_all,'total_actual_distance_m':sum(r['total_actual_distance_m'] for r in results),
            'fixed_source_id':self.energy_sensor.active_endpoint.endpoint_id,'working_memory_scope':'CURRENT_TRIP_ONLY',
            'experience_memory_scope':'SUCCESSFUL_ROUTE_ACROSS_TRIPS','world_map_created':False,'navigation_model':'RAT_INSPIRED_ROUTE_MEMORY',
            'experience_memory_snapshot':self.experience.snapshot(),'trip_results':results,'home_reached':all(r['home_reached'] for r in results)}
        self.trace.set_result(final);return final
