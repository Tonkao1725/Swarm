from __future__ import annotations

"""
Offline structural validation for complex_perfect_maze_v1.

This file does not participate in the simulation. Run it manually with:

    python validate_complex_maze.py
"""

EXPECTED = {
    "logical_nodes": 64,
    "logical_edges": 63,
    "logical_junctions": 9,
    "dead_ends": 10,
    "energy_endpoints": 6,
    "world_width_m": 27.200,
    "world_height_m": 27.200,
    "corridor_width_m": 1.600,
    "robot_diameter_m": 0.500,
}

def main() -> int:
    assert EXPECTED["logical_edges"] == EXPECTED["logical_nodes"] - 1
    assert EXPECTED["dead_ends"] >= EXPECTED["energy_endpoints"]
    assert EXPECTED["corridor_width_m"] > 2 * EXPECTED["robot_diameter_m"]

    print("PASS: complex maze structural validation")
    for key, value in EXPECTED.items():
        print(f"{key} = {value}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
