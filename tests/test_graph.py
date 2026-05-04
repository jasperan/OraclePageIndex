import pytest
from unittest.mock import MagicMock
from oracle_pageindex.graph import GraphStore


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute_returning.return_value = 1
    db.fetchall.return_value = []
    db.fetchone.return_value = None
    return db


@pytest.fixture
def store(mock_db):
    return GraphStore(mock_db)


def test_insert_document(store, mock_db):
    doc_id = store.insert_document("test.pdf", "A test document", "/path/test.pdf")
    assert doc_id == 1
    mock_db.execute_returning.assert_called_once()


def test_insert_section(store, mock_db):
    section_id = store.insert_section(
        doc_id=1, node_id="0001", title="Introduction",
        summary="Intro text", text_content="Full text",
        start_index=1, end_index=3, depth_level=0
    )
    assert section_id == 1


def test_insert_entity(store, mock_db):
    mock_db.fetchone.return_value = None
    entity_id = store.upsert_entity("machine learning", "CONCEPT", "ML description")
    assert entity_id == 1


def test_upsert_entity_existing(store, mock_db):
    mock_db.fetchone.return_value = {"entity_id": 42}
    entity_id = store.upsert_entity("machine learning", "CONCEPT", "ML description")
    assert entity_id == 42
    mock_db.execute_returning.assert_not_called()


def test_insert_hierarchy_edge(store, mock_db):
    store.insert_hierarchy_edge(parent_id=1, child_id=2)
    mock_db.execute.assert_called_once()


def test_insert_mention_edge(store, mock_db):
    store.insert_mention_edge(section_id=1, entity_id=1, relevance="DEFINES")
    mock_db.execute.assert_called_once()


def test_insert_entity_relationship(store, mock_db):
    store.insert_entity_relationship(source_id=1, target_id=2, relationship="PART_OF")
    mock_db.execute.assert_called_once()


def test_get_all_documents(store, mock_db):
    mock_db.fetchall.return_value = [
        {"doc_id": 1, "doc_name": "test.pdf"},
    ]
    docs = store.get_all_documents()
    assert len(docs) == 1
    assert docs[0]["doc_name"] == "test.pdf"


def test_get_document_sections(store, mock_db):
    mock_db.fetchall.return_value = [
        {"section_id": 1, "title": "Intro", "doc_id": 1},
        {"section_id": 2, "title": "Body", "doc_id": 1},
    ]
    sections = store.get_document_sections(doc_id=1)
    assert len(sections) == 2
    mock_db.fetchall.assert_called_once()


def test_get_sections_by_ids_returns_mapping(store, mock_db):
    mock_db.fetchall.return_value = [
        {"section_id": 2, "title": "Body", "doc_name": "report.pdf"},
        {"section_id": 1, "title": "Intro", "doc_name": "report.pdf"},
    ]

    sections = store.get_sections_by_ids([2, 1, 2])

    assert sections[1]["title"] == "Intro"
    assert sections[2]["doc_name"] == "report.pdf"
    sql, params = mock_db.fetchall.call_args[0]
    assert "JOIN documents" in sql
    assert params == {"id_0": 2, "id_1": 1}


def test_get_sections_by_ids_empty_skips_query(store, mock_db):
    assert store.get_sections_by_ids([]) == {}
    mock_db.fetchall.assert_not_called()


def test_get_section_children(store, mock_db):
    mock_db.fetchall.return_value = [
        {"section_id": 3, "title": "Sub-section"},
    ]
    children = store.get_section_children(section_id=1)
    assert len(children) == 1


def test_get_section_entities(store, mock_db):
    mock_db.fetchall.return_value = [
        {"entity_id": 1, "name": "ML", "entity_type": "CONCEPT", "relevance": "DEFINES"},
    ]
    entities = store.get_section_entities(section_id=1)
    assert len(entities) == 1
    assert entities[0]["name"] == "ML"


