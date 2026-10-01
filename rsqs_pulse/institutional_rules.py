from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from .domain_adapter import CanonicalRule


@dataclass(frozen=True)
class RuleDecision:
    scope: str
    subject: str
    effect: str | None
    rule_ids: tuple[str, ...]


class InstitutionalRuleStore:
    """
    Persistent target-agnostic institutional rule store.

    Rule precedence is deterministic: deny > require > allow.
    Exact scope/subject matches and '*' wildcards are supported.
    """

    _PRECEDENCE = {"allow": 1, "require": 2, "deny": 3}

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS institutional_rules(
          rule_id TEXT PRIMARY KEY,
          scope TEXT NOT NULL,
          effect TEXT NOT NULL,
          subject TEXT NOT NULL,
          source TEXT NOT NULL,
          updated_at INTEGER NOT NULL
        )
        """)
        self.conn.commit()

    def add(
        self,
        rule: CanonicalRule,
        *,
        updated_at: int | None = None,
    ) -> None:
        updated_at = int(time.time()) if updated_at is None else int(updated_at)
        self.conn.execute(
            """INSERT INTO institutional_rules(
               rule_id,scope,effect,subject,source,updated_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(rule_id) DO UPDATE SET
                 scope=excluded.scope,
                 effect=excluded.effect,
                 subject=excluded.subject,
                 source=excluded.source,
                 updated_at=excluded.updated_at""",
            (
                rule.rule_id,
                rule.scope,
                rule.effect,
                rule.subject,
                rule.source,
                updated_at,
            ),
        )
        self.conn.commit()

    def remove(self, rule_id: str) -> None:
        self.conn.execute(
            "DELETE FROM institutional_rules WHERE rule_id=?",
            (rule_id,),
        )
        self.conn.commit()

    def rules(self) -> tuple[CanonicalRule, ...]:
        rows = self.conn.execute(
            """SELECT rule_id,scope,effect,subject,source
               FROM institutional_rules ORDER BY rule_id"""
        ).fetchall()
        return tuple(CanonicalRule(*row) for row in rows)

    def decide(self, scope: str, subject: str) -> RuleDecision:
        rows = self.conn.execute(
            """SELECT rule_id,scope,effect,subject,source
               FROM institutional_rules
               WHERE scope IN (?, '*') AND subject IN (?, '*')
               ORDER BY rule_id""",
            (scope, subject),
        ).fetchall()
        if not rows:
            return RuleDecision(scope, subject, None, ())
        rules = [CanonicalRule(*row) for row in rows]
        highest = max(self._PRECEDENCE[rule.effect] for rule in rules)
        effect = next(
            name for name, priority in self._PRECEDENCE.items()
            if priority == highest
        )
        selected = tuple(
            sorted(
                rule.rule_id
                for rule in rules
                if self._PRECEDENCE[rule.effect] == highest
            )
        )
        return RuleDecision(scope, subject, effect, selected)
