from __future__ import annotations

import csv
import io
import json
import ssl
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .reality_observation import PhysicalObservation


@dataclass(frozen=True)
class ObservationMapping:
    observation_type_field: str | None
    asset_id_field: str
    value_field: str
    unit_field: str | None
    confidence_field: str | None = None
    timestamp_field: str | None = None
    source_field: str | None = None
    static_observation_type: str | None = None
    static_unit: str | None = None
    static_source: str | None = None


class RecordObservationAdapter:
    def __init__(
        self,
        mapping: ObservationMapping,
        *,
        source: str,
        provenance_builder: Callable[[Mapping[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.mapping = mapping
        self.source = source
        self.provenance_builder = provenance_builder or (lambda record: {})

    def adapt(self, records: Iterable[Mapping[str, Any]]) -> tuple[PhysicalObservation, ...]:
        result = []
        for record in records:
            if self.mapping.static_observation_type is not None:
                observation_type = self.mapping.static_observation_type
            elif self.mapping.observation_type_field is not None:
                observation_type = str(record[self.mapping.observation_type_field])
            else:
                raise ValueError("observation type requires a field or static value")
            if self.mapping.static_unit is not None:
                unit = self.mapping.static_unit
            elif self.mapping.unit_field is not None:
                unit = str(record[self.mapping.unit_field])
            else:
                raise ValueError("unit requires a field or static value")
            source = (
                self.mapping.static_source
                or (
                    str(record[self.mapping.source_field])
                    if self.mapping.source_field is not None
                    else self.source
                )
            )
            confidence = (
                1.0
                if self.mapping.confidence_field is None
                else float(record[self.mapping.confidence_field])
            )
            if self.mapping.timestamp_field is None:
                timestamp = datetime.now(timezone.utc).isoformat()
            else:
                timestamp = str(record[self.mapping.timestamp_field])
            result.append(
                PhysicalObservation(
                    observation_type=observation_type,
                    asset_id=str(record[self.mapping.asset_id_field]),
                    timestamp=timestamp,
                    value=record[self.mapping.value_field],
                    unit=unit,
                    confidence=max(0.0, min(1.0, confidence)),
                    source=source,
                    provenance=self.provenance_builder(record),
                )
            )
        return tuple(result)


class JSONHTTPObservationAdapter:
    def __init__(
        self,
        url: str,
        record_adapter: RecordObservationAdapter,
        *,
        timeout: float = 10.0,
        ssl_context: ssl.SSLContext | None = None,
        headers: Mapping[str, str] | None = None,
        records_path: tuple[str, ...] = (),
    ) -> None:
        self.url = url
        self.record_adapter = record_adapter
        self.timeout = timeout
        self.ssl_context = ssl_context
        self.headers = dict(headers or {})
        self.records_path = tuple(records_path)

    def fetch(self) -> tuple[PhysicalObservation, ...]:
        request = urllib.request.Request(self.url, headers=self.headers, method="GET")
        kwargs = {"timeout": self.timeout}
        if self.ssl_context is not None:
            kwargs["context"] = self.ssl_context
        with urllib.request.urlopen(request, **kwargs) as response:
            payload = json.loads(response.read().decode("utf-8"))
        for key in self.records_path:
            payload = payload[key]
        if isinstance(payload, Mapping):
            payload = [payload]
        if not isinstance(payload, list):
            raise TypeError("JSON records payload must be an object or list")
        return self.record_adapter.adapt(payload)


class JSONFileObservationAdapter:
    def __init__(
        self,
        path: str,
        record_adapter: RecordObservationAdapter,
        *,
        records_path: tuple[str, ...] = (),
    ) -> None:
        self.path = Path(path)
        self.record_adapter = record_adapter
        self.records_path = tuple(records_path)

    def fetch(self) -> tuple[PhysicalObservation, ...]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        for key in self.records_path:
            payload = payload[key]
        if isinstance(payload, Mapping):
            payload = [payload]
        if not isinstance(payload, list):
            raise TypeError("JSON records payload must be an object or list")
        return self.record_adapter.adapt(payload)


class CSVObservationAdapter:
    def __init__(self, path: str, record_adapter: RecordObservationAdapter) -> None:
        self.path = Path(path)
        self.record_adapter = record_adapter

    def fetch(self) -> tuple[PhysicalObservation, ...]:
        with self.path.open("r", encoding="utf-8", newline="") as handle:
            return self.record_adapter.adapt(csv.DictReader(handle))


class TelemetryAdapter(RecordObservationAdapter):
    pass


class WeatherAdapter(RecordObservationAdapter):
    pass


class SatelliteAdapter(RecordObservationAdapter):
    pass


class LogisticsAdapter(RecordObservationAdapter):
    pass


class MarketObservationAdapter(RecordObservationAdapter):
    pass
