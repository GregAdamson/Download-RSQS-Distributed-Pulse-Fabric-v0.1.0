from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Dict, List
from .model import Pulse


@dataclass(frozen=True)
class Subscription:
    subscriber_id: str
    kinds: tuple[str, ...]


class SubscriptionRouter:
    def __init__(self) -> None:
        self._subscriptions: Dict[str, tuple[Subscription, Callable[[Pulse], None]]] = {}

    def subscribe(self, subscription: Subscription, callback: Callable[[Pulse], None]) -> None:
        self._subscriptions[subscription.subscriber_id] = (subscription, callback)

    def unsubscribe(self, subscriber_id: str) -> None:
        self._subscriptions.pop(subscriber_id, None)

    def publish(self, pulse: Pulse) -> List[str]:
        delivered: List[str] = []
        for subscriber_id in sorted(self._subscriptions):
            subscription, callback = self._subscriptions[subscriber_id]
            if "*" in subscription.kinds or pulse.kind in subscription.kinds:
                callback(pulse)
                delivered.append(subscriber_id)
        return delivered
