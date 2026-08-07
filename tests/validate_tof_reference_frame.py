from __future__ import annotations

import math


def wrap(angle_rad: float) -> float:
    return math.atan2(
        math.sin(angle_rad),
        math.cos(angle_rad),
    )


def targets(heading_deg: float) -> dict[str, float]:
    heading = math.radians(heading_deg)
    return {
        "LEFT": math.degrees(
            wrap(heading + math.pi / 2.0)
        ),
        "FRONT": math.degrees(wrap(heading)),
        "RIGHT": math.degrees(
            wrap(heading - math.pi / 2.0)
        ),
    }


def main() -> int:
    expected = {
        0.0: {
            "LEFT": 90.0,
            "FRONT": 0.0,
            "RIGHT": -90.0,
        },
        90.0: {
            "LEFT": 180.0,
            "FRONT": 90.0,
            "RIGHT": 0.0,
        },
        180.0: {
            "LEFT": -90.0,
            "FRONT": 180.0,
            "RIGHT": 90.0,
        },
        -90.0: {
            "LEFT": 0.0,
            "FRONT": -90.0,
            "RIGHT": -180.0,
        },
    }

    for heading, values in expected.items():
        actual = targets(heading)
        for name, expected_deg in values.items():
            error = abs(
                wrap(
                    math.radians(
                        actual[name] - expected_deg
                    )
                )
            )
            assert error < 1e-9, (
                heading,
                name,
                actual[name],
                expected_deg,
            )

    print("PASS: robot-relative ToF bearings rotate with heading")
    for heading in expected:
        print(heading, targets(heading))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
