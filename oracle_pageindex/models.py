"""Shared data models for OraclePageIndex v2."""
from dataclasses import dataclass, field
from enum import Enum


class QueryIntent(Enum):
    LOOKUP = "LOOKUP"
    RELATIONSHIP = "RELATIONSHIP"
    EXPLORATION = "EXPLORATION"
    COMPARISON = "COMPARISON"
    HIERARCHICAL = "HIERARCHICAL"
    TEMPORAL = "TEMPORAL"


@dataclass
class GraphQuery:
    sql: str
    params: dict
    purpose: str
    rows_returned: int
    execution_ms: float


@dataclass
class TraversalStep:
    step_number: int
    node_type: str
    node_id: int
    node_label: str
    edge_label: str | None
    edge_direction: str
    reason: str


@dataclass
class QueryResult:
    answer: str
    sources: list[dict]
    concepts: list[str]
    related_entities: list[dict] = field(default_factory=list)
    graph_queries: list[GraphQuery] = field(default_factory=list)
    traversal_path: list[TraversalStep] = field(default_factory=list)
    session_id: int | None = None
