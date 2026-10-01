from __future__ import annotations
import sqlite3
from typing import Iterable

from .world_models import WorldModel


class WorldModelStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS world_model_evidence(
          model_id TEXT PRIMARY KEY,
          evidence REAL NOT NULL,
          error_total REAL NOT NULL,
          observations INTEGER NOT NULL
        )
        """)
        self.conn.commit()

    def restore(self, model: WorldModel) -> WorldModel:
        row = self.conn.execute(
            "SELECT evidence,error_total,observations FROM world_model_evidence WHERE model_id=?",
            (model.model_id,),
        ).fetchone()
        if row:
            model.evidence = float(row[0])
            model.error_total = float(row[1])
            model.observations = int(row[2])
        return model

    def save(self, model: WorldModel) -> None:
        self.conn.execute(
            """INSERT INTO world_model_evidence(model_id,evidence,error_total,observations)
               VALUES(?,?,?,?)
               ON CONFLICT(model_id) DO UPDATE SET evidence=excluded.evidence,
                 error_total=excluded.error_total, observations=excluded.observations""",
            (model.model_id, model.evidence, model.error_total, model.observations),
        )
        self.conn.commit()
