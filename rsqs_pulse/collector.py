from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class CollectorSource:
    source_id: str
    adapter: Any
    interval_seconds: int
    max_backoff_seconds: int = 3600

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if self.max_backoff_seconds < self.interval_seconds:
            raise ValueError(
                "max_backoff_seconds must be >= interval_seconds"
            )


@dataclass(frozen=True)
class CollectorBatch:
    source_id: str
    observations: tuple[Any, ...]
    status: str
    error: str | None
    next_due: int
    failures: int


class ObservationCollector:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS collector_state(
          source_id TEXT PRIMARY KEY,
          last_attempt INTEGER,
          last_success INTEGER,
          failures INTEGER NOT NULL DEFAULT 0,
          next_due INTEGER NOT NULL DEFAULT 0,
          last_error TEXT
        )
        """)
        self.conn.commit()

    def _state(self, source_id: str) -> tuple[int | None, int | None, int, int, str | None]:
        row = self.conn.execute(
            """SELECT last_attempt,last_success,failures,next_due,last_error
               FROM collector_state WHERE source_id=?""",
            (source_id,),
        ).fetchone()
        if row is None:
            return None, None, 0, 0, None
        return (
            None if row[0] is None else int(row[0]),
            None if row[1] is None else int(row[1]),
            int(row[2]),
            int(row[3]),
            row[4],
        )

    def due(
        self,
        sources: Iterable[CollectorSource],
        *,
        now: int,
    ) -> tuple[CollectorSource, ...]:
        return tuple(
            source
            for source in sorted(sources, key=lambda item: item.source_id)
            if self._state(source.source_id)[3] <= now
        )

    def run_due(
        self,
        sources: Iterable[CollectorSource],
        *,
        now: int,
    ) -> tuple[CollectorBatch, ...]:
        batches = []
        for source in self.due(sources, now=now):
            _, last_success, failures, _, _ = self._state(source.source_id)
            try:
                observations = tuple(source.adapter.fetch())
                failures = 0
                next_due = now + source.interval_seconds
                self.conn.execute(
                    """INSERT INTO collector_state(
                       source_id,last_attempt,last_success,failures,next_due,last_error)
                       VALUES(?,?,?,?,?,NULL)
                       ON CONFLICT(source_id) DO UPDATE SET
                         last_attempt=excluded.last_attempt,
                         last_success=excluded.last_success,
                         failures=0,
                         next_due=excluded.next_due,
                         last_error=NULL""",
                    (
                        source.source_id,
                        now,
                        now,
                        0,
                        next_due,
                    ),
                )
                batches.append(
                    CollectorBatch(
                        source.source_id,
                        observations,
                        "ok",
                        None,
                        next_due,
                        0,
                    )
                )
            except Exception as exc:
                failures += 1
                backoff = min(
                    source.max_backoff_seconds,
                    source.interval_seconds * (2 ** min(failures - 1, 20)),
                )
                next_due = now + backoff
                self.conn.execute(
                    """INSERT INTO collector_state(
                       source_id,last_attempt,last_success,failures,next_due,last_error)
                       VALUES(?,?,?,?,?,?)
                       ON CONFLICT(source_id) DO UPDATE SET
                         last_attempt=excluded.last_attempt,
                         failures=excluded.failures,
                         next_due=excluded.next_due,
                         last_error=excluded.last_error""",
                    (
                        source.source_id,
                        now,
                        last_success,
                        failures,
                        next_due,
                        str(exc),
                    ),
                )
                batches.append(
                    CollectorBatch(
                        source.source_id,
                        (),
                        "failed",
                        str(exc),
                        next_due,
                        failures,
                    )
                )
            self.conn.commit()
        return tuple(batches)

    def status(self) -> tuple[dict[str, Any], ...]:
        rows = self.conn.execute(
            """SELECT source_id,last_attempt,last_success,failures,next_due,last_error
               FROM collector_state ORDER BY source_id"""
        ).fetchall()
        return tuple(
            {
                "source_id": row[0],
                "last_attempt": row[1],
                "last_success": row[2],
                "failures": int(row[3]),
                "next_due": int(row[4]),
                "last_error": row[5],
            }
            for row in rows
        )
