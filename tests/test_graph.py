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