def test_get_all_entities(store, mock_db):
    mock_db.fetchall.return_value = [
        {"entity_id": 1, "name": "ML", "entity_type": "CONCEPT"},
    ]
    entities = store.get_all_entities()
    assert len(entities) == 1
    call_sql = mock_db.fetchall.call_args[0][0]
    assert "name_embedding" not in call_sql
    assert "canonical_id" in call_sql


def test_get_entity_sections(store, mock_db):
    mock_db.fetchall.return_value = [
        {"section_id": 1, "title": "Intro", "doc_name": "test.pdf", "relevance": "MENTIONS"},
    ]
    sections = store.get_entity_sections("machine learning")
    assert len(sections) == 1
    assert sections[0]["doc_name"] == "test.pdf"


def test_get_related_entities(store, mock_db):
    mock_db.fetchall.return_value = [
        {"entity_id": 2, "name": "deep learning", "relationship": "PART_OF"},
    ]
    related = store.get_related_entities("machine learning")
    assert len(related) == 1
    assert related[0]["relationship"] == "PART_OF"


def test_get_full_graph_data_empty(store, mock_db):
    mock_db.fetchall.return_value = []
    data = store.get_full_graph_data()
    assert data == {"nodes": [], "edges": []}


def test_get_full_graph_data_populated(store, mock_db):
    call_count = [0]
    return_values = [
        # documents
        [{"doc_id": 1, "doc_name": "test.pdf"}],
        # sections
        [{"section_id": 1, "title": "Intro", "doc_id": 1}],
        # entities
        [{"entity_id": 1, "name": "ML", "entity_type": "CONCEPT"}],
        # section_hierarchy
        [],
        # section_entities
        [{"section_id": 1, "entity_id": 1, "relevance": "DEFINES"}],
        # entity_relationships
        [],
    ]

    def side_effect(*args, **kwargs):
        idx = call_count[0]
        call_count[0] += 1
        return return_values[idx]

    mock_db.fetchall.side_effect = side_effect

    data = store.get_full_graph_data()
    assert len(data["nodes"]) == 3
    assert len(data["edges"]) == 2

    # Check node types
    types = {n["type"] for n in data["nodes"]}
    assert types == {"document", "section", "entity"}

    # Check node IDs follow the expected pattern
    ids = {n["id"] for n in data["nodes"]}
    assert "doc_1" in ids
    assert "sec_1" in ids
    assert "ent_1" in ids


def test_graph_query_entity_sections(store, mock_db):
    mock_db.fetchall.return_value = [
        {"section_id": 1, "section_title": "Intro", "entity_name": "ML"},
    ]
    result = store.graph_query_entity_sections("ML")
    assert len(result) == 1
    mock_db.fetchall.assert_called_once()


def test_graph_query_related_entities(store, mock_db):
    mock_db.fetchall.return_value = [
        {"source_name": "ML", "related_name": "DL", "relationship": "RELATED_TO"},
    ]
    result = store.graph_query_related_entities("ML")
    assert len(result) == 1


def test_graph_query_section_children(store, mock_db):
    mock_db.fetchall.return_value = [
        {"parent_title": "Chapter 1", "child_title": "Section 1.1", "child_depth": 1},
    ]
    result = store.graph_query_section_children("Chapter 1")
    assert len(result) == 1
    assert result[0]["child_title"] == "Section 1.1"


