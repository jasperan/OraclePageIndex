"""Tests for temporal document versioning.

Covers:
- Version-aware document insertion (backward compat + new params)
- Temporal query methods on GraphStore
- Temporal edge insertion
- Temporal diff computation in the Indexer
"""
from unittest.mock import MagicMock, patch, call
import pytest

from oracle_pageindex.graph import GraphStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_graph():
    mock_db = MagicMock()
    mock_db.execute_returning.return_value = 1
    mock_db.fetchall.return_value = []
    mock_db.fetchone.return_value = None
    return GraphStore(mock_db), mock_db


# ---------------------------------------------------------------------------
# GraphStore: insert_document with version params
# ---------------------------------------------------------------------------

class TestInsertDocumentVersioning:
    def test_insert_document_with_version(self):
        gs, db = _make_graph()
        db.execute_returning.return_value = 2
        doc_id = gs.insert_document(
            "apple-10k-2024.pdf", "Annual report", "/path",
            doc_group="apple-10k", doc_version=2,
        )
        assert doc_id == 2
        call_sql = db.execute_returning.call_args[0][0]
        assert "doc_group" in call_sql
        assert "doc_version" in call_sql

    def test_insert_document_without_version(self):
        """Backward compat: no group/version still works."""
        gs, db = _make_graph()
        doc_id = gs.insert_document("test.pdf", "desc", "/path")
        assert doc_id == 1
        # Verify default values were passed
        call_params = db.execute_returning.call_args[0][1]
        assert call_params["doc_group"] is None
        assert call_params["doc_version"] == 1

    def test_insert_document_group_only(self):
        """Supplying doc_group without doc_version uses default version 1."""
        gs, db = _make_graph()
        doc_id = gs.insert_document("v1.pdf", "first", "/path", doc_group="reports")
        assert doc_id == 1
        call_params = db.execute_returning.call_args[0][1]
        assert call_params["doc_group"] == "reports"
        assert call_params["doc_version"] == 1


# ---------------------------------------------------------------------------
# GraphStore: temporal query methods
# ---------------------------------------------------------------------------

class TestTemporalQueries:
    def test_get_previous_version(self):
        gs, db = _make_graph()
        db.fetchone.return_value = {"doc_id": 1, "doc_name": "v1.pdf", "doc_version": 1}
        prev = gs.get_previous_version(doc_group="apple-10k", current_version=2)
        assert prev["doc_id"] == 1
        assert prev["doc_version"] == 1

    def test_get_previous_version_none(self):
        gs, db = _make_graph()
        db.fetchone.return_value = None
        prev = gs.get_previous_version(doc_group="apple-10k", current_version=1)
        assert prev is None

    def test_get_doc_entities(self):
        gs, db = _make_graph()
        db.fetchall.return_value = [
            {"entity_id": 1, "name": "Apple", "entity_type": "ORGANIZATION"},
            {"entity_id": 2, "name": "iPhone", "entity_type": "TECHNOLOGY"},
        ]
        entities = gs.get_doc_entities(doc_id=1)
        assert len(entities) == 2
        assert entities[0]["name"] == "Apple"
        assert entities[1]["entity_type"] == "TECHNOLOGY"

    def test_get_doc_entities_empty(self):
        gs, db = _make_graph()
        db.fetchall.return_value = []
        entities = gs.get_doc_entities(doc_id=999)
        assert entities == []


# ---------------------------------------------------------------------------
# GraphStore: temporal edge methods
# ---------------------------------------------------------------------------

class TestTemporalEdges:
    def test_insert_temporal_edge(self):
        gs, db = _make_graph()
        gs.insert_temporal_edge(
            source_doc_id=1, target_doc_id=2, entity_id=5,
            change_type="APPEARED", new_value="New entity",
        )
        db.execute.assert_called_once()
        call_sql = db.execute.call_args[0][0]
        assert "temporal_edges" in call_sql

    def test_insert_temporal_edge_all_params(self):
        gs, db = _make_graph()
        gs.insert_temporal_edge(
            source_doc_id=1, target_doc_id=2, entity_id=3,
            change_type="DISAPPEARED", old_value="Old text",
            new_value=None, confidence=0.9,
        )
        call_params = db.execute.call_args[0][1]
        assert call_params["change_type"] == "DISAPPEARED"
        assert call_params["old_value"] == "Old text"
        assert call_params["confidence"] == 0.9

    def test_insert_temporal_edge_stable(self):
        gs, db = _make_graph()
        gs.insert_temporal_edge(
            source_doc_id=1, target_doc_id=2, entity_id=10,
            change_type="STABLE",
        )
        call_params = db.execute.call_args[0][1]
        assert call_params["change_type"] == "STABLE"
        assert call_params["old_value"] is None
        assert call_params["new_value"] is None

    def test_get_temporal_changes(self):
        gs, db = _make_graph()
        db.fetchall.return_value = [
            {
                "edge_id": 1, "entity_id": 1, "name": "AI",
                "entity_type": "TECHNOLOGY", "change_type": "APPEARED",
                "old_value": None, "new_value": None, "confidence": 1.0,
            },
            {
                "edge_id": 2, "entity_id": 2, "name": "Nokia",
                "entity_type": "ORGANIZATION", "change_type": "DISAPPEARED",
                "old_value": None, "new_value": None, "confidence": 1.0,
            },
        ]
        changes = gs.get_temporal_changes(
            doc_group="apple-10k", version_from=1, version_to=2,
        )
        appeared = [c for c in changes if c["change_type"] == "APPEARED"]
        disappeared = [c for c in changes if c["change_type"] == "DISAPPEARED"]
        assert len(appeared) == 1
        assert len(disappeared) == 1
        assert appeared[0]["name"] == "AI"
        assert disappeared[0]["name"] == "Nokia"

    def test_get_temporal_changes_empty(self):
        gs, db = _make_graph()
        db.fetchall.return_value = []
        changes = gs.get_temporal_changes(
            doc_group="nonexistent", version_from=1, version_to=2,
        )
        assert changes == []


