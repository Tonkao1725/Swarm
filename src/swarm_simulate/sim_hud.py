from __future__ import annotations

from dataclasses import dataclass
import math

import matplotlib.pyplot as plt
from matplotlib.patches import Circle


@dataclass
class HUDState:
    phase: str = "INITIALIZING"
    activity: str = "Starting simulation"
    energy_visible: bool = False
    energy_detected: bool = False
    energy_collected: bool = False
    carried_energy_units: int = 0
    energy_distance_m: float | None = None
    line_of_sight_clear: bool = False
    inside_sensor_fov: bool = False
    last_action: str = "-"
    junction_id: str = "-"
    working_memory_route: str = "-"
    sim_time_s: float = 0.0
    solar_left: float = 0.0
    solar_center: float = 0.0
    solar_right: float = 0.0
    solar_max: float = 0.0
    strongest_direction: str = "-"
    light_guidance_active: bool = False
    collect_threshold_reached: bool = False
    light_approach_active: bool = False
    light_state: str = "SEARCH"
    decision_seed: int | None = None
    energy_endpoint_id: str = "-"
    trip_id: int = 1
    trip_target: int = 1
    nest_energy_units: int = 0


class SimulationHUD:
    """
    Right-side live status panel and non-physical Energy marker.

    The yellow marker is drawn by Matplotlib only. It is not an IR-SIM
    obstacle, so it cannot block LiDAR, collide with the robot, or alter
    navigation physics.
    """

    def __init__(
        self,
        *,
        energy_x_m: float,
        energy_y_m: float,
        energy_radius_m: float = 0.12,
        decision_seed: int | None = None,
        energy_endpoint_id: str = "-",
        enabled: bool = True,
        trail_minimum_spacing_m: float = 0.04,
        trail_maximum_points: int = 12000,
    ) -> None:
        self.energy_x_m = energy_x_m
        self.energy_y_m = energy_y_m
        self.energy_radius_m = energy_radius_m
        self.enabled = bool(enabled)
        self.state = HUDState(
            energy_visible=True,
            decision_seed=decision_seed,
            energy_endpoint_id=energy_endpoint_id,
        )
        self.trail_minimum_spacing_m = max(
            0.0, float(trail_minimum_spacing_m)
        )
        self.trail_maximum_points = max(
            100, int(trail_maximum_points)
        )

        self._figure = None
        self._map_axes = None
        self._panel_axes = None
        self._marker = None
        self._halo_outer = None
        self._halo_inner = None
        self._text = None
        self._trail_line = None
        self._trail_lines: list = []
        self._trail_x: list[float] = []
        self._trail_y: list[float] = []
        self._trail_trip_id: int | None = None
        self._last_draw_sim_time = -1.0
        self._last_trail_sim_time = -1.0
        self._minimum_draw_interval_s = 0.30
        self._trail_discontinuity_threshold_m = 0.30

    def update(self, **changes) -> None:
        for key, value in changes.items():
            if hasattr(self.state, key):
                setattr(self.state, key, value)

    def _start_new_trip_trail(
        self,
        trip_id: int,
    ) -> None:
        """
        Preserve completed trip trails and create a new line for this trip.

        No explicit color is assigned. Matplotlib advances its normal color
        cycle, so Trip 1, Trip 2, ... are visually distinct.
        """
        if self._trail_trip_id == int(trip_id):
            return

        self._trail_trip_id = int(trip_id)
        self._trail_x = []
        self._trail_y = []

        if self._map_axes is None:
            self._trail_line = None
            return

        (line,) = self._map_axes.plot(
            [],
            [],
            linewidth=1.25,
            alpha=0.80,
            zorder=40,
            label=f"Trip {trip_id}",
        )
        self._trail_line = line
        self._trail_lines.append(line)

    def start_trip(
        self,
        *,
        trip_id: int,
        trip_target: int,
        endpoint_id: str,
        energy_x_m: float,
        energy_y_m: float,
        nest_energy_units: int,
    ) -> None:
        self.energy_x_m = energy_x_m
        self.energy_y_m = energy_y_m
        self._start_new_trip_trail(trip_id)

        self.update(
            phase="EXPLORE",
            activity="Starting new foraging trip",
            energy_visible=True,
            energy_detected=False,
            energy_collected=False,
            carried_energy_units=0,
            energy_distance_m=None,
            line_of_sight_clear=False,
            inside_sensor_fov=False,
            last_action="START_TRIP",
            junction_id="-",
            working_memory_route="-",
            solar_left=0.0,
            solar_center=0.0,
            solar_right=0.0,
            solar_max=0.0,
            strongest_direction="-",
            light_guidance_active=False,
            collect_threshold_reached=False,
            light_approach_active=False,
            light_state="SEARCH",
            energy_endpoint_id=endpoint_id,
            trip_id=trip_id,
            trip_target=trip_target,
            nest_energy_units=nest_energy_units,
        )

        for patch in (
            self._marker,
            self._halo_inner,
            self._halo_outer,
        ):
            if patch is not None:
                patch.center = (energy_x_m, energy_y_m)

    def deposit_at_nest(self, nest_energy_units: int) -> None:
        self.update(
            phase="AT_HOME",
            activity="Energy deposited at NEST",
            carried_energy_units=0,
            nest_energy_units=nest_energy_units,
            last_action="DEPOSIT",
        )

    def collect_energy(self) -> None:
        self.update(
            phase="RETURN_HOME",
            activity="Energy collected — returning HOME",
            energy_detected=True,
            energy_collected=True,
            energy_visible=False,
            carried_energy_units=1,
        )

    def _initialize(self) -> None:
        if not self.enabled or self._panel_axes is not None:
            return

        figure = plt.gcf()
        if not figure.axes:
            return

        self._figure = figure
        self._map_axes = figure.axes[0]

        try:
            figure.subplots_adjust(right=0.75)
        except Exception:
            pass

        self._panel_axes = figure.add_axes(
            [0.77, 0.08, 0.21, 0.84]
        )
        self._panel_axes.set_axis_off()
        self._panel_axes.set_title(
            "ROBOT STATUS",
            fontsize=11,
            fontweight="bold",
            loc="left",
        )

        self._halo_outer = Circle(
            (self.energy_x_m, self.energy_y_m),
            4.50,
            facecolor="yellow",
            edgecolor="none",
            alpha=0.05,
            zorder=45,
        )
        self._map_axes.add_patch(self._halo_outer)

        self._halo_inner = Circle(
            (self.energy_x_m, self.energy_y_m),
            2.25,
            facecolor="yellow",
            edgecolor="gold",
            linewidth=0.8,
            alpha=0.10,
            zorder=46,
        )
        self._map_axes.add_patch(self._halo_inner)

        self._marker = Circle(
            (self.energy_x_m, self.energy_y_m),
            self.energy_radius_m,
            facecolor="yellow",
            edgecolor="goldenrod",
            linewidth=1.5,
            zorder=50,
        )
        self._map_axes.add_patch(self._marker)

        # Trail is display-only. Each Trip owns a separate Matplotlib line.
        # Completed Trip lines remain visible while the next Trip receives the
        # next color from Matplotlib's automatic color cycle.
        initial_trip = max(1, int(self.state.trip_id))
        self._trail_trip_id = None
        self._start_new_trip_trail(initial_trip)

        self._text = self._panel_axes.text(
            0.0,
            0.98,
            "",
            va="top",
            ha="left",
            fontsize=9,
            family="monospace",
            transform=self._panel_axes.transAxes,
        )

    @staticmethod
    def _yes_no(value: bool) -> str:
        return "YES" if value else "NO"

    def _append_trail_pose(
        self,
        pose,
        *,
        sim_time_s: float | None,
    ) -> None:
        if pose is None:
            return

        x_m = float(pose.x_m)
        y_m = float(pose.y_m)

        if self._trail_x:
            last_x = self._trail_x[-1]
            last_y = self._trail_y[-1]

            # NaN marks a previous visual discontinuity.
            if not (
                math.isnan(last_x)
                or math.isnan(last_y)
            ):
                dx = x_m - last_x
                dy = y_m - last_y
                displacement = math.hypot(dx, dy)

                if displacement < self.trail_minimum_spacing_m:
                    return

                # A large sample gap must never be drawn as a straight
                # diagonal. Insert a line break instead.
                if (
                    displacement
                    > self._trail_discontinuity_threshold_m
                ):
                    self._trail_x.append(float("nan"))
                    self._trail_y.append(float("nan"))

        self._trail_x.append(x_m)
        self._trail_y.append(y_m)

        if sim_time_s is not None:
            self._last_trail_sim_time = float(sim_time_s)

        if len(self._trail_x) > self.trail_maximum_points:
            remove_count = len(self._trail_x) - self.trail_maximum_points
            del self._trail_x[:remove_count]
            del self._trail_y[:remove_count]

        if self._trail_line is not None:
            self._trail_line.set_data(
                self._trail_x,
                self._trail_y,
            )

    def render(
        self,
        pose=None,
        sim_time_s: float | None = None,
    ) -> None:
        if not self.enabled:
            return

        self._initialize()
        if self._panel_axes is None:
            return

        # Trail sampling is independent from the expensive HUD redraw.
        # This uses actual backend simulation time, not the Energy/HUD state
        # time which may remain unchanged during a long motion primitive.
        self._append_trail_pose(
            pose,
            sim_time_s=sim_time_s,
        )

        draw_time = (
            float(sim_time_s)
            if sim_time_s is not None
            else float(self.state.sim_time_s)
        )
        if (
            self._last_draw_sim_time >= 0.0
            and draw_time - self._last_draw_sim_time
            < self._minimum_draw_interval_s
        ):
            return
        self._last_draw_sim_time = draw_time

        s = self.state
        distance = (
            f"{s.energy_distance_m:.2f} m"
            if s.energy_distance_m is not None
            else "-"
        )

        lines = [
            f"Seed        : {s.decision_seed if s.decision_seed is not None else '-'}",
            f"Trip        : {s.trip_id}/{s.trip_target}",
            f"Nest Energy : {s.nest_energy_units}",
            f"Energy point: {s.energy_endpoint_id}",
            "",
            f"Phase       : {s.phase}",
            f"Activity    : {s.activity}",
            "",
            f"Energy seen : {self._yes_no(s.energy_detected)}",
            f"Collected   : {self._yes_no(s.energy_collected)}",
            f"Carrying    : {s.carried_energy_units}",
            f"Distance    : {distance}",
            f"Light visible: {self._yes_no(s.inside_sensor_fov)}",
            f"LOS clear   : {self._yes_no(s.line_of_sight_clear)}",
            "",
            f"Solar L     : {s.solar_left:.3f}",
            f"Solar C     : {s.solar_center:.3f}",
            f"Solar R     : {s.solar_right:.3f}",
            f"Light max   : {s.solar_max:.3f}",
            f"Strongest   : {s.strongest_direction}",
            f"Guidance    : {self._yes_no(s.light_guidance_active)}",
            f"Approaching : {self._yes_no(s.light_approach_active)}",
            f"Light state : {s.light_state}",
            f"Collect     : {self._yes_no(s.collect_threshold_reached)}",
            "",
            f"Junction    : {s.junction_id}",
            f"Last action : {s.last_action}",
            f"WM route    : {s.working_memory_route or '-'}",
            "",
            f"Sim time    : {s.sim_time_s:.1f} s",
        ]

        self._text.set_text("\n".join(lines))

        visible = s.energy_visible and not s.energy_collected
        if self._marker is not None:
            self._marker.set_visible(visible)
        if self._halo_inner is not None:
            self._halo_inner.set_visible(visible)
        if self._halo_outer is not None:
            self._halo_outer.set_visible(visible)

        try:
            self._figure.canvas.draw_idle()
        except Exception:
            pass
