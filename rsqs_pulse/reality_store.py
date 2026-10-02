from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import asdict
from typing import Any

from .evidence_fusion import FusedObservation
from .reality_observation import PhysicalObservation, RealityVariance


class RealityStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS physical_observations(
          observation_id TEXT PRIMARY KEY,
          observation_type TEXT NOT NULL,
          asset_id TEXT NOT NULL,
          timestamp TEXT NOT NULL,
          value_json TEXT NOT NULL,
          unit TEXT NOT NULL,
          confidence REAL NOT NULL,
          source TEXT NOT NULL,
          provenance_json TEXT NOT NULL,
          ingested_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_physical_observations_asset
          ON physical_observations(asset_id,observation_type,timestamp);

        CREATE TABLE IF NOT EXISTS fused_observations(
          fused_id TEXT PRIMARY KEY,
          observation_type TEXT NOT NULL,
          asset_id TEXT NOT NULL,
          timestamp TEXT NOT NULL,
          value_json TEXT NOT NULL,
          unit TEXT NOT NULL,
          confidence REAL NOT NULL,
          contributors_json TEXT NOT NULL,
          contributor_count INTEGER NOT NULL,
          independent_source_count INTEGER NOT NULL,
          disagreement REAL NOT NULL,
          contradictory INTEGER NOT NULL,
          provenance_json TEXT NOT NULL,
          created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_fused_observations_asset
          ON fused_observations(asset_id,observation_type,timestamp);

        CREATE TABLE IF NOT EXISTS reality_variances(
          variance_id TEXT PRIMARY KEY,
          asset_id TEXT NOT NULL,
          expected_json TEXT,
          observed_json TEXT NOT NULL,
          variance REAL NOT NULL,
          confidence REAL NOT NULL,
          explanation TEXT NOT NULL,
          created_at INTEGER NOT NULL
        );
        """)
        self.conn.commit()

    def record_observation(
        self,
        observation: PhysicalObservation,
        *,
        observation_id: str | None = None,
    ) -> str:
        observation_id = observation_id or str(uuid.uuid4())
        self.conn.execute(
            """INSERT OR IGNORE INTO physical_observations(
               observation_id,observation_type,asset_id,timestamp,value_json,
               unit,confidence,source,provenance_json,ingested_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                observation_id,
                observation.observation_type,
                observation.asset_id,
                observation.timestamp,
                json.dumps(observation.value, sort_keys=True),
                observation.unit,
                observation.confidence,
                observation.source,
                json.dumps(observation.provenance, sort_keys=True),
                int(time.time()),
            ),
        )
        self.conn.commit()
        return observation_id

    def record_fused(
        self,
        fused: FusedObservation,
        *,
        fused_id: str | None = None,
    ) -> str:
        fused_id = fused_id or str(uuid.uuid4())
        self.conn.execute(
            """INSERT OR REPLACE INTO fused_observations(
               fused_id,observation_type,asset_id,timestamp,value_json,unit,
               confidence,contributors_json,contributor_count,
               independent_source_count,disagreement,contradictory,
               provenance_json,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                fused_id,
                fused.observation_type,
                fused.asset_id,
                fused.timestamp,
                json.dumps(fused.value, sort_keys=True),
                fused.unit,
                fused.confidence,
                json.dumps(fused.contributors),
                fused.contributor_count,
                fused.independent_source_count,
                fused.disagreement,
                int(fused.contradictory),
                json.dumps(fused.provenance, sort_keys=True),
                int(time.time()),
            ),
        )
        self.conn.commit()
        return fused_id

    def record_variance(
        self,
        variance: RealityVariance,
        *,
        variance_id: str | None = None,
    ) -> str:
        variance_id = variance_id or str(uuid.uuid4())
        self.conn.execute(
            """INSERT OR REPLACE INTO reality_variances(
               variance_id,asset_id,expected_json,observed_json,variance,
               confidence,explanation,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                variance_id,
                variance.asset_id,
                json.dumps(variance.expected, sort_keys=True),
                json.dumps(variance.observed, sort_keys=True),
                variance.variance,
                variance.confidence,
                variance.explanation,
                int(time.time()),
            ),
        )
        self.conn.commit()
        return variance_id

    def observations(
        self,
        asset_id: str,
        observation_type: str | None = None,
    ) -> tuple[PhysicalObservation, ...]:
        sql = """SELECT observation_type,asset_id,timestamp,value_json,unit,
                        confidence,source,provenance_json
                 FROM physical_observations WHERE asset_id=?"""
        params: list[Any] = [asset_id]
        if observation_type is not None:
            sql += " AND observation_type=?"
            params.append(observation_type)
        sql += " ORDER BY timestamp,rowid"
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        return tuple(
            PhysicalObservation(
                observation_type=row[0],
                asset_id=row[1],
                timestamp=row[2],
                value=json.loads(row[3]),
                unit=row[4],
                confidence=float(row[5]),
                source=row[6],
                provenance=json.loads(row[7]),
            )
            for row in rows
        )

    def latest_fused(
        self,
        asset_id: str,
        observation_type: str,
    ) -> FusedObservation | None:
        row = self.conn.execute(
            """SELECT observation_type,asset_id,timestamp,value_json,unit,
                      confidence,contributors_json,contributor_count,
                      independent_source_count,disagreement,contradictory,
                      provenance_json
               FROM fused_observations
               WHERE asset_id=? AND observation_type=?
               ORDER BY timestamp DESC,rowid DESC LIMIT 1""",
            (asset_id, observation_type),
        ).fetchone()
        if row is None:
            return None
        return FusedObservation(
            observation_type=row[0],
            asset_id=row[1],
            timestamp=row[2],
            value=json.loads(row[3]),
            unit=row[4],
            confidence=float(row[5]),
            contributors=tuple(json.loads(row[6])),
            contributor_count=int(row[7]),
            independent_source_count=int(row[8]),
            disagreement=float(row[9]),
            contradictory=bool(row[10]),
            provenance=tuple(json.loads(row[11])),
        )

    def counts(self) -> dict[str, int]:
        return {
            "raw_observations": int(self.conn.execute(
                "SELECT COUNT(*) FROM physical_observations"
            ).fetchone()[0]),
            "fused_observations": int(self.conn.execute(
                "SELECT COUNT(*) FROM fused_observations"
            ).fetchone()[0]),
            "variances": int(self.conn.execute(
                "SELECT COUNT(*) FROM reality_variances"
            ).fetchone()[0]),
        }
