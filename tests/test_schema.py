"""Tests for the expanded schema (Living Graph v2)."""
import re
from pathlib import Path


def _load_schema():
    sql_path = Path(__file__).parent.parent / "setup_schema.sql"
    return sql_path.read_text()


def test_schema_contains_new_vertex_tables():
    schema = _load_schema()
    assert "CREATE TABLE sessions" in schema
    assert "CREATE TABLE turns" in schema


def test_schema_contains_new_edge_tables():
    schema = _load_schema()
    assert "CREATE TABLE turn_entities" in schema
    assert "CREATE TABLE turn_sections" in schema
    assert "CREATE TABLE temporal_edges" in schema
    assert "CREATE TABLE entity_aliases" in schema


def test_schema_contains_new_document_columns():
    schema = _load_schema()
    # Find the documents CREATE TABLE block
    doc_match = re.search(r"CREATE TABLE documents\s*\((.*?)\);", schema, re.DOTALL)
    assert doc_match, "documents table not found"
    doc_body = doc_match.group(1)
    assert "doc_version" in doc_body
    assert "doc_group" in doc_body


def test_schema_contains_new_entity_columns():
    schema = _load_schema()
    ent_match = re.search(r"CREATE TABLE entities\s*\((.*?)\);", schema, re.DOTALL)
    assert ent_match, "entities table not found"
    ent_body = ent_match.group(1)
    assert "name_embedding" in ent_body
    assert "canonical_id" in ent_body
    assert "first_seen_doc" in ent_body
    assert "last_seen_doc" in ent_body


def test_schema_entity_relationships_has_source_and_confidence():
    schema = _load_schema()
    er_match = re.search(r"CREATE TABLE entity_relationships\s*\((.*?)\);", schema, re.DOTALL)
    assert er_match, "entity_relationships table not found"
    er_body = er_match.group(1)
    assert "edge_source" in er_body
    assert "confidence" in er_body


def test_property_graph_includes_new_vertex_tables():
    schema = _load_schema()
    pg_match = re.search(r"CREATE PROPERTY GRAPH doc_knowledge_graph(.*?);", schema, re.DOTALL)
    assert pg_match, "Property graph definition not found"
    pg_body = pg_match.group(1)
    assert "sessions" in pg_body
    assert "turns" in pg_body


def test_property_graph_includes_new_edge_tables():
    schema = _load_schema()
    pg_match = re.search(r"CREATE PROPERTY GRAPH doc_knowledge_graph(.*?);", schema, re.DOTALL)
    assert pg_match, "Property graph definition not found"
    pg_body = pg_match.group(1)
    assert "turn_entities" in pg_body
    assert "turn_sections" in pg_body
    assert "temporal_edges" in pg_body
    assert "entity_aliases" in pg_body


def test_schema_has_new_indexes():
    schema = _load_schema()
    assert "idx_turns_session" in schema
    assert "idx_docs_group" in schema
    assert "idx_alias_canonical" in schema


def test_schema_drops_new_tables():
    schema = _load_schema()
    # All new tables should appear in drop statements
    for table in ["turn_sections", "turn_entities", "temporal_edges",
                   "entity_aliases", "turns", "sessions"]:
        assert table.upper() in schema.upper() or f"'{table.upper()}'" in schema.upper(), \
            f"Drop statement for {table} not found"


def test_property_graph_has_5_vertices():
    schema = _load_schema()
    pg_match = re.search(r"CREATE PROPERTY GRAPH doc_knowledge_graph(.*?);", schema, re.DOTALL)
    assert pg_match, "Property graph definition not found"
    pg_body = pg_match.group(1)
    # Count LABEL keywords in VERTEX TABLES section
    vertex_section = re.search(r"VERTEX TABLES\s*\((.*?)\)\s*EDGE TABLES", pg_body, re.DOTALL)
    assert vertex_section, "VERTEX TABLES section not found"
    labels = re.findall(r'LABEL\s+(?:"\w+"|\w+)', vertex_section.group(1))
    assert len(labels) == 5, f"Expected 5 vertex labels, found {len(labels)}: {labels}"


def test_property_graph_has_7_edges():
    schema = _load_schema()
    pg_match = re.search(r"CREATE PROPERTY GRAPH doc_knowledge_graph(.*?);", schema, re.DOTALL)
    assert pg_match, "Property graph definition not found"
    pg_body = pg_match.group(1)
    # Count LABEL keywords in EDGE TABLES section
    edge_section = re.search(r"EDGE TABLES\s*\((.*)\)", pg_body, re.DOTALL)
    assert edge_section, "EDGE TABLES section not found"
    labels = re.findall(r"LABEL\s+\w+", edge_section.group(1))
    assert len(labels) == 7, f"Expected 7 edge labels, found {len(labels)}: {labels}"


def test_vector_index_commented_out():
    schema = _load_schema()
    assert "idx_entity_embedding" in schema
    # Should be commented out
    for line in schema.splitlines():
        if "idx_entity_embedding" in line:
            assert line.strip().startswith("--"), \
                "Vector index should be commented out"
            break


def test_no_reserved_word_source_column():
    """Ensure we use edge_source, not source (reserved word)."""
    schema = _load_schema()
    er_match = re.search(r"CREATE TABLE entity_relationships\s*\((.*?)\);", schema, re.DOTALL)
    assert er_match, "entity_relationships table not found"
    er_body = er_match.group(1)
    # Should have edge_source, not bare 'source' as column name
    assert "edge_source" in er_body
    # Make sure there's no standalone 'source' column (source_entity is fine)
    lines = er_body.splitlines()
    for line in lines:
        stripped = line.strip().lower()
        if stripped.startswith("source") and "source_entity" not in stripped and "edge_source" not in stripped:
            raise AssertionError(f"Found reserved word 'source' as column: {line.strip()}")
