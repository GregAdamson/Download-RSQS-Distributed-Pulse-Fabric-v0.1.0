from __future__ import annotations
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Dict, Iterable

@dataclass(frozen=True)
class ResourceLot:
    lot_id: str
    resource: str
    quantity: float
    unit: str
    location: str
    quality: float
    owner: str | None
    replenishment_per_day: float
    lead_time_days: float
    observed_at: int
    source: str

class ResourceInventory:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS resource_lots(
          lot_id TEXT PRIMARY KEY,
          resource TEXT NOT NULL,
          quantity REAL NOT NULL,
          unit TEXT NOT NULL,
          location TEXT NOT NULL,
          quality REAL NOT NULL,
          owner TEXT,
          replenishment_per_day REAL NOT NULL,
          lead_time_days REAL NOT NULL,
          observed_at INTEGER NOT NULL,
          source TEXT NOT NULL
        )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_resource_lots_resource ON resource_lots(resource,unit,location)")
        self.conn.commit()

    def observe(
        self,
        resource: str,
        quantity: float,
        unit: str,
        location: str,
        source: str,
        *,
        quality: float = 1.0,
        owner: str | None = None,
        replenishment_per_day: float = 0.0,
        lead_time_days: float = 0.0,
        observed_at: int | None = None,
        lot_id: str | None = None,
    ) -> ResourceLot:
        if quantity < 0:
            raise ValueError("quantity must be non-negative")
        if not 0.0 <= quality <= 1.0:
            raise ValueError("quality must be in [0,1]")
        if replenishment_per_day < 0 or lead_time_days < 0:
            raise ValueError("replenishment and lead time must be non-negative")
        lot = ResourceLot(
            lot_id or str(uuid.uuid4()), resource, float(quantity), unit, location,
            float(quality), owner, float(replenishment_per_day), float(lead_time_days),
            int(time.time()) if observed_at is None else int(observed_at), source,
        )
        self.conn.execute(
            """INSERT OR REPLACE INTO resource_lots(
               lot_id,resource,quantity,unit,location,quality,owner,replenishment_per_day,
               lead_time_days,observed_at,source) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                lot.lot_id, lot.resource, lot.quantity, lot.unit, lot.location, lot.quality,
                lot.owner, lot.replenishment_per_day, lot.lead_time_days, lot.observed_at, lot.source,
            ),
        )
        self.conn.commit()
        return lot

    def lots(self, resource: str, unit: str | None = None, location: str | None = None, minimum_quality: float = 0.0) -> list[ResourceLot]:
        query = """SELECT lot_id,resource,quantity,unit,location,quality,owner,replenishment_per_day,
                          lead_time_days,observed_at,source
                   FROM resource_lots WHERE resource=? AND quality>=?"""
        args: list[object] = [resource, float(minimum_quality)]
        if unit is not None:
            query += " AND unit=?"
            args.append(unit)
        if location is not None:
            query += " AND location=?"
            args.append(location)
        query += " ORDER BY quality DESC, lead_time_days, lot_id"
        rows = self.conn.execute(query, tuple(args)).fetchall()
        return [ResourceLot(*row) for row in rows]

    def available(self, resource: str, unit: str, *, location: str | None = None, minimum_quality: float = 0.0) -> float:
        return sum(lot.quantity for lot in self.lots(resource, unit, location, minimum_quality))

    def snapshot(self) -> Dict[str, float]:
        rows = self.conn.execute(
            "SELECT resource,unit,SUM(quantity) FROM resource_lots GROUP BY resource,unit ORDER BY resource,unit"
        ).fetchall()
        return {f"{resource}:{unit}": float(quantity) for resource, unit, quantity in rows}
