from __future__ import annotations

import inspect

from energy_sensor import (
    EnergyEndpoint,
    RandomEndpointEnergySensor,
)


def main() -> int:
    expected = {
        "endpoints",
        "detection_radius_m",
        "random_seed",
        "line_of_sight_margin_m",
        "visible_marker_radius_m",
        "guidance_threshold",
        "collect_threshold",
        "light_range_scale_m",
        "blocked_light_factor",
        "diffuse_guidance_threshold",
        "maximum_diffuse_guidance_distance_m",
        "angular_exponent",
        "ambient_light",
    }

    signature = inspect.signature(
        RandomEndpointEnergySensor.__init__
    )
    accepted = {
        name
        for name in signature.parameters
        if name != "self"
    }

    missing = sorted(expected - accepted)
    assert not missing, (
        "EnergySensor constructor missing parameters: "
        + ", ".join(missing)
    )

    sensor = RandomEndpointEnergySensor(
        endpoints=(
            EnergyEndpoint(
                "E_FIXED_NE",
                11.875,
                11.875,
            ),
        ),
        detection_radius_m=0.20,
        random_seed=123456,
        line_of_sight_margin_m=0.03,
        visible_marker_radius_m=0.12,
        guidance_threshold=0.001,
        collect_threshold=0.90,
        light_range_scale_m=4.50,
        blocked_light_factor=0.06,
        diffuse_guidance_threshold=0.003,
        maximum_diffuse_guidance_distance_m=7.0,
        angular_exponent=2.0,
        ambient_light=0.0,
    )

    assert sensor.diffuse_guidance_threshold == 0.003
    assert (
        sensor.maximum_diffuse_guidance_distance_m
        == 7.0
    )

    print(
        "PASS: main.py and RandomEndpointEnergySensor "
        "interfaces are synchronized"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
