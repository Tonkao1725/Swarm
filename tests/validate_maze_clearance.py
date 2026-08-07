from __future__ import annotations

CLEAR_CORRIDOR_WIDTH_M = 1.820000
ROBOT_DIAMETER_M = 0.500000
TWO_ROBOT_WIDTH_M = 1.000000
REMAINING_CLEARANCE_M = 0.820000

def main() -> int:
    assert CLEAR_CORRIDOR_WIDTH_M > TWO_ROBOT_WIDTH_M
    assert REMAINING_CLEARANCE_M > 0.30

    print("PASS: two-robot straight-corridor clearance")
    print(f"clear corridor width = {CLEAR_CORRIDOR_WIDTH_M:.3f} m")
    print(f"two robot width      = {TWO_ROBOT_WIDTH_M:.3f} m")
    print(f"remaining clearance  = {REMAINING_CLEARANCE_M:.3f} m")
    print(
        "Note: corner right-of-way still requires multi-robot avoidance logic."
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
