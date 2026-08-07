from __future__ import annotations

from pathlib import Path

from energy_sensor import EnergyEndpoint


def build_runtime_world(
    *,
    base_world_path: Path,
    runtime_world_path: Path,
    active_energy: EnergyEndpoint,
) -> Path:
    """
    Build the run-specific world without adding Energy as an obstacle.

    Energy visualization is handled by SimulationHUD. This prevents the
    visible marker from affecting LiDAR, collision detection, or navigation.
    """
    base_text = base_world_path.read_text(
        encoding="utf-8"
    ).rstrip()

    comment = (
        "\n\n"
        f"# ACTIVE ENERGY SOURCE FOR HUD: "
        f"{active_energy.endpoint_id} "
        f"({active_energy.x_m:.6f}, "
        f"{active_energy.y_m:.6f})\n"
    )

    runtime_world_path.write_text(
        base_text + comment,
        encoding="utf-8",
    )
    return runtime_world_path
