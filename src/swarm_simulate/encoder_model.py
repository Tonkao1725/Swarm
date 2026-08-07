from __future__ import annotations

import math
from dataclasses import dataclass

@dataclass(frozen=True)
class EncoderConfig:
    """
    Encoder resolution per wheel revolution.

    ticks_per_revolution must later be replaced by the measured effective
    count from the real motor encoder, including gearbox multiplication.
    """
    ticks_per_revolution: int = 600

@dataclass(frozen=True)
class EncoderSample:
    delta_left_ticks: int
    delta_right_ticks: int
    cumulative_left_ticks: int
    cumulative_right_ticks: int
    exact_left_ticks: float
    exact_right_ticks: float
    left_quantization_error_ticks: float
    right_quantization_error_ticks: float


class EncoderSimulator:
    """
    Converts wheel angular displacement into integer encoder ticks.

    Quantization is applied to cumulative counts, preserving fractional
    progress internally so small movements are not permanently discarded.
    """

    def __init__(self, config: EncoderConfig) -> None:
        if config.ticks_per_revolution <= 0:
            raise ValueError(
                "ticks_per_revolution must be greater than zero."
            )

        self.config = config
        self._exact_left_ticks = 0.0
        self._exact_right_ticks = 0.0
        self._reported_left_ticks = 0
        self._reported_right_ticks = 0

    def update(
        self,
        left_wheel_radps: float,
        right_wheel_radps: float,
        dt_s: float,
    ) -> EncoderSample:
        if dt_s <= 0:
            raise ValueError("dt_s must be greater than zero.")

        ticks_per_rad = (
            self.config.ticks_per_revolution / (2.0 * math.pi)
        )

        self._exact_left_ticks += (
            left_wheel_radps * dt_s * ticks_per_rad
        )
        self._exact_right_ticks += (
            right_wheel_radps * dt_s * ticks_per_rad
        )

        new_left = int(round(self._exact_left_ticks))
        new_right = int(round(self._exact_right_ticks))

        delta_left = new_left - self._reported_left_ticks
        delta_right = new_right - self._reported_right_ticks

        self._reported_left_ticks = new_left
        self._reported_right_ticks = new_right

        return EncoderSample(
            delta_left_ticks=delta_left,
            delta_right_ticks=delta_right,
            cumulative_left_ticks=new_left,
            cumulative_right_ticks=new_right,
            exact_left_ticks=self._exact_left_ticks,
            exact_right_ticks=self._exact_right_ticks,
            left_quantization_error_ticks=(
                new_left - self._exact_left_ticks
            ),
            right_quantization_error_ticks=(
                new_right - self._exact_right_ticks
            ),
        )
