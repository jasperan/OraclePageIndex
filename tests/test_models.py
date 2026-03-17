"""Tests for shared data models."""
from oracle_pageindex.models import (
    GraphQuery, TraversalStep, QueryResult, QueryIntent,
)

def test_query_intent_values():
    assert QueryIntent.LOOKUP.value == "LOOKUP"
    assert QueryIntent.RELATIONSHIP.value == "RELATIONSHIP"
    assert QueryIntent.EXPLORATION.value == "EXPLORATION"
    assert QueryIntent.COMPARISON.value == "COMPARISON"
    assert QueryIntent.HIERARCHICAL.value == "HIERARCHICAL"
    assert QueryIntent.TEMPORAL.value == "TEMPORAL"

def test_graph_query_dataclass():
    gq = GraphQuery(
        sql="SELECT 1 FROM dual",
        params={"x": 1},
        purpose="Test query",
        rows_returned=1,
        execution_ms=2.5,
    )
    assert gq.sql == "SELECT 1 FROM dual"
    assert gq.execution_ms == 2.5

def test_traversal_step_dataclass():
    ts = TraversalStep(
        step_number=1,
        node_type="entity",
        node_id=42,
        node_label="Apple Inc.",
        edge_label="mentions",
        edge_direction="reverse",
        reason="Matched concept 'Apple'",
    )
    assert ts.node_type == "entity"
    assert ts.edge_direction == "reverse"

def test_query_result_defaults():
    qr = QueryResult(answer="test", sources=[], concepts=[])
    assert qr.graph_queries == []
    assert qr.traversal_path == []
    assert qr.related_entities == []
    assert qr.session_id is None

def test_query_result_full():
    gq = GraphQuery("SQL", {}, "purpose", 5, 1.0)
    ts = TraversalStep(1, "entity", 1, "X", None, "forward", "reason")
    qr = QueryResult(
        answer="answer",
        sources=[{"title": "T"}],
        concepts=["c"],
        related_entities=[{"name": "E"}],
        graph_queries=[gq],
        traversal_path=[ts],
        session_id=7,
    )
    assert len(qr.graph_queries) == 1
    assert qr.session_id == 7
