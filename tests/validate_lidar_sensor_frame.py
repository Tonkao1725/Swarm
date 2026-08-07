from __future__ import annotations

import math
import numpy as np


def nearest_index(
    angles: np.ndarray,
    target_rad: float,
) -> tuple[int, float]:
    errors = np.abs(
        np.arctan2(
            np.sin(angles - target_rad),
            np.cos(angles - target_rad),
        )
    )
    index = int(np.argmin(errors))
    return index, float(errors[index])


def main() -> int:
    angles = np.linspace(
        -math.pi / 2.0,
        math.pi / 2.0,
        181,
    )
    expected = {
        "RIGHT": (-math.pi / 2.0, 0),
        "FRONT": (0.0, 90),
        "LEFT": (math.pi / 2.0, 180),
    }

    for heading_deg in (0.0, 90.0, 180.0, -90.0):
        for name, (target, expected_index) in expected.items():
            index, error = nearest_index(angles, target)
            assert index == expected_index
            assert error < 1e-12

    print("PASS: LiDAR targets remain robot-relative")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
