from __future__ import annotations

import os
import ssl
from pathlib import Path
from typing import Any, Mapping

from .sensor_adapters import (
    CSVObservationAdapter,
    JSONFileObservationAdapter,
    JSONHTTPObservationAdapter,
    ObservationMapping,
    RecordObservationAdapter,
)


def _mapping(raw: Mapping[str, Any]) -> ObservationMapping:
    required = (
        "observation_type_field",
        "asset_id_field",
        "value_field",
        "unit_field",
    )
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(f"missing mapping fields: {missing}")
    return ObservationMapping(
        observation_type_field=str(raw["observation_type_field"]),
        asset_id_field=str(raw["asset_id_field"]),
        value_field=str(raw["value_field"]),
        unit_field=str(raw["unit_field"]),
        confidence_field=(
            None if raw.get("confidence_field") is None
            else str(raw["confidence_field"])
        ),
        timestamp_field=(
            None if raw.get("timestamp_field") is None
            else str(raw["timestamp_field"])
        ),
        source_field=(
            None if raw.get("source_field") is None
            else str(raw["source_field"])
        ),
        static_observation_type=(
            None if raw.get("static_observation_type") is None
            else str(raw["static_observation_type"])
        ),
        static_unit=(
            None if raw.get("static_unit") is None
            else str(raw["static_unit"])
        ),
        static_source=(
            None if raw.get("static_source") is None
            else str(raw["static_source"])
        ),
    )


def build_observation_adapter(config: Mapping[str, Any]):
    adapter_type = str(config["type"])
    source = str(config.get("source", adapter_type))
    mapping = _mapping(config["mapping"])
    provenance_static = dict(config.get("provenance", {}))

    record_adapter = RecordObservationAdapter(
        mapping,
        source=source,
        provenance_builder=lambda record: {
            **provenance_static,
            "adapter_type": adapter_type,
        },
    )
    records_path = tuple(str(item) for item in config.get("records_path", []))

    if adapter_type == "http_json":
        headers = dict(config.get("headers", {}))
        for header, env_name in dict(config.get("header_env", {})).items():
            value = os.environ.get(str(env_name))
            if value is None:
                raise RuntimeError(
                    f"missing environment variable for header {header}: {env_name}"
                )
            headers[str(header)] = value
        tls = None
        ca_file = config.get("ca_file")
        if ca_file is not None:
            tls = ssl.create_default_context(cafile=str(ca_file))
        return JSONHTTPObservationAdapter(
            str(config["url"]),
            record_adapter,
            timeout=float(config.get("timeout", 10.0)),
            ssl_context=tls,
            headers=headers,
            records_path=records_path,
        )
    if adapter_type == "json_file":
        return JSONFileObservationAdapter(
            str(Path(config["path"])),
            record_adapter,
            records_path=records_path,
        )
    if adapter_type == "csv_file":
        return CSVObservationAdapter(
            str(Path(config["path"])),
            record_adapter,
        )
    raise ValueError(f"unsupported observation adapter type: {adapter_type}")
