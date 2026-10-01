from __future__ import annotations
from typing import Any, Callable, Dict
from .persistent import SQLiteState


class OfflineJournal:
    def __init__(self, node_id: str, state: SQLiteState) -> None:
        self.node_id = node_id
        self.state = state

    def append(self, event: Dict[str, Any]) -> int:
        return self.state.queue_offline(self.node_id, event)

    def reconcile(self, sender: Callable[[Dict[str, Any]], bool]) -> int:
        count = 0
        for seq, event in list(self.state.pending_offline(self.node_id)):
            if not sender(event):
                break
            self.state.mark_reconciled(seq)
            count += 1
        return count
