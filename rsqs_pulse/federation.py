from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class FederationScope:
    institution: str
    region: str = ""
    global_namespace: str = "rsqs"

    @property
    def topic_prefix(self) -> str:
        parts = [self.global_namespace]
        if self.region:
            parts.append(self.region)
        parts.append(self.institution)
        return ".".join(parts)


def within_scope(topic: str, scope: FederationScope) -> bool:
    prefix = scope.topic_prefix
    return topic == prefix or topic.startswith(prefix + ".")
