from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .information_requirements import InformationNeed
from .reality_observation import PhysicalObservation


@dataclass(frozen=True)
class ObservationSource:
    source_id: str
    observation_types: tuple[str, ...]
    adapter: Any
    reliability: float = 1.0
    estimated_cost: float = 0.0
    latency_seconds: float = 0.0
    independence_group: str | None = None
    asset_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.reliability <= 1.0:
            raise ValueError("reliability must be in [0,1]")
        if self.estimated_cost < 0 or self.latency_seconds < 0:
            raise ValueError("cost and latency must be non-negative")

    def supports(self, need: InformationNeed) -> bool:
        return (
            need.observation_type in self.observation_types
            and (not self.asset_ids or need.asset_id in self.asset_ids)
        )


@dataclass(frozen=True)
class AcquisitionTask:
    need_id: str
    asset_id: str
    observation_type: str
    source_id: str
    score: float


@dataclass(frozen=True)
class AcquisitionResult:
    task: AcquisitionTask
    observations: tuple[PhysicalObservation, ...]
    status: str
    error: str | None = None


class AcquisitionPlanner:
    def __init__(
        self,
        *,
        max_sources_per_need: int = 2,
        latency_weight: float = 0.01,
        cost_weight: float = 1.0,
    ) -> None:
        if max_sources_per_need <= 0:
            raise ValueError("max_sources_per_need must be positive")
        self.max_sources_per_need = max_sources_per_need
        self.latency_weight = max(0.0, latency_weight)
        self.cost_weight = max(0.0, cost_weight)

    def _score(self, source: ObservationSource) -> float:
        penalty = (
            1.0
            + self.cost_weight * source.estimated_cost
            + self.latency_weight * source.latency_seconds
        )
        return source.reliability / penalty

    def plan(
        self,
        needs: Iterable[InformationNeed],
        sources: Iterable[ObservationSource],
    ) -> tuple[AcquisitionTask, ...]:
        source_list = tuple(sources)
        tasks = []
        for need in sorted(
            needs,
            key=lambda item: (
                -item.priority,
                item.asset_id,
                item.observation_type,
                item.need_id,
            ),
        ):
            candidates = [
                source for source in source_list if source.supports(need)
            ]
            candidates.sort(
                key=lambda source: (
                    -self._score(source),
                    source.source_id,
                )
            )
            used_groups = set()
            selected = 0
            for source in candidates:
                group = source.independence_group or f"source:{source.source_id}"
                if group in used_groups:
                    continue
                tasks.append(
                    AcquisitionTask(
                        need.need_id,
                        need.asset_id,
                        need.observation_type,
                        source.source_id,
                        self._score(source),
                    )
                )
                used_groups.add(group)
                selected += 1
                if selected >= self.max_sources_per_need:
                    break
        return tuple(tasks)


class AcquisitionExecutor:
    def execute(
        self,
        tasks: Iterable[AcquisitionTask],
        sources: Iterable[ObservationSource],
    ) -> tuple[AcquisitionResult, ...]:
        source_map = {source.source_id: source for source in sources}
        results = []
        cache: dict[str, tuple[PhysicalObservation, ...]] = {}
        errors: dict[str, str] = {}
        for task in tasks:
            source = source_map.get(task.source_id)
            if source is None:
                results.append(
                    AcquisitionResult(task, (), "failed", "source unavailable")
                )
                continue
            if source.source_id not in cache and source.source_id not in errors:
                try:
                    fetched = tuple(source.adapter.fetch())
                    if not all(
                        isinstance(item, PhysicalObservation)
                        for item in fetched
                    ):
                        raise TypeError(
                            "observation adapter must return PhysicalObservation objects"
                        )
                    cache[source.source_id] = fetched
                except Exception as exc:
                    errors[source.source_id] = str(exc)
            if source.source_id in errors:
                results.append(
                    AcquisitionResult(
                        task,
                        (),
                        "failed",
                        errors[source.source_id],
                    )
                )
                continue
            matched = tuple(
                item
                for item in cache[source.source_id]
                if item.asset_id == task.asset_id
                and item.observation_type == task.observation_type
            )
            results.append(
                AcquisitionResult(
                    task,
                    matched,
                    "ok" if matched else "no_matching_observation",
                    None,
                )
            )
        return tuple(results)
