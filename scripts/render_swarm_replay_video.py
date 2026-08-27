"""Create a presentation replay video from a completed Swarm trajectory log.

The script only reads logs.  It never runs the controller or alters research
results.  The default timing compresses a 3600 s run into roughly 72 seconds.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter
from matplotlib.patches import Circle, Rectangle
import numpy as np
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCOUT_COLORS = {"0": "#078a16", "1": "#1359e8", "2": "#c000c9"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--frame-step-s", type=float, default=5.0)
    parser.add_argument("--fps", type=int, default=10)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    rows = read_csv(run_dir / "swarm_trajectory.csv")
    metadata = yaml.safe_load((PROJECT_ROOT / "config" / "robot_world.yaml").read_text(encoding="utf-8"))
    run_metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    seed = run_metadata["configuration"]["decision_random_seed"]
    resource_config = json.loads((PROJECT_ROOT / "config" / "resource_harvesting_config.json").read_text(encoding="utf-8"))

    traces: dict[str, dict[str, np.ndarray]] = {}
    for scout_id in ("0", "1", "2"):
        scout = [row for row in rows if row["scout_id"] == scout_id]
        traces[scout_id] = {
            "t": np.asarray([float(row["sim_time_s"]) for row in scout]),
            "x": np.asarray([float(row["x_m"]) for row in scout]),
            "y": np.asarray([float(row["y_m"]) for row in scout]),
            "heading": np.asarray([float(row["heading_deg"]) for row in scout]),
            "phase": np.asarray([row["phase"] for row in scout]),
            "trip": np.asarray([row["trip_id"] for row in scout]),
        }
    duration = max(trace["t"][-1] for trace in traces.values())
    frame_times = np.arange(0.0, duration + args.frame_step_s, args.frame_step_s)
    # Keep the exported replay deliberately uncluttered for presentation:
    # the maze, sources, robot motion, and a single simulation-time readout.
    fig = plt.figure(figsize=(9.2, 9.2), facecolor="white")
    ax = fig.add_axes([0.10, 0.08, 0.84, 0.84])
    ax.set_aspect("equal")
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 14)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    for obstacle in metadata["obstacle"]:
        shape = obstacle["shape"]
        x, y, _ = obstacle["state"]
        ax.add_patch(Rectangle((x - shape["length"] / 2, y - shape["width"] / 2),
                               shape["length"], shape["width"], color="black", zorder=1))
    ax.add_patch(Circle((1, 1), 0.38, fill=False, edgecolor="#008d1a", linewidth=2.4, zorder=3))
    ax.text(1, 1.53, "NEST", color="#008d1a", ha="center", weight="bold", fontsize=10)
    for source in resource_config["sources"]:
        x, y = source["x_m"], source["y_m"]
        ax.add_patch(Circle((x, y), 0.18, facecolor="#ffdc22", edgecolor="#e58d00", linewidth=2, zorder=3))
        ax.text(x, y + 0.30, f"ENERGY {source['resource_id']}", color="#e57900", ha="center", weight="bold", fontsize=8)

    trails = {sid: ax.plot([], [], color=SCOUT_COLORS[sid], alpha=0.48, linewidth=1.35, zorder=2)[0]
              for sid in traces}
    robots = {sid: ax.plot([], [], "o", color=SCOUT_COLORS[sid], markersize=16, zorder=5)[0]
              for sid in traces}
    arrows = {sid: ax.plot([], [], color="#ffd400", linewidth=2.8, zorder=6)[0] for sid in traces}
    time_text = ax.text(7, 14.28, "", ha="center", va="bottom", fontsize=15, weight="bold")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    writer = FFMpegWriter(fps=args.fps, bitrate=2500, metadata={
        "title": f"Swarm Baseline Replay — seed {seed}", "artist": "SwarmSimulate",
        "comment": "Replay from recorded CSV trajectory; no controller rerun."
    })
    with writer.saving(fig, str(args.output), dpi=110):
        for t in frame_times:
            for i, sid in enumerate(("0", "1", "2")):
                trace = traces[sid]
                idx = max(0, np.searchsorted(trace["t"], t, side="right") - 1)
                stride = 10  # recorded every 0.1 s -> 1 s trail samples
                trails[sid].set_data(trace["x"][:idx + 1:stride], trace["y"][:idx + 1:stride])
                x, y = trace["x"][idx], trace["y"][idx]
                heading = math.radians(trace["heading"][idx])
                phase = trace["phase"][idx]
                carrying = phase == "RETURN_HOME"
                robots[sid].set_data([x], [y])
                arrow_color = "#df2020" if carrying else "#ffd400"
                arrows[sid].set_color(arrow_color)
                arrows[sid].set_data([x, x + 0.34 * math.cos(heading)], [y, y + 0.34 * math.sin(heading)])
            time_text.set_text(f"Simulation time: {t:,.0f} s")
            writer.grab_frame()
    plt.close(fig)


if __name__ == "__main__":
    main()
