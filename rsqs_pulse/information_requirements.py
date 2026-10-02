from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from .digital_twin import DigitalTwinStore
from .reality_store import RealityStore


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class InformationNeed:
    need_id: str
    asset_id: str
    observation_type: str
    reason: str
    priority: int
    minimum_confidence: float
    max_age_seconds: float | None
    created_at: int


@dataclass(frozen=True)
class InformationRequirementSpec:
    observation_type: str
    minimum_confidence: float = 0.5
    max_age_seconds: float | None = None
    priority: int = 0
    block_on_contradiction: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be in [0,1]")
        if self.max_age_seconds is not None and self.max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be positive")


class InformationRequirementEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS information_needs(
          need_id TEXT PRIMARY KEY,
          asset_id TEXT NOT NULL,
          observation_type TEXT NOT NULL,
          reason TEXT NOT NULL,
          priority INTEGER NOT NULL,
          minimum_confidence REAL NOT NULL,
          max_age_seconds REAL,
          created_at INTEGER NOT NULL,
          resolved_at INTEGER
        )
        """)
        self.conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_information_needs_open
          ON information_needs(asset_id,observation_type,resolved_at);
        """)
        self.conn.commit()

    def evaluate(
        self,
        asset_id: str,
        specs: Iterable[InformationRequirementSpec],
        twin: DigitalTwinStore,
        reality: RealityStore,
        *,
        now: datetime | None = None,
    ) -> tuple[InformationNeed, ...]:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        state = twin.latest_state(asset_id)
        needs = []
        for spec in specs:
            current = state.get(spec.observation_type)
            fused = reality.latest_fused(asset_id, spec.observation_type)
            reason = None
            if current is None:
                reason = "missing"
            elif current.confidence < spec.minimum_confidence:
                reason = "low_confidence"
            elif (
                spec.max_age_seconds is not None
                and (now - _parse_time(current.observed_at)).total_seconds()
                > spec.max_age_seconds
            ):
                reason = "stale"
            elif (
                spec.block_on_contradiction
                and fused is not None
                and fused.contradictory
            ):
                reason = "contradictory_evidence"

            if reason is None:
                self.resolve(asset_id, spec.observation_type, now=int(now.timestamp()))
                continue

            existing = self._open_need(asset_id, spec.observation_type)
            if existing is not None and existing.reason == reason:
                needs.append(existing)
                continue
            if existing is not None:
                self.resolve(asset_id, spec.observation_type, now=int(now.timestamp()))

            need = InformationNeed(
                need_id=str(uuid.uuid4()),
                asset_id=asset_id,
                observation_type=spec.observation_type,
                reason=reason,
                priority=spec.priority,
                minimum_confidence=spec.minimum_confidence,
                max_age_seconds=spec.max_age_seconds,
                created_at=int(now.timestamp()),
            )
            self.conn.execute(
                """INSERT INTO information_needs(
                   need_id,asset_id,observation_type,reason,priority,
                   minimum_confidence,max_age_seconds,created_at,resolved_at)
                   VALUES(?,?,?,?,?,?,?,?,NULL)""",
                (
                    need.need_id,
                    need.asset_id,
                    need.observation_type,
                    need.reason,
                    need.priority,
                    need.minimum_confidence,
                    need.max_age_seconds,
                    need.created_at,
                ),
            )
            self.conn.commit()
            needs.append(need)

        return tuple(
            sorted(
                needs,
                key=lambda item: (
                    -item.priority,
                    item.asset_id,
                    item.observation_type,
                ),
            )
        )

    def _open_need(
        self,
        asset_id: str,
        observation_type: str,
    ) -> InformationNeed | None:
        row = self.conn.execute(
            """SELECT need_id,asset_id,observation_type,reason,priority,
                      minimum_confidence,max_age_seconds,created_at
               FROM information_needs
               WHERE asset_id=? AND observation_type=? AND resolved_at IS NULL
               ORDER BY created_at DESC,rowid DESC LIMIT 1""",
            (asset_id, observation_type),
        ).fetchone()
        if row is None:
            return None
        return InformationNeed(
            row[0], row[1], row[2], row[3], int(row[4]),
            float(row[5]), None if row[6] is None else float(row[6]),
            int(row[7]),
        )

    def resolve(
        self,
        asset_id: str,
        observation_type: str,
        *,
        now: int | None = None,
    ) -> None:
        now = int(time.time()) if now is None else int(now)
        self.conn.execute(
            """UPDATE information_needs SET resolved_at=?
               WHERE asset_id=? AND observation_type=? AND resolved_at IS NULL""",
            (now, asset_id, observation_type),
        )
        self.conn.commit()

    def open_needs(self) -> tuple[InformationNeed, ...]:
        rows = self.conn.execute(
            """SELECT need_id,asset_id,observation_type,reason,priority,
                      minimum_confidence,max_age_seconds,created_at
               FROM information_needs WHERE resolved_at IS NULL
               ORDER BY priority DESC,created_at,need_id"""
        ).fetchall()
        return tuple(
            InformationNeed(
                row[0], row[1], row[2], row[3], int(row[4]),
                float(row[5]), None if row[6] is None else float(row[6]),
                int(row[7]),
            )
            for row in rows
        )
