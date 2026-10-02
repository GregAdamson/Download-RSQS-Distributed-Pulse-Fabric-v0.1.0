from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .intelligence_export import (
    IntelligenceDirectory,
    IntelligenceEnvelope,
    IntelligenceExportPolicy,
    IntelligenceExporter,
    IntelligenceIdentity,
)


@dataclass(frozen=True)
class IntelligenceCallResult:
    identity_uri: str
    operation: str
    result: dict[str, Any]


class IntelligenceRouter:
    def __init__(self, runtime, *, reality_engine=None, federated_store=None) -> None:
        self.runtime = runtime
        self.reality_engine = reality_engine
        self.federated_store = federated_store
        self.directory = IntelligenceDirectory(runtime.state.conn)
        twin = None if reality_engine is None else reality_engine.twin
        self.exporter = (
            None
            if twin is None
            else IntelligenceExporter(runtime.identity, self.directory, twin)
        )
        self.node_identity = self.directory.register(
            kind="node",
            local_ref=runtime.node_id,
            display_name=runtime.node_id,
            owner_node=runtime.node_id,
            metadata={"node_id": runtime.node_id},
        )

    def register_identity(
        self,
        *,
        kind: str,
        local_ref: str,
        display_name: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> IntelligenceIdentity:
        return self.directory.register(
            kind=kind,
            local_ref=local_ref,
            display_name=display_name,
            owner_node=self.runtime.node_id,
            metadata=metadata,
        )

    def ensure_asset_identity(self, asset_id: str) -> IntelligenceIdentity:
        if self.exporter is None:
            raise RuntimeError("reality engine is required for asset identities")
        return self.exporter.ensure_asset_identity(asset_id)

    def identities(self) -> tuple[IntelligenceIdentity, ...]:
        if self.reality_engine is not None:
            rows = self.runtime.state.conn.execute(
                "SELECT asset_id FROM twin_assets ORDER BY asset_id"
            ).fetchall()
            for row in rows:
                self.ensure_asset_identity(row[0])
        return self.directory.all()

    def identity_uris(self) -> tuple[str, ...]:
        local = {item.uri for item in self.identities()}
        remote = (
            set()
            if self.federated_store is None
            else set(self.federated_store.identities())
        )
        return tuple(sorted(local | remote))

    def call(
        self,
        identity_uri: str,
        operation: str = "describe",
        args: Mapping[str, Any] | None = None,
    ) -> IntelligenceCallResult:
        args = dict(args or {})
        identity = self.directory.by_uri(identity_uri)
        if identity is None:
            if self.federated_store is not None:
                try:
                    return IntelligenceCallResult(
                        identity_uri,
                        operation,
                        self.federated_store.call(
                            identity_uri,
                            operation,
                        ),
                    )
                except KeyError:
                    pass
            raise KeyError(identity_uri)

        if identity.kind == "node":
            result = self._call_node(identity, operation, args)
        elif identity.kind == "asset":
            result = self._call_asset(identity, operation, args)
        else:
            result = self._call_generic(identity, operation, args)
        return IntelligenceCallResult(identity_uri, operation, result)

    def _call_node(
        self,
        identity: IntelligenceIdentity,
        operation: str,
        args: Mapping[str, Any],
    ) -> dict[str, Any]:
        if operation == "describe":
            return {
                "identity": asdict(identity),
                "uri": identity.uri,
                "operations": ["describe", "health", "state", "capabilities"],
            }
        if operation == "health":
            return dict(self.runtime.health())
        if operation == "state":
            return dict(self.runtime.current_state().values)
        if operation == "capabilities":
            return {"capabilities": sorted(self.runtime.handlers)}
        raise ValueError(f"unsupported node operation: {operation}")

    def _call_asset(
        self,
        identity: IntelligenceIdentity,
        operation: str,
        args: Mapping[str, Any],
    ) -> dict[str, Any]:
        if self.reality_engine is None or self.exporter is None:
            raise RuntimeError("reality engine is required for asset calls")
        twin = self.reality_engine.twin

        if operation == "describe":
            asset = twin.asset(identity.local_ref)
            if asset is None:
                raise KeyError(identity.local_ref)
            return {
                "identity": asdict(identity),
                "uri": identity.uri,
                "asset": asdict(asset),
                "operations": [
                    "describe",
                    "snapshot",
                    "state",
                    "relations",
                    "history",
                    "export",
                ],
            }
        if operation == "snapshot":
            return twin.snapshot(identity.local_ref)
        if operation == "state":
            return {
                key: asdict(value)
                for key, value in twin.latest_state(identity.local_ref).items()
            }
        if operation == "relations":
            return {
                "relations": [
                    asdict(item)
                    for item in twin.relations(identity.local_ref)
                ]
            }
        if operation == "history":
            key = args.get("key")
            if not key:
                raise ValueError("history operation requires args['key']")
            return {
                "history": [
                    asdict(item)
                    for item in twin.history(identity.local_ref, str(key))
                ]
            }
        if operation == "export":
            include_keys = tuple(
                str(item) for item in args.get("include_keys", ())
            )
            exclude_keys = tuple(
                str(item) for item in args.get("exclude_keys", ())
            )
            policy = IntelligenceExportPolicy(
                minimum_confidence=float(args.get("minimum_confidence", 0.0)),
                include_keys=include_keys,
                exclude_keys=exclude_keys,
                include_provenance_refs=bool(
                    args.get("include_provenance_refs", True)
                ),
                include_relations=bool(args.get("include_relations", True)),
            )
            envelope = self.exporter.export(
                identity.identity_id,
                policy=policy,
                ttl_seconds=(
                    None
                    if args.get("ttl_seconds") is None
                    else int(args["ttl_seconds"])
                ),
            )
            return {"envelope": asdict(envelope)}
        raise ValueError(f"unsupported asset operation: {operation}")

    def _call_generic(
        self,
        identity: IntelligenceIdentity,
        operation: str,
        args: Mapping[str, Any],
    ) -> dict[str, Any]:
        if operation == "describe":
            return {
                "identity": asdict(identity),
                "uri": identity.uri,
                "operations": ["describe", "metadata"],
            }
        if operation == "metadata":
            return dict(identity.metadata)
        raise ValueError(
            f"unsupported {identity.kind} operation: {operation}"
        )
