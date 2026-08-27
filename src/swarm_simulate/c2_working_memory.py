"""Bounded, cycle-local odometric Working Memory for Condition 2.

This module deliberately has no environment, sensor, Nest, Resource, or RNG
dependency.  It stores a Scout's *own* executed outbound displacement in an
arbitrary local frame.  It is therefore neither a map nor a source of global
geometry; the controller can only retrace waypoints it physically recorded in
the active cycle.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


def wrap(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


@dataclass(frozen=True)
class WMEntry:
    cycle_id: int
    x_m: float
    y_m: float


class CycleWorkingMemory:
    """Sparse local breadcrumbs, bounded to one foraging cycle.

    Entries are recorded in a reset-at-Nest odometric frame.  The newest
    breadcrumb is consumed first during return; it is never available after
    :meth:`reset`.  Pruning removes oldest non-origin entries only, preserving
    the cycle origin as the last retrace target.
    """

    def __init__(self, *, enabled: bool, maximum_entries: int = 300,
                 spacing_m: float = 0.25) -> None:
        self.enabled = bool(enabled)
        self.maximum_entries = int(maximum_entries)
        self.spacing_m = float(spacing_m)
        self.entries: list[WMEntry] = []
        self.x_m = 0.0
        self.y_m = 0.0
        self.heading_rad = 0.0
        self.cycle_id: int | None = None
        self.read_count = 0
        self.pop_count = 0
        self.prune_count = 0
        self.reset_count = 0
        self.max_size = 0
        self.skip_count = 0

    @property
    def size(self) -> int:
        return len(self.entries) if self.enabled else 0

    def start_cycle(self, cycle_id: int) -> bool:
        """Start with exactly one local origin breadcrumb."""
        if not self.enabled:
            return False
        self.entries = [WMEntry(int(cycle_id), 0.0, 0.0)]
        self.x_m = self.y_m = self.heading_rad = 0.0
        self.cycle_id = int(cycle_id)
        self.max_size = max(self.max_size, len(self.entries))
        return True

    def update_executed_motion(self, *, moved_m: float, heading_delta_rad: float,
                               cycle_id: int, record_breadcrumb: bool = True) -> str | None:
        """Integrate executed odometry, optionally recording outbound crumbs.

        Return movement must update the same local odometric pose so heading
        error toward the next stored waypoint is meaningful, but it must never
        append new breadcrumbs.
        """
        if not self.enabled or self.cycle_id != int(cycle_id):
            return None
        self.heading_rad = wrap(self.heading_rad + float(heading_delta_rad))
        if moved_m <= 1e-9:
            return None
        self.x_m += float(moved_m) * math.cos(self.heading_rad)
        self.y_m += float(moved_m) * math.sin(self.heading_rad)
        if not record_breadcrumb:
            return None
        last = self.entries[-1]
        if math.hypot(self.x_m - last.x_m, self.y_m - last.y_m) < self.spacing_m:
            return None
        self.entries.append(WMEntry(int(cycle_id), self.x_m, self.y_m))
        operation = "WM_ADD"
        if len(self.entries) > self.maximum_entries:
            # Keep the current-cycle origin plus the newest route portion.
            del self.entries[1]
            self.prune_count += 1
            operation = "WM_PRUNE"
        self.max_size = max(self.max_size, len(self.entries))
        return operation

    def return_target(self, cycle_id: int) -> tuple[float, float] | None:
        if not self.enabled or self.cycle_id != int(cycle_id) or not self.entries:
            return None
        self.read_count += 1
        target = self.entries[-1]
        return target.x_m, target.y_m

    def pop_if_reached(self, cycle_id: int, *, tolerance_m: float = 0.28) -> bool:
        if not self.enabled or self.cycle_id != int(cycle_id) or not self.entries:
            return False
        target = self.entries[-1]
        if math.hypot(self.x_m - target.x_m, self.y_m - target.y_m) > tolerance_m:
            return False
        if len(self.entries) > 1:
            self.entries.pop()
            self.pop_count += 1
            return True
        return False

    def skip_unreachable(self, cycle_id: int) -> bool:
        """Route reacquisition (F3 correction): drop the current retrace
        target when the caller has determined -- from its own bounded,
        deterministic progress tracking -- that it is not being reached.

        This reuses the exact same LIFO pop used by :meth:`pop_if_reached`
        and the exact same guard: the final current-cycle origin entry is
        never removed this way either, so route reacquisition can never
        erase the one waypoint the F4 correction depends on.  It adds no
        new breadcrumb, coordinate, or path -- only an alternate reason to
        advance to the next-older breadcrumb already recorded this cycle.
        """
        if not self.enabled or self.cycle_id != int(cycle_id) or not self.entries:
            return False
        if len(self.entries) > 1:
            self.entries.pop()
            self.skip_count += 1
            return True
        return False

    def reset(self) -> bool:
        if not self.enabled:
            return False
        self.entries.clear()
        self.x_m = self.y_m = self.heading_rad = 0.0
        self.cycle_id = None
        self.reset_count += 1
        return True
