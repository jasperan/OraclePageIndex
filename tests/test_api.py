"""Tests for FastAPI endpoints."""
from unittest.mock import MagicMock, patch
from dataclasses import asdict

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_graph():
    return MagicMock()


@pytest.fixture
def mock_query_engine():
    return MagicMock()


@pytest.fixture
def client(mock_graph, mock_query_engine):
    """Create a TestClient with mocked backend.

    We patch the module-level globals *before* the app handles any request
    so that endpoint functions see our mocks instead of ``None``.
    """
    with patch("api.server.graph", mock_graph), \
         patch("api.server.query_engine", mock_query_engine):
        from api.server import app
        from fastapi.testclient import TestClient
        yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client_no_backend():
    """TestClient where both graph and query_engine are None."""
    with patch("api.server.graph", None), \
         patch("api.server.query_engine", None):
        from api.server import app
        from fastapi.testclient import TestClient
        yield TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Index page
# ---------------------------------------------------------------------------

def test_index_page(client):
    resp = client.get("/")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /api/graph
# ---------------------------------------------------------------------------

def test_graph_endpoint_full(client, mock_graph):
    mock_graph.get_full_graph_data.return_value = {
        "nodes": [{"id": 1}],
        "edges": [{"source": 1, "target": 2}],
    }
    resp = client.get("/api/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert data["nodes"] == [{"id": 1}]
    assert data["edges"] == [{"source": 1, "target": 2}]
    mock_graph.get_full_graph_data.assert_called_once()


def test_graph_endpoint_versioned(client, mock_graph):
    mock_graph.get_versioned_graph_data.return_value = {
        "nodes": [{"id": 2, "temporal_status": "APPEARED"}],
        "edges": [],
    }
    resp = client.get("/api/graph", params={"doc_group": "test", "version": 2})
    assert resp.status_code == 200
    data = resp.json()
    assert data["nodes"][0]["temporal_status"] == "APPEARED"
    mock_graph.get_versioned_graph_data.assert_called_once_with("test", 2)


def test_graph_endpoint_no_backend(client_no_backend):
    resp = client_no_backend.get("/api/graph")
    assert resp.status_code == 200
    assert resp.json() == {"nodes": [], "edges": []}


# ---------------------------------------------------------------------------
# /api/documents
# ---------------------------------------------------------------------------

def test_documents_endpoint(client, mock_graph):
    mock_graph.get_all_documents.return_value = [
        {"id": 1, "title": "Doc A"},
    ]
    resp = client.get("/api/documents")
    assert resp.status_code == 200
    assert resp.json() == [{"id": 1, "title": "Doc A"}]
    mock_graph.get_all_documents.assert_called_once()


# ---------------------------------------------------------------------------
# /api/entities
# ---------------------------------------------------------------------------

def test_entities_endpoint(client, mock_graph):
    mock_graph.get_all_entities.return_value = [
        {"id": 1, "name": "Apple", "type": "ORGANIZATION"},
    ]
    resp = client.get("/api/entities")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    mock_graph.get_all_entities.assert_called_once()


# ---------------------------------------------------------------------------
# /api/query
# ---------------------------------------------------------------------------

def test_query_endpoint(client, mock_query_engine):
    from oracle_pageindex.models import QueryResult

    result = QueryResult(
        answer="test answer",
        sources=[],
        concepts=["c"],
        graph_queries=[],
        traversal_path=[],
        session_id=1,
    )
    mock_query_engine.query.return_value = result

    resp = client.get("/api/query", params={"q": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "test answer"
    assert data["session_id"] == 1
    assert "graph_queries" in data
    assert "traversal_path" in data
    mock_query_engine.query.assert_called_once_with("test", None)


def test_query_endpoint_with_session(client, mock_query_engine):
    from oracle_pageindex.models import QueryResult

    result = QueryResult(
        answer="follow-up",
        sources=[],
        concepts=[],
        session_id=5,
    )
    mock_query_engine.query.return_value = result

    resp = client.get("/api/query", params={"q": "test", "session_id": 5})
    assert resp.status_code == 200
    mock_query_engine.query.assert_called_once_with("test", 5)


def test_query_endpoint_no_engine(client_no_backend):
    resp = client_no_backend.get("/api/query", params={"q": "test"})
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# /api/sessions
# ---------------------------------------------------------------------------

def test_sessions_endpoint(client, mock_graph):
    mock_graph.list_sessions.return_value = [
        {"session_id": 1, "created_at": "2025-01-01"},
        {"session_id": 2, "created_at": "2025-01-02"},
    ]
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    mock_graph.list_sessions.assert_called_once()


def test_session_turns_endpoint(client, mock_graph):
    mock_graph.get_session_turns.return_value = [
        {"turn_id": 1, "question": "hi", "answer": "hello"},
    ]
    resp = client.get("/api/sessions/1/turns")
    assert resp.status_code == 200
    assert resp.json()[0]["question"] == "hi"
    mock_graph.get_session_turns.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# /api/entities/{name}/sections and /related
# ---------------------------------------------------------------------------

def test_entity_sections_endpoint(client, mock_graph):
    mock_graph.get_entity_sections.return_value = [
        {"section_id": 10, "title": "Intro"},
    ]
    resp = client.get("/api/entities/Apple/sections")
    assert resp.status_code == 200
    assert resp.json()[0]["section_id"] == 10
    mock_graph.get_entity_sections.assert_called_once_with("Apple")


def test_related_entities_endpoint(client, mock_graph):
    mock_graph.get_related_entities.return_value = [
        {"name": "Google", "relationship": "COMPETES_WITH"},
    ]
    resp = client.get("/api/entities/Apple/related")
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "Google"
    mock_graph.get_related_entities.assert_called_once_with("Apple")
