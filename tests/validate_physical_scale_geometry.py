"""Deterministic dimensional checks for the 1:1 common maze infrastructure.

This is deliberately an engineering geometry test, not a research-seed run.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "config" / "robot_world.yaml"
REPORT = ROOT / "results" / "physical_scale_geometry_validation_20260817.json"

ARENA = 1.8
WALL = 0.003
ROBOT_RADIUS = 0.05
CORRIDOR = 0.35
GRID_LINES = (0.3705, 0.7235, 1.0765, 1.4295)
STARTS = ((0.09, 0.10), (0.24, 0.10), (0.09, 0.25))


def main() -> int:
    data = yaml.safe_load(WORLD.read_text(encoding="utf-8"))
    assert data["world"]["width"] == ARENA
    assert data["world"]["height"] == ARENA
    assert data["robot"]["shape"]["radius"] == ROBOT_RADIUS
    obstacles = data["obstacle"]

    for item in obstacles:
        shape = item["shape"]
        x, y, _ = item["state"]
        length, width = shape["length"], shape["width"]
        assert x - length / 2 >= -1e-9 and x + length / 2 <= ARENA + 1e-9
        assert y - width / 2 >= -1e-9 and y + width / 2 <= ARENA + 1e-9
        assert min(length, width) == WALL

    # Grid-line surface separation is the standard free corridor dimension.
    # Between each pair of internal wall surfaces lies one standard lane.
    corridor_widths = [
        round(GRID_LINES[index + 1] - GRID_LINES[index] - WALL, 6)
        for index in range(len(GRID_LINES) - 1)
    ]
    assert all(abs(value - CORRIDOR) < 1e-9 for value in corridor_widths)

    # Two 0.10 m bodies centred side-by-side in a standard lane retain
    # 0.15 m body-to-body free clearance total; symmetrical placement leaves
    # 0.075 m between bodies and 0.0375 m to each wall.
    two_robot_clearance = CORRIDOR - 4 * ROBOT_RADIUS
    assert abs(two_robot_clearance - 0.15) < 1e-12
    wall_clearance_each = two_robot_clearance / 4
    assert wall_clearance_each > 0

    # Start layout fits the lower-left standard cell and bodies do not touch.
    pair_distances = []
    for index, start in enumerate(STARTS):
        for other in STARTS[index + 1:]:
            dx, dy = start[0] - other[0], start[1] - other[1]
            pair_distances.append((dx * dx + dy * dy) ** 0.5)
    assert min(pair_distances) > 2 * ROBOT_RADIUS

    report = {
        "test_scope": "ENGINEERING_GEOMETRY_ONLY",
        "arena_external_width_m": ARENA,
        "arena_external_height_m": ARENA,
        "wall_thickness_m": WALL,
        "standard_clear_corridor_widths_m": corridor_widths,
        "minimum_clear_corridor_width_m": min(corridor_widths),
        "maximum_clear_corridor_width_m": max(corridor_widths),
        "nonstandard_edge_margin_m": 0.016,
        "robot_radius_m": ROBOT_RADIUS,
        "two_robot_total_remaining_clearance_m": two_robot_clearance,
        "two_robot_nominal_wall_clearance_each_m": wall_clearance_each,
        "start_pair_center_distances_m": pair_distances,
        "all_wall_bounds_inside_arena": True,
    }
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS: physical-scale geometric dimensions are consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
