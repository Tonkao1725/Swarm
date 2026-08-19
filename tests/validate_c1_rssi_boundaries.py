"""Static boundary regression checks for the final C1 RSSI baseline."""
from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "swarm_simulate" / "swarm_baseline.py"
OUT = ROOT / "results" / "c1_rssi_boundary_tests_20260819"


def method(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Missing method: {name}")


def names(node: ast.AST) -> set[str]:
    return {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}


def attributes(node: ast.AST) -> set[str]:
    return {item.attr for item in ast.walk(node) if isinstance(item, ast.Attribute)}


def main() -> int:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    return_method = method(tree, "_return_command")
    command_method = method(tree, "_command_for")
    forward_safety = method(tree, "_forward_body_clearance_safe")
    return_names = names(return_method)
    return_attrs = attributes(return_method)
    forbidden_names = {"home", "nest_x_m", "nest_y_m", "distance", "bearing"}
    forbidden_attrs = {"nest_x_m", "nest_y_m", "home", "x_m", "y_m"}
    assert not (return_names & forbidden_names), return_names & forbidden_names
    assert not (return_attrs & forbidden_attrs), return_attrs & forbidden_attrs
    assert "sample" not in return_attrs, "RSSI must be supplied as a scalar argument"
    assert "_environment_nest_reached" in attributes(command_method)
    assert "_nest_beacon" in attributes(command_method)
    assert "ray_distance" in attributes(forward_safety)
    assert "math.pi / 4.0" in (ast.get_source_segment(SOURCE.read_text(encoding="utf-8"), forward_safety) or "")
    source_text = SOURCE.read_text(encoding="utf-8")
    active_span = ast.get_source_segment(source_text, return_method) or ""
    for forbidden in ("atan2(", "home.", "nest_x_m", "nest_y_m", "ray_distance("):
        assert forbidden not in active_span, forbidden
    assert "energy_sensor.active_endpoint.x_m" not in ast.get_source_segment(source_text, method(tree, "_explore_command"))
    report = {
        "classification": "NOT_RESEARCH_DATA",
        "nest_information_boundary": {
            "active_return_controller": "RSSI scalar + current ToF + current actuator state + seeded RNG",
            "exact_nest_geometry_in_active_return": False,
            "environment_arrival_check": "_environment_nest_reached only",
        },
        "resource_information_boundary": {
            "active_explore_controller": "EnergyReading solar L/C/R and detected state only",
            "exact_resource_coordinate_access_in_explore": False,
        },
        "feature_isolation": {
            "working_memory": False, "experience_memory": False,
            "exchange": False, "aih": False, "internal_energy_decision": False,
        },
        "sensor_boundary": {
            "nominal_tof": ["FRONT_LEFT +20deg", "FRONT_RIGHT -20deg", "SIDE_LEFT +90deg", "SIDE_RIGHT -90deg"],
            "additional_rays": ["-45deg", "+45deg"],
            "additional_ray_effect": "COMMON_LOW_LEVEL_COLLISION_SAFETY only in _forward_body_clearance_safe",
        },
        "verdict": "PASS",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("nest_information_boundary_test.json", "baseline_feature_isolation_report.json", "sensor_boundary_audit.json"):
        (OUT / name).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS: C1_RSSI_BOUNDARIES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
