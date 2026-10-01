from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping


@dataclass(frozen=True)
class CanonicalObservation:
    key: str
    value: Any
    source: str
    observed_at: int | None = None
    unit: str | None = None
    confidence: float = 1.0


@dataclass(frozen=True)
class CanonicalResource:
    resource: str
    quantity: float
    unit: str
    location: str
    source: str
    quality: float = 1.0
    owner: str | None = None


@dataclass(frozen=True)
class CanonicalDependency:
    capability: str
    resource: str | None = None
    quantity: float | None = None
    unit: str | None = None
    dependency_capability: str | None = None
    critical: bool = True


@dataclass(frozen=True)
class CanonicalRule:
    rule_id: str
    scope: str
    effect: str
    subject: str
    source: str

    def __post_init__(self) -> None:
        if self.effect not in {"allow", "deny", "require"}:
            raise ValueError("effect must be allow, deny or require")


@dataclass(frozen=True)
class AdapterBatch:
    observations: tuple[CanonicalObservation, ...] = ()
    resources: tuple[CanonicalResource, ...] = ()
    dependencies: tuple[CanonicalDependency, ...] = ()
    rules: tuple[CanonicalRule, ...] = ()
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True)
class MappingSpec:
    source: str
    observation_fields: Mapping[str, str] = field(default_factory=dict)
    resource_name_field: str | None = None
    quantity_field: str | None = None
    unit_field: str | None = None
    location_field: str | None = None
    quality_field: str | None = None
    owner_field: str | None = None


class MappingDomainAdapter:
    """
    Target-agnostic record adapter.

    It maps caller-supplied record fields into canonical observations/resources.
    Domain meaning stays in the MappingSpec rather than being hard-coded here.
    """

    def __init__(
        self,
        spec: MappingSpec,
        *,
        transform: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        self.spec = spec
        self.transform = transform or (lambda record: record)

    def ingest(
        self,
        records: Iterable[Mapping[str, Any]],
    ) -> AdapterBatch:
        observations = []
        resources = []
        provenance = []
        for index, original in enumerate(records):
            record = dict(self.transform(original))
            provenance.append(f"{self.spec.source}:record:{index}")
            for canonical_key, field_name in sorted(self.spec.observation_fields.items()):
                if field_name in record:
                    observations.append(
                        CanonicalObservation(
                            key=canonical_key,
                            value=record[field_name],
                            source=self.spec.source,
                        )
                    )
            if self.spec.resource_name_field is not None:
                required = (
                    self.spec.resource_name_field,
                    self.spec.quantity_field,
                    self.spec.unit_field,
                    self.spec.location_field,
                )
                if any(field is None for field in required):
                    raise ValueError("resource mapping requires name, quantity, unit and location fields")
                missing = [field for field in required if field not in record]
                if missing:
                    raise KeyError(f"missing mapped resource fields: {missing}")
                quantity = float(record[self.spec.quantity_field])
                quality = (
                    1.0 if self.spec.quality_field is None
                    else float(record[self.spec.quality_field])
                )
                if quantity < 0:
                    raise ValueError("resource quantity must be non-negative")
                if not 0.0 <= quality <= 1.0:
                    raise ValueError("resource quality must be in [0,1]")
                resources.append(
                    CanonicalResource(
                        resource=str(record[self.spec.resource_name_field]),
                        quantity=quantity,
                        unit=str(record[self.spec.unit_field]),
                        location=str(record[self.spec.location_field]),
                        source=self.spec.source,
                        quality=quality,
                        owner=(
                            None if self.spec.owner_field is None
                            else str(record[self.spec.owner_field])
                        ),
                    )
                )
        return AdapterBatch(
            observations=tuple(observations),
            resources=tuple(resources),
            provenance=tuple(provenance),
        )


class CompositeDomainAdapter:
    def __init__(self, adapters: Iterable[MappingDomainAdapter]) -> None:
        self.adapters = tuple(adapters)

    def ingest(
        self,
        record_sets: Iterable[Iterable[Mapping[str, Any]]],
    ) -> AdapterBatch:
        sets = tuple(record_sets)
        if len(sets) != len(self.adapters):
            raise ValueError("one record set is required per adapter")
        observations = []
        resources = []
        dependencies = []
        rules = []
        provenance = []
        for adapter, records in zip(self.adapters, sets):
            batch = adapter.ingest(records)
            observations.extend(batch.observations)
            resources.extend(batch.resources)
            dependencies.extend(batch.dependencies)
            rules.extend(batch.rules)
            provenance.extend(batch.provenance)
        return AdapterBatch(
            tuple(observations),
            tuple(resources),
            tuple(dependencies),
            tuple(rules),
            tuple(provenance),
        )


def apply_adapter_batch(
    batch: AdapterBatch,
    *,
    runtime=None,
    inventory=None,
    graph=None,
    rule_sink: Callable[[CanonicalRule], None] | None = None,
) -> dict[str, int]:
    if runtime is not None and batch.observations:
        from .cognitive_loop import Observation
        for item in batch.observations:
            runtime.observe([Observation(item.source, {item.key: item.value})])

    if inventory is not None:
        for item in batch.resources:
            inventory.observe(
                item.resource,
                item.quantity,
                item.unit,
                item.location,
                item.source,
                quality=item.quality,
                owner=item.owner,
            )

    if graph is not None:
        from .dependency_graph import CapabilityRequirement, ResourceRequirement
        for item in batch.dependencies:
            if item.resource is not None:
                if item.quantity is None or item.unit is None:
                    raise ValueError(
                        "resource dependency requires quantity and unit"
                    )
                graph.require_resource(
                    item.capability,
                    ResourceRequirement(
                        item.resource,
                        float(item.quantity),
                        item.unit,
                        critical=item.critical,
                    ),
                )
            elif item.dependency_capability is not None:
                graph.require_capability(
                    item.capability,
                    CapabilityRequirement(
                        item.dependency_capability,
                        critical=item.critical,
                    ),
                )
            else:
                raise ValueError(
                    "dependency requires resource or dependency_capability"
                )

    if rule_sink is not None:
        for item in batch.rules:
            rule_sink(item)

    return {
        "observations": len(batch.observations),
        "resources": len(batch.resources),
        "dependencies": len(batch.dependencies),
        "rules": len(batch.rules),
        "provenance": len(batch.provenance),
    }
