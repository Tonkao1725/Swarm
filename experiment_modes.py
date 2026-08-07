from __future__ import annotations
from dataclasses import asdict, dataclass
from enum import Enum
import os
from typing import Any

class ExperimentMode(str, Enum):
    BASELINE="baseline"
    MEMORY_ONLY="memory_only"
    RAT_EXCHANGE="rat_exchange"
    MEMORY_EXCHANGE="memory_exchange"
    ALL="all"

class ExchangeType(str, Enum):
    NONE="none"
    RAT_NO_DIRECTION="rat_no_direction"
    DIRECTIONAL_EXPERIENCE="directional_experience"
    BEST_EXPERIENCE="best_experience"

@dataclass(frozen=True)
class ExperimentModeConfig:
    mode: ExperimentMode
    display_name: str
    memory_enabled: bool
    route_experience_enabled: bool
    exchange_enabled: bool
    exchange_type: ExchangeType
    hormone_enabled: bool
    implementation_status: str
    research_description: str

    @property
    def ready_for_valid_experiment(self)->bool:
        return self.implementation_status=="READY"

    def snapshot(self)->dict[str,Any]:
        data=asdict(self)
        data["mode"]=self.mode.value
        data["exchange_type"]=self.exchange_type.value
        data["ready_for_valid_experiment"]=self.ready_for_valid_experiment
        return data

_MODE_TABLE = {
    ExperimentMode.BASELINE: ExperimentModeConfig(
        mode=ExperimentMode.BASELINE,
        display_name="Baseline",
        memory_enabled=False,
        route_experience_enabled=False,
        exchange_enabled=False,
        exchange_type=ExchangeType.NONE,
        hormone_enabled=False,
        implementation_status="READY",
        research_description=(
            "No cross-trip memory, no exchange, no hormone."
        ),
    ),
    ExperimentMode.MEMORY_ONLY: ExperimentModeConfig(
        mode=ExperimentMode.MEMORY_ONLY,
        display_name="Memory Only",
        memory_enabled=True,
        route_experience_enabled=True,
        exchange_enabled=False,
        exchange_type=ExchangeType.NONE,
        hormone_enabled=False,
        implementation_status="READY",
        research_description=(
            "Trip-local Working Memory and persistent successful "
            "decision Experience Memory."
        ),
    ),
    ExperimentMode.RAT_EXCHANGE: ExperimentModeConfig(
        mode=ExperimentMode.RAT_EXCHANGE,
        display_name="Rat Exchange",
        memory_enabled=True,
        route_experience_enabled=True,
        exchange_enabled=True,
        exchange_type=ExchangeType.RAT_NO_DIRECTION,
        hormone_enabled=False,
        implementation_status="SCAFFOLD_ONLY",
        research_description=(
            "Exchange source quality/status without direction."
        ),
    ),
    ExperimentMode.MEMORY_EXCHANGE: ExperimentModeConfig(
        mode=ExperimentMode.MEMORY_EXCHANGE,
        display_name="Memory Exchange",
        memory_enabled=True,
        route_experience_enabled=True,
        exchange_enabled=True,
        exchange_type=ExchangeType.DIRECTIONAL_EXPERIENCE,
        hormone_enabled=False,
        implementation_status="SCAFFOLD_ONLY",
        research_description=(
            "Exchange source information with route/direction."
        ),
    ),
    ExperimentMode.ALL: ExperimentModeConfig(
        mode=ExperimentMode.ALL,
        display_name="All",
        memory_enabled=True,
        route_experience_enabled=True,
        exchange_enabled=True,
        exchange_type=ExchangeType.BEST_EXPERIENCE,
        hormone_enabled=True,
        implementation_status="SCAFFOLD_ONLY",
        research_description=(
            "Memory, best-experience exchange and AIH."
        ),
    ),
}

def resolve_experiment_mode(raw:str|None=None)->ExperimentModeConfig:
    value=raw if raw is not None else os.environ.get(
        "SWARM_EXPERIMENT_MODE",ExperimentMode.MEMORY_ONLY.value)
    normalized=str(value).strip().lower()
    normalized={"1":"baseline","2":"memory_only","3":"rat_exchange",
                "4":"memory_exchange","5":"all","memory":"memory_only",
                "rat":"rat_exchange"}.get(normalized,normalized)
    try:
        mode=ExperimentMode(normalized)
    except ValueError as exc:
        allowed=", ".join(x.value for x in ExperimentMode)
        raise ValueError(f"Unknown SWARM_EXPERIMENT_MODE={value!r}. Allowed: {allowed}") from exc
    cfg=_MODE_TABLE[mode]
    allow=os.environ.get("SWARM_ALLOW_SCAFFOLD_MODES","0").strip().lower() in {
        "1","true","yes","on"}
    if not cfg.ready_for_valid_experiment and not allow:
        raise RuntimeError(
            f"Mode '{mode.value}' is defined but not valid for research runs yet. "
            "It requires multi-robot Encounter/Exchange and/or AIH. "
            "Use baseline or memory_only now.")
    return cfg

def all_mode_snapshots()->list[dict[str,Any]]:
    return [_MODE_TABLE[m].snapshot() for m in ExperimentMode]
