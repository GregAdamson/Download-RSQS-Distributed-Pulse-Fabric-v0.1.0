from __future__ import annotations
from typing import Callable, List
from .model import Pulse


class InMemoryBroker:
    def __init__(self) -> None:
        self._subs: List[Callable[[Pulse], None]] = []

    def subscribe(self, fn: Callable[[Pulse], None]) -> None:
        self._subs.append(fn)

    def publish(self, pulse: Pulse) -> None:
        for fn in list(self._subs):
            fn(pulse)
