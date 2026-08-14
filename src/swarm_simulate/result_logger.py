from __future__ import annotations

import csv, json, math, platform, shutil, sys, traceback
from datetime import datetime
from pathlib import Path
from typing import Any
import matplotlib.pyplot as plt

from encoder_model import EncoderSample
from imperfection_model import PhysicalWheelState
from motion_types import MotionCommandResult, RobotPose, StepTelemetry
from odometry import OdometrySample
from wheel_model import WheelCommand


class RunLogger:
    def __init__(
        self,
        project_root: Path,
        env,
        config: dict[str, Any],
        *,
        results_root: Path | None = None,
        run_id: str | None = None,
    ) -> None:
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        base = results_root if results_root is not None else project_root / 'results'
        safe_run_id = (run_id or f'run_{stamp}').strip()
        if not safe_run_id:
            safe_run_id = f'run_{stamp}'
        self.run_dir = base / safe_run_id
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.env, self.status = env, 'RUNNING'
        self.summary_extra: dict[str, Any] = {}
        self.step_count = self.command_count = self.wheel_limit_count = 0
        self.total_distance_m = 0.0
        self.max_odom_position_error_m = self.max_odom_heading_error_deg = 0.0
        self.max_forward_heading_deviation_deg = 0.0
        self.start_state = self._state()
        self.last_state = self.start_state.copy()
        self.final_estimated_pose = RobotPose(*self.start_state)
        self._files, self._writers = {}, {}
        schemas = {
            'trajectory.csv':['step','sim_time_s','action','motion_phase','ground_truth_x_m','ground_truth_y_m','ground_truth_theta_deg','estimated_x_m','estimated_y_m','estimated_theta_deg','cumulative_ground_truth_distance_m'],
            'wheel.csv':['step','sim_time_s','requested_left_radps','requested_right_radps','limited_left_radps','limited_right_radps','wheel_speed_limited','wheel_scale_factor'],
            'imperfection.csv':['step','sim_time_s','action','commanded_left_radps','commanded_right_radps','physical_left_radps','physical_right_radps','left_motor_gain','right_motor_gain','left_wheel_radius_m','right_wheel_radius_m','left_linear_speed_mps','right_linear_speed_mps','physical_linear_velocity_mps','physical_angular_velocity_radps'],
            'encoder.csv':['step','sim_time_s','delta_left_ticks','delta_right_ticks','cumulative_left_ticks','cumulative_right_ticks','left_quantization_error_ticks','right_quantization_error_ticks'],
            'odometry.csv':['step','sim_time_s','estimated_x_m','estimated_y_m','estimated_theta_deg','ground_truth_x_m','ground_truth_y_m','ground_truth_theta_deg','position_error_m','heading_error_deg'],
            'events.csv':['sim_time_s','event','detail'],
            'movement.csv':['command_index','command','target_value','actual_value','error_value','unit','duration_s','start_x_m','start_y_m','start_theta_deg','end_x_m','end_y_m','end_theta_deg'],
        }
        for name, fields in schemas.items():
            f=(self.run_dir/name).open('w',newline='',encoding='utf-8'); w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
            self._files[name],self._writers[name]=f,w
        self._write_json('metadata.json', {'created_at':datetime.now().isoformat(timespec='seconds'),'python_version':sys.version,'platform':platform.platform(),'configuration':config})
        self.log_event('RUN_START','Simulation initialized.')

    def _state(self):
        v=self.env.get_robot_state().reshape(-1); return [float(v[0]),float(v[1]),float(v[2])]

    @staticmethod
    def _angle_error(est,truth):
        return math.atan2(math.sin(est-truth),math.cos(est-truth))

    def snapshot_sources(self, paths):
        d=self.run_dir/'source_snapshot'; d.mkdir(exist_ok=True)
        for p in paths:
            if p.exists() and p.is_file(): shutil.copy2(p,d/p.name)

    def log_step(self, telemetry:StepTelemetry, wheel:WheelCommand, physical:PhysicalWheelState, encoder:EncoderSample, odometry:OdometrySample, truth:RobotPose):
        self.step_count += 1; step=self.step_count; t=round(float(self.env.time),6)
        self.total_distance_m += math.hypot(truth.x_m-self.last_state[0],truth.y_m-self.last_state[1]); self.last_state=[truth.x_m,truth.y_m,truth.theta_rad]
        self.final_estimated_pose=odometry.estimated_pose
        if wheel.wheel_speed_limited: self.wheel_limit_count += 1
        pos_err=math.hypot(odometry.estimated_pose.x_m-truth.x_m,odometry.estimated_pose.y_m-truth.y_m)
        head_err=math.degrees(self._angle_error(odometry.estimated_pose.theta_rad,truth.theta_rad))
        self.max_odom_position_error_m=max(self.max_odom_position_error_m,pos_err); self.max_odom_heading_error_deg=max(self.max_odom_heading_error_deg,abs(head_err))
        self._writers['trajectory.csv'].writerow({'step':step,'sim_time_s':t,'action':telemetry.action_name,'motion_phase':telemetry.motion_phase,'ground_truth_x_m':truth.x_m,'ground_truth_y_m':truth.y_m,'ground_truth_theta_deg':math.degrees(truth.theta_rad),'estimated_x_m':odometry.estimated_pose.x_m,'estimated_y_m':odometry.estimated_pose.y_m,'estimated_theta_deg':math.degrees(odometry.estimated_pose.theta_rad),'cumulative_ground_truth_distance_m':self.total_distance_m})
        self._writers['wheel.csv'].writerow({'step':step,'sim_time_s':t,'requested_left_radps':wheel.requested_left_wheel_radps,'requested_right_radps':wheel.requested_right_wheel_radps,'limited_left_radps':wheel.applied_left_wheel_radps,'limited_right_radps':wheel.applied_right_wheel_radps,'wheel_speed_limited':wheel.wheel_speed_limited,'wheel_scale_factor':wheel.wheel_scale_factor})
        self._writers['imperfection.csv'].writerow({'step':step,'sim_time_s':t,'action':telemetry.action_name,'commanded_left_radps':physical.commanded_left_wheel_radps,'commanded_right_radps':physical.commanded_right_wheel_radps,'physical_left_radps':physical.physical_left_wheel_radps,'physical_right_radps':physical.physical_right_wheel_radps,'left_motor_gain':physical.left_motor_gain,'right_motor_gain':physical.right_motor_gain,'left_wheel_radius_m':physical.left_wheel_radius_m,'right_wheel_radius_m':physical.right_wheel_radius_m,'left_linear_speed_mps':physical.left_linear_speed_mps,'right_linear_speed_mps':physical.right_linear_speed_mps,'physical_linear_velocity_mps':physical.physical_linear_velocity_mps,'physical_angular_velocity_radps':physical.physical_angular_velocity_radps})
        self._writers['encoder.csv'].writerow({'step':step,'sim_time_s':t,'delta_left_ticks':encoder.delta_left_ticks,'delta_right_ticks':encoder.delta_right_ticks,'cumulative_left_ticks':encoder.cumulative_left_ticks,'cumulative_right_ticks':encoder.cumulative_right_ticks,'left_quantization_error_ticks':encoder.left_quantization_error_ticks,'right_quantization_error_ticks':encoder.right_quantization_error_ticks})
        self._writers['odometry.csv'].writerow({'step':step,'sim_time_s':t,'estimated_x_m':odometry.estimated_pose.x_m,'estimated_y_m':odometry.estimated_pose.y_m,'estimated_theta_deg':math.degrees(odometry.estimated_pose.theta_rad),'ground_truth_x_m':truth.x_m,'ground_truth_y_m':truth.y_m,'ground_truth_theta_deg':math.degrees(truth.theta_rad),'position_error_m':pos_err,'heading_error_deg':head_err})
        if step % 10 == 0:
            for n in [
                'trajectory.csv', 'wheel.csv', 'imperfection.csv',
                'encoder.csv', 'odometry.csv'
            ]:
                self._files[n].flush()

    def log_movement(self,result:MotionCommandResult):
        self.command_count += 1
        unit='rad' if result.command.startswith('TURN') else ('s' if result.command=='STOP' else 'm')
        self._writers['movement.csv'].writerow({'command_index':self.command_count,'command':result.command,'target_value':result.target_value,'actual_value':result.actual_value,'error_value':result.error_value,'unit':unit,'duration_s':result.duration_s,'start_x_m':result.start_pose.x_m,'start_y_m':result.start_pose.y_m,'start_theta_deg':math.degrees(result.start_pose.theta_rad),'end_x_m':result.end_pose.x_m,'end_y_m':result.end_pose.y_m,'end_theta_deg':math.degrees(result.end_pose.theta_rad)})
        self._files['movement.csv'].flush()

    def log_event(self,event,detail=''):
        self._writers['events.csv'].writerow({'sim_time_s':round(float(self.env.time),6),'event':event,'detail':detail}); self._files['events.csv'].flush()

    def save_final_figure(self):
        try: plt.gcf().savefig(self.run_dir/'final_state.png',dpi=160,bbox_inches='tight')
        except Exception as exc: self.log_event('FIGURE_SAVE_FAILED',f'{type(exc).__name__}: {exc}')

    def mark_success(self): self.status='SUCCESS'; self.log_event('RUN_COMPLETE','Simulation completed normally.')
    def mark_completed(self, *, mission_outcome: str, experimental_validity: str):
        """Record a completed experiment without equating it to mission success."""
        self.status = 'COMPLETED'
        self.summary_extra = {
            'engineering_status': 'COMPLETED',
            'mission_outcome': str(mission_outcome),
            'experimental_validity': str(experimental_validity),
        }
        self.log_event(
            'RUN_COMPLETE',
            f"engineering=COMPLETED; mission={mission_outcome}; validity={experimental_validity}",
        )
    def mark_failure(self,exc):
        self.status='FAILED'; (self.run_dir/'error_traceback.txt').write_text(''.join(traceback.format_exception(type(exc),exc,exc.__traceback__)),encoding='utf-8'); self.log_event('RUN_FAILED',f'{type(exc).__name__}: {exc}')

    def close(self):
        truth=RobotPose(*self.last_state); est=self.final_estimated_pose
        summary = {
            'status':self.status,'steps':self.step_count,'commands':self.command_count,'simulation_time_s':round(float(self.env.time),6),'total_ground_truth_distance_m':round(self.total_distance_m,10),'wheel_speed_limit_steps':self.wheel_limit_count,
            'ground_truth_start_pose':{'x_m':self.start_state[0],'y_m':self.start_state[1],'theta_rad':self.start_state[2]},
            'ground_truth_final_pose':{'x_m':truth.x_m,'y_m':truth.y_m,'theta_rad':truth.theta_rad},
            'ground_truth_closure_error_m':round(math.hypot(truth.x_m-self.start_state[0],truth.y_m-self.start_state[1]),10),
            'ground_truth_closure_heading_error_deg':round(math.degrees(self._angle_error(truth.theta_rad,self.start_state[2])),8),
            'odometry_final_pose':{'x_m':est.x_m,'y_m':est.y_m,'theta_rad':est.theta_rad},
            'final_odometry_position_error_m':round(math.hypot(est.x_m-truth.x_m,est.y_m-truth.y_m),10),
            'final_odometry_heading_error_deg':round(math.degrees(self._angle_error(est.theta_rad,truth.theta_rad)),8),
            'max_odometry_position_error_m':round(self.max_odom_position_error_m,10),'max_odometry_heading_error_deg':round(self.max_odom_heading_error_deg,8),
        }
        summary.update(self.summary_extra)
        self._write_json('summary.json', summary)
        for f in self._files.values(): f.close()

    def _write_json(self,name,data): (self.run_dir/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