# ---------------------------------------------------------------------------
# Indexer: _compute_temporal_diff
# ---------------------------------------------------------------------------

class TestComputeTemporalDiff:
    def _make_indexer(self):
        """Build an Indexer with fully mocked dependencies."""
        from oracle_pageindex.indexer import Indexer

        mock_llm = MagicMock()
        mock_db = MagicMock()
        mock_db.execute_returning.return_value = 1
        mock_db.fetchone.return_value = None
        mock_db.fetchall.return_value = []

        mock_opt = MagicMock()
        mock_opt.toc_check_page_num = 20
        mock_opt.max_token_num_each_node = 20000
        mock_opt.pdf_parser = "PyMuPDF"
        mock_opt.if_add_node_id = "yes"
        mock_opt.if_add_node_summary = "yes"
        mock_opt.if_extract_entities = "no"

        indexer = Indexer(llm=mock_llm, db=mock_db, opt=mock_opt)
        return indexer

    def test_no_previous_version_skips(self):
        indexer = self._make_indexer()
        indexer.graph = MagicMock()
        indexer.graph.get_previous_version.return_value = None

        # Should not raise; just logs and returns
        indexer._compute_temporal_diff(doc_id=2, doc_group="reports", doc_version=1)
        indexer.graph.get_previous_version.assert_called_once_with("reports", 1)
        indexer.graph.insert_temporal_edge.assert_not_called()

    def test_diff_with_appeared_and_disappeared(self):
        indexer = self._make_indexer()
        indexer.graph = MagicMock()

        # Previous version exists
        indexer.graph.get_previous_version.return_value = {
            "doc_id": 1, "doc_name": "v1.pdf", "doc_version": 1,
        }
        # Previous doc has entities: Apple, Nokia
        indexer.graph.get_doc_entities.side_effect = [
            # prev doc (doc_id=1)
            [
                {"entity_id": 10, "name": "Apple", "entity_type": "ORGANIZATION"},
                {"entity_id": 20, "name": "Nokia", "entity_type": "ORGANIZATION"},
            ],
            # curr doc (doc_id=2)
            [
                {"entity_id": 10, "name": "Apple", "entity_type": "ORGANIZATION"},
                {"entity_id": 30, "name": "AI", "entity_type": "TECHNOLOGY"},
            ],
        ]
        # All entities for the map
        indexer.graph.get_all_entities.return_value = [
            {"entity_id": 10, "name": "Apple", "entity_type": "ORGANIZATION"},
            {"entity_id": 20, "name": "Nokia", "entity_type": "ORGANIZATION"},
            {"entity_id": 30, "name": "AI", "entity_type": "TECHNOLOGY"},
        ]

        indexer._compute_temporal_diff(doc_id=2, doc_group="reports", doc_version=2)

        # Should have inserted 3 temporal edges: 1 APPEARED, 1 DISAPPEARED, 1 STABLE
        assert indexer.graph.insert_temporal_edge.call_count == 3

        # Collect the change_types from all calls (4th positional arg)
        change_types = [
            c[0][3] for c in indexer.graph.insert_temporal_edge.call_args_list
        ]
        assert "APPEARED" in change_types
        assert "DISAPPEARED" in change_types
        assert "STABLE" in change_types

    def test_diff_all_stable(self):
        indexer = self._make_indexer()
        indexer.graph = MagicMock()

        indexer.graph.get_previous_version.return_value = {
            "doc_id": 1, "doc_name": "v1.pdf", "doc_version": 1,
        }
        shared_entities = [
            {"entity_id": 10, "name": "Apple", "entity_type": "ORGANIZATION"},
        ]
        indexer.graph.get_doc_entities.side_effect = [shared_entities, shared_entities]
        indexer.graph.get_all_entities.return_value = shared_entities

        indexer._compute_temporal_diff(doc_id=2, doc_group="reports", doc_version=2)

        # Only STABLE edges
        assert indexer.graph.insert_temporal_edge.call_count == 1
        call_args = indexer.graph.insert_temporal_edge.call_args
        assert call_args[0][3] == "STABLE"  # change_type is the 4th positional arg

    def test_diff_all_new(self):
        """First version with entities but empty previous version."""
        indexer = self._make_indexer()
        indexer.graph = MagicMock()

        indexer.graph.get_previous_version.return_value = {
            "doc_id": 1, "doc_name": "v1.pdf", "doc_version": 1,
        }
        indexer.graph.get_doc_entities.side_effect = [
            [],  # prev doc: no entities
            [{"entity_id": 10, "name": "X", "entity_type": "CONCEPT"}],  # curr
        ]
        indexer.graph.get_all_entities.return_value = [
            {"entity_id": 10, "name": "X", "entity_type": "CONCEPT"},
        ]

        indexer._compute_temporal_diff(doc_id=2, doc_group="g", doc_version=2)

        assert indexer.graph.insert_temporal_edge.call_count == 1
        call_args = indexer.graph.insert_temporal_edge.call_args
        assert call_args[0][3] == "APPEARED"
