from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class DALNode:
    kind: str
    node_id: str
    attributes: Dict[str, Any]


@dataclass(frozen=True)
class DALEdge:
    source: str
    relation: str
    target: str


class DALGraph:
    ALLOWED_KINDS = {
        "STATE", "OBSERVATION", "DESIRED_STATE", "DEFICIENCY", "GOAL",
        "CONSTRAINT", "TRAJECTORY", "ACTION", "AGENT", "CAPABILITY",
        "OUTCOME", "EVIDENCE", "CAUSE", "EFFECT", "SKILL",
        "COUNTERFACTUAL", "LESSON", "PROVENANCE",
    }

    def __init__(self) -> None:
        self.nodes: Dict[str, DALNode] = {}
        self.edges: list[DALEdge] = []

    def add_node(self, node: DALNode) -> None:
        if node.kind not in self.ALLOWED_KINDS:
            raise ValueError(f"unsupported DAL kind: {node.kind}")
        self.nodes[node.node_id] = node

    def connect(self, source: str, relation: str, target: str) -> None:
        if source not in self.nodes or target not in self.nodes:
            raise KeyError("DAL edge endpoint missing")
        self.edges.append(DALEdge(source, relation, target))

    def snapshot(self) -> Tuple[Tuple[DALNode, ...], Tuple[DALEdge, ...]]:
        return tuple(self.nodes[k] for k in sorted(self.nodes)), tuple(self.edges)
