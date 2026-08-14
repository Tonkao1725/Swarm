from __future__ import annotations
from dataclasses import asdict, dataclass
from enum import Enum
import os
from typing import Any

class ExperimentMode(str, Enum):
    BASELINE="baseline"
    WORKING_MEMORY="working_memory"
    EXPERIENCE_MEMORY="experience_memory"
    RAT_EXCHANGE="rat_exchange"
    CODE_EXCHANGE="code_exchange"
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
    working_memory_enabled: bool
    experience_memory_enabled: bool
    exchange_enabled: bool
    exchange_type: ExchangeType
    hormone_enabled: bool
    implementation_status: str
    research_description: str

    @property
    def ready_for_valid_experiment(self)->bool:
        return self.implementation_status=="READY"

    # Compatibility names for the controller and historical run metadata.
    # They preserve the old configuration interface while making the two
    # research memory architectures explicit at the experiment boundary.
    @property
    def memory_enabled(self) -> bool:
        return self.working_memory_enabled

    @property
    def route_experience_enabled(self) -> bool:
        return self.experience_memory_enabled

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
        working_memory_enabled=False,
        experience_memory_enabled=False,
        exchange_enabled=False,
        exchange_type=ExchangeType.NONE,
        hormone_enabled=False,
        implementation_status="READY",
        research_description=(
            "No cross-trip memory, no exchange, no hormone."
        ),
    ),
    ExperimentMode.WORKING_MEMORY: ExperimentModeConfig(
        mode=ExperimentMode.WORKING_MEMORY,
        display_name="Working Memory",
        working_memory_enabled=True,
        experience_memory_enabled=False,
        exchange_enabled=False,
        exchange_type=ExchangeType.NONE,
        hormone_enabled=False,
        implementation_status="READY",
        research_description=(
            "Trip-local Working Memory only; no cross-trip experience."
        ),
    ),
    ExperimentMode.EXPERIENCE_MEMORY: ExperimentModeConfig(
        mode=ExperimentMode.EXPERIENCE_MEMORY,
        display_name="Experience Memory",
        working_memory_enabled=True,
        experience_memory_enabled=True,
        exchange_enabled=False,
        exchange_type=ExchangeType.NONE,
        hormone_enabled=False,
        implementation_status="READY",
        research_description=(
            "Trip-local Working Memory plus successful cross-trip "
            "Experience Memory as a probabilistic decision bias."
        ),
    ),
    ExperimentMode.RAT_EXCHANGE: ExperimentModeConfig(
        mode=ExperimentMode.RAT_EXCHANGE,
        display_name="Rat Exchange",
        working_memory_enabled=True,
        experience_memory_enabled=True,
        exchange_enabled=True,
        exchange_type=ExchangeType.RAT_NO_DIRECTION,
        hormone_enabled=False,
        implementation_status="SCAFFOLD_ONLY",
        research_description=(
            "Exchange source quality/status without direction."
        ),
    ),
    ExperimentMode.CODE_EXCHANGE: ExperimentModeConfig(
        mode=ExperimentMode.CODE_EXCHANGE,
        display_name="Code Exchange",
        working_memory_enabled=True,
        experience_memory_enabled=True,
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
        working_memory_enabled=True,
        experience_memory_enabled=True,
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
        "SWARM_EXPERIMENT_MODE",ExperimentMode.EXPERIENCE_MEMORY.value)
    normalized=str(value).strip().lower()
    normalized={
        "1":"baseline", "2":"working_memory", "3":"experience_memory",
        "4":"rat_exchange", "5":"code_exchange", "6":"all",
        "memory_only":"experience_memory", "memory":"experience_memory",
        "wm":"working_memory", "em":"experience_memory",
        "rat":"rat_exchange", "memory_exchange":"code_exchange",
    }.get(normalized,normalized)
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
            "Use baseline, working_memory, or experience_memory now.")
    return cfg

def all_mode_snapshots()->list[dict[str,Any]]:
    return [_MODE_TABLE[m].snapshot() for m in ExperimentMode]