class TestMultiHopTraversal:
    """Tests for multi-hop GRAPH_TABLE traversal methods."""

    def setup_method(self):
        self.mock_db = MagicMock()
        self.gs = GraphStore(self.mock_db)

    def test_traverse_entity_neighborhood(self):
        self.mock_db.fetchall.return_value = [
            {"section_id": 1, "title": "Risk Factors", "text_content": "...",
             "depth_level": 1, "relevance": "DISCUSSES",
             "co_entity_id": 2, "co_entity_name": "China",
             "co_entity_type": "LOCATION"}
        ]
        result = self.gs.traverse_entity_neighborhood(42)
        assert len(result["sections"]) == 1
        assert result["sections"][0]["title"] == "Risk Factors"
        assert len(result["entities"]) == 1
        assert result["graph_query"].purpose != ""
        call_sql = self.mock_db.fetchall.call_args[0][0]
        assert "GRAPH_TABLE" in call_sql

    def test_traverse_entity_neighborhood_deduplicates(self):
        """Same section appearing with different co-entities should be deduped."""
        self.mock_db.fetchall.return_value = [
            {"section_id": 1, "title": "Risk", "text_content": "...",
             "depth_level": 1, "relevance": "DISCUSSES",
             "co_entity_id": 2, "co_entity_name": "China", "co_entity_type": "LOCATION"},
            {"section_id": 1, "title": "Risk", "text_content": "...",
             "depth_level": 1, "relevance": "DISCUSSES",
             "co_entity_id": 3, "co_entity_name": "India", "co_entity_type": "LOCATION"},
        ]
        result = self.gs.traverse_entity_neighborhood(42)
        assert len(result["sections"]) == 1  # deduplicated
        assert len(result["entities"]) == 2  # both entities kept

    def test_traverse_entity_neighborhood_empty(self):
        self.mock_db.fetchall.return_value = []
        result = self.gs.traverse_entity_neighborhood(99)
        assert result["sections"] == []
        assert result["entities"] == []

    def test_traverse_section_ancestors(self):
        self.mock_db.fetchall.return_value = [
            {"section_id": 10, "title": "Introduction", "depth_level": 0, "tree_level": 1}
        ]
        result = self.gs.traverse_section_ancestors(20)
        assert len(result) == 1

    def test_traverse_section_descendants(self):
        self.mock_db.fetchall.return_value = [
            {"section_id": 21, "title": "Sub-section A", "depth_level": 2, "tree_level": 1},
            {"section_id": 22, "title": "Sub-section B", "depth_level": 2, "tree_level": 1},
        ]
        result = self.gs.traverse_section_descendants(10)
        assert len(result) == 2

    def test_find_entity_paths(self):
        self.mock_db.fetchall.return_value = [
            {"source_name": "Apple", "mid_id": 5, "mid_name": "iPhone",
             "mid_type": "TECHNOLOGY", "r1_type": "PART_OF",
             "target_name": "Qualcomm", "r2_type": "USED_BY"}
        ]
        result = self.gs.find_entity_paths("Apple", "Qualcomm")
        assert len(result["paths"]) == 1
        assert result["paths"][0]["mid_name"] == "iPhone"
        assert result["graph_query"].purpose != ""

    def test_find_entity_paths_empty(self):
        self.mock_db.fetchall.return_value = []
        result = self.gs.find_entity_paths("A", "B")
        assert result["paths"] == []

    def test_get_multi_hop_entities(self):
        self.mock_db.fetchall.return_value = [
            {"entity_id": 2, "name": "iPhone", "entity_type": "TECHNOLOGY",
             "relationship": "PART_OF", "hops": 1},
            {"entity_id": 3, "name": "Qualcomm", "entity_type": "ORGANIZATION",
             "relationship": "USED_BY", "hops": 2},
        ]
        result = self.gs.get_multi_hop_entities(entity_id=1, max_hops=2)
        assert len(result["entities"]) == 2
        assert result["entities"][0]["hops"] == 1

    def test_get_multi_hop_entities_single_hop(self):
        self.mock_db.fetchall.return_value = [
            {"entity_id": 2, "name": "iPhone", "entity_type": "TECH",
             "relationship": "PART_OF", "hops": 1}
        ]
        result = self.gs.get_multi_hop_entities(entity_id=1, max_hops=1)
        assert len(result["entities"]) == 1
        # Verify SQL does NOT contain UNION for single hop
        call_sql = self.mock_db.fetchall.call_args[0][0]
        assert "UNION" not in call_sql
