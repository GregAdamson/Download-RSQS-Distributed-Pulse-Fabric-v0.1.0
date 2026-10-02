from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from .evidence_fusion import FusedObservation


@dataclass(frozen=True)
class TwinAsset:
    asset_id: str
    asset_type: str
    name: str
    parent_id: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class TwinRelation:
    source_asset: str
    relation: str
    target_asset: str


@dataclass(frozen=True)
class TwinState:
    asset_id: str
    key: str
    value: Any
    unit: str
    confidence: float
    observed_at: str
    source_ref: str


class DigitalTwinStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS twin_assets(
          asset_id TEXT PRIMARY KEY,
          asset_type TEXT NOT NULL,
          name TEXT NOT NULL,
          parent_id TEXT,
          metadata_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS twin_relations(
          source_asset TEXT NOT NULL,
          relation TEXT NOT NULL,
          target_asset TEXT NOT NULL,
          PRIMARY KEY(source_asset,relation,target_asset)
        );
        CREATE TABLE IF NOT EXISTS twin_state(
          seq INTEGER PRIMARY KEY AUTOINCREMENT,
          asset_id TEXT NOT NULL,
          key TEXT NOT NULL,
          value_json TEXT NOT NULL,
          unit TEXT NOT NULL,
          confidence REAL NOT NULL,
          observed_at TEXT NOT NULL,
          source_ref TEXT NOT NULL,
          recorded_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_twin_state_latest
          ON twin_state(asset_id,key,seq);
        """)
        self.conn.commit()

    def upsert_asset(self, asset: TwinAsset) -> None:
        if asset.parent_id == asset.asset_id:
            raise ValueError("asset cannot be its own parent")
        self.conn.execute("SAVEPOINT twin_asset_update")
        try:
            self.conn.execute(
                """INSERT INTO twin_assets(asset_id,asset_type,name,parent_id,metadata_json)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(asset_id) DO UPDATE SET
                     asset_type=excluded.asset_type,
                     name=excluded.name,
                     parent_id=excluded.parent_id,
                     metadata_json=excluded.metadata_json""",
                (
                    asset.asset_id,
                    asset.asset_type,
                    asset.name,
                    asset.parent_id,
                    json.dumps(asset.metadata, sort_keys=True),
                ),
            )
            self._assert_no_parent_cycle(asset.asset_id)
            self.conn.execute("RELEASE SAVEPOINT twin_asset_update")
            self.conn.commit()
        except Exception:
            self.conn.execute("ROLLBACK TO SAVEPOINT twin_asset_update")
            self.conn.execute("RELEASE SAVEPOINT twin_asset_update")
            self.conn.rollback()
            raise

    def _assert_no_parent_cycle(self, asset_id: str) -> None:
        seen = set()
        current = asset_id
        while current is not None:
            if current in seen:
                raise ValueError("asset parent hierarchy contains a cycle")
            seen.add(current)
            row = self.conn.execute(
                "SELECT parent_id FROM twin_assets WHERE asset_id=?",
                (current,),
            ).fetchone()
            current = None if row is None else row[0]

    def add_relation(self, relation: TwinRelation) -> None:
        if relation.source_asset == relation.target_asset:
            raise ValueError("self relations are not permitted")
        self.conn.execute(
            """INSERT OR IGNORE INTO twin_relations(
               source_asset,relation,target_asset) VALUES(?,?,?)""",
            (
                relation.source_asset,
                relation.relation,
                relation.target_asset,
            ),
        )
        self.conn.commit()

    def apply_fused(
        self,
        fused: FusedObservation,
        *,
        source_ref: str,
    ) -> TwinState:
        if self.asset(fused.asset_id) is None:
            self.upsert_asset(
                TwinAsset(
                    fused.asset_id,
                    "unknown",
                    fused.asset_id,
                    None,
                    {},
                )
            )
        self.conn.execute(
            """INSERT INTO twin_state(
               asset_id,key,value_json,unit,confidence,observed_at,source_ref,recorded_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                fused.asset_id,
                fused.observation_type,
                json.dumps(fused.value, sort_keys=True),
                fused.unit,
                fused.confidence,
                fused.timestamp,
                source_ref,
                int(time.time()),
            ),
        )
        self.conn.commit()
        return TwinState(
            fused.asset_id,
            fused.observation_type,
            fused.value,
            fused.unit,
            fused.confidence,
            fused.timestamp,
            source_ref,
        )

    def asset(self, asset_id: str) -> TwinAsset | None:
        row = self.conn.execute(
            """SELECT asset_id,asset_type,name,parent_id,metadata_json
               FROM twin_assets WHERE asset_id=?""",
            (asset_id,),
        ).fetchone()
        if row is None:
            return None
        return TwinAsset(
            row[0], row[1], row[2], row[3], json.loads(row[4])
        )

    def children(self, asset_id: str) -> tuple[TwinAsset, ...]:
        rows = self.conn.execute(
            """SELECT asset_id,asset_type,name,parent_id,metadata_json
               FROM twin_assets WHERE parent_id=? ORDER BY asset_id""",
            (asset_id,),
        ).fetchall()
        return tuple(
            TwinAsset(row[0], row[1], row[2], row[3], json.loads(row[4]))
            for row in rows
        )

    def latest_state(self, asset_id: str) -> dict[str, TwinState]:
        rows = self.conn.execute(
            """SELECT s.asset_id,s.key,s.value_json,s.unit,s.confidence,
                      s.observed_at,s.source_ref
               FROM twin_state s
               JOIN (
                 SELECT key,MAX(seq) AS seq
                 FROM twin_state WHERE asset_id=? GROUP BY key
               ) latest ON latest.seq=s.seq
               WHERE s.asset_id=?
               ORDER BY s.key""",
            (asset_id, asset_id),
        ).fetchall()
        return {
            row[1]: TwinState(
                row[0], row[1], json.loads(row[2]), row[3],
                float(row[4]), row[5], row[6],
            )
            for row in rows
        }

    def history(
        self,
        asset_id: str,
        key: str,
    ) -> tuple[TwinState, ...]:
        rows = self.conn.execute(
            """SELECT asset_id,key,value_json,unit,confidence,observed_at,source_ref
               FROM twin_state WHERE asset_id=? AND key=? ORDER BY seq""",
            (asset_id, key),
        ).fetchall()
        return tuple(
            TwinState(
                row[0], row[1], json.loads(row[2]), row[3],
                float(row[4]), row[5], row[6],
            )
            for row in rows
        )

    def relations(self, asset_id: str) -> tuple[TwinRelation, ...]:
        rows = self.conn.execute(
            """SELECT source_asset,relation,target_asset
               FROM twin_relations
               WHERE source_asset=? OR target_asset=?
               ORDER BY source_asset,relation,target_asset""",
            (asset_id, asset_id),
        ).fetchall()
        return tuple(TwinRelation(*row) for row in rows)

    def snapshot(self, asset_id: str) -> dict[str, Any]:
        asset = self.asset(asset_id)
        if asset is None:
            raise KeyError(asset_id)
        return {
            "asset": {
                "asset_id": asset.asset_id,
                "asset_type": asset.asset_type,
                "name": asset.name,
                "parent_id": asset.parent_id,
                "metadata": asset.metadata,
            },
            "state": {
                key: {
                    "value": value.value,
                    "unit": value.unit,
                    "confidence": value.confidence,
                    "observed_at": value.observed_at,
                    "source_ref": value.source_ref,
                }
                for key, value in self.latest_state(asset_id).items()
            },
            "children": [child.asset_id for child in self.children(asset_id)],
            "relations": [
                {
                    "source_asset": relation.source_asset,
                    "relation": relation.relation,
                    "target_asset": relation.target_asset,
                }
                for relation in self.relations(asset_id)
            ],
        }
