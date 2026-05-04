"""Live Oracle integration tests for ``GraphStore``.

Strict run against this repo's docker-compose Oracle:

    ORACLE_GRAPH_INTEGRATION=1 ORACLE_DSN=localhost:1522/FREEPDB1 python -m pytest tests/test_graph_integration.py

Without ``ORACLE_GRAPH_INTEGRATION=1`` these tests always skip, because schema
initialization is destructive to the configured Oracle user.
"""

from __future__ import annotations

from dataclasses import dataclass
import inspect
import os
import re

import oracledb
import pytest

from oracle_pageindex.db import OracleDB
from oracle_pageindex.graph import GraphStore


STRICT_VALUES = {"1", "true", "yes", "on"}
PROVISION_SYS_VALUES = {"1", "true", "yes", "on"}
LOCAL_DSN_RE = re.compile(r"(^localhost[:/]|^127\.0\.0\.1[:/]|^::1[:/])")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("ORACLE_GRAPH_INTEGRATION", "").lower() not in STRICT_VALUES,
        reason=(
            "live Oracle integration tests are destructive; set "
            "ORACLE_GRAPH_INTEGRATION=1 to run"
        ),
    ),
]
EMBEDDING = [0.1] * 384
REQUIRED_SCHEMA_TABLES = {
    "documents",
    "sections",
    "entities",
    "sessions",
    "turns",
    "section_hierarchy",
    "section_entities",
    "entity_relationships",
    "turn_entities",
    "turn_sections",
    "temporal_edges",
    "entity_aliases",
}

PUBLIC_METHOD_COVERAGE = {
    "insert_document": "test_seeded_write_methods_persist_to_oracle",
    "insert_section": "test_seeded_write_methods_persist_to_oracle",
    "upsert_entity": "test_seeded_write_methods_persist_to_oracle",
    "insert_hierarchy_edge": "test_seeded_write_methods_persist_to_oracle",
    "insert_mention_edge": "test_seeded_write_methods_persist_to_oracle",
    "insert_entity_relationship": "test_seeded_write_methods_persist_to_oracle",
    "get_all_documents": "test_document_and_section_queries_use_live_rows",
    "get_document_sections": "test_document_and_section_queries_use_live_rows",
    "get_sections_by_ids": "test_document_and_section_queries_use_live_rows",
    "get_section_children": "test_document_and_section_queries_use_live_rows",
    "get_section_entities": "test_document_and_section_queries_use_live_rows",
    "get_all_entities": "test_entity_queries_and_resolution_use_live_rows",
    "find_similar_entities": "test_entity_queries_and_resolution_use_live_rows",
    "insert_entity_alias": "test_seeded_write_methods_persist_to_oracle",
    "update_entity_canonical": "test_seeded_write_methods_persist_to_oracle",
    "update_entity_embedding": "test_seeded_write_methods_persist_to_oracle",
    "get_entity_sections": "test_entity_queries_and_resolution_use_live_rows",
    "get_related_entities": "test_entity_queries_and_resolution_use_live_rows",
    "get_full_graph_data": "test_graph_visualization_methods_use_live_rows",
    "get_versioned_graph_data": "test_graph_visualization_methods_use_live_rows",
    "graph_query_entity_sections": "test_sql_pgq_graph_queries_run_on_oracle_property_graph",
    "graph_query_related_entities": "test_sql_pgq_graph_queries_run_on_oracle_property_graph",
    "graph_query_section_children": "test_sql_pgq_graph_queries_run_on_oracle_property_graph",
    "traverse_entity_neighborhood": "test_multihop_traversal_methods_run_on_oracle",
    "traverse_section_ancestors": "test_multihop_traversal_methods_run_on_oracle",
    "traverse_section_descendants": "test_multihop_traversal_methods_run_on_oracle",
    "find_entity_paths": "test_multihop_traversal_methods_run_on_oracle",
    "get_multi_hop_entities": "test_multihop_traversal_methods_run_on_oracle",
    "get_isolated_entities": "test_enrichment_support_methods_use_live_rows",
    "get_cooccurring_pairs": "test_enrichment_support_methods_use_live_rows",
    "get_shared_section_text": "test_enrichment_support_methods_use_live_rows",
    "insert_enriched_relationship": "test_seeded_write_methods_persist_to_oracle",
    "get_previous_version": "test_temporal_methods_use_live_rows",
    "get_doc_entities": "test_temporal_methods_use_live_rows",
    "insert_temporal_edge": "test_seeded_write_methods_persist_to_oracle",
    "get_temporal_changes": "test_temporal_methods_use_live_rows",
    "create_session": "test_session_methods_use_live_rows",
    "create_turn": "test_session_methods_use_live_rows",
    "update_turn_answer": "test_session_methods_use_live_rows",
    "insert_turn_entity": "test_session_methods_use_live_rows",
    "insert_turn_section": "test_session_methods_use_live_rows",
    "get_session_context": "test_session_methods_use_live_rows",
    "list_sessions": "test_session_methods_use_live_rows",
    "get_session_turns": "test_session_methods_use_live_rows",
}


@dataclass(frozen=True)
class GraphSeed:
    graph: GraphStore
    doc_v1: int
    doc_v2: int
    root: int
    risks: int
    supply: int
    semiconductors: int
    apple: int
    apple_alias: int
    iphone: int
    qualcomm: int
    china: int
    foxconn: int
    tim_cook: int


def _strict_integration() -> bool:
    return os.getenv("ORACLE_GRAPH_INTEGRATION", "").lower() in STRICT_VALUES


def _oracle_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_$#]*", value):
        raise ValueError(f"Unsupported Oracle test identifier: {value!r}")
    return value


def _oracle_test_password(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_$#]+", value):
        raise ValueError("Oracle integration test password contains unsupported characters")
    return f'"{value}"'


def _sys_provisioning_enabled(dsn: str) -> bool:
    if os.getenv("ORACLE_GRAPH_PROVISION_SYS", "").lower() not in PROVISION_SYS_VALUES:
        return False
    if not LOCAL_DSN_RE.search(dsn):
        raise RuntimeError("Refusing SYSDBA provisioning outside a local Oracle test DB")
    return True


def _connect_oracle(user: str, password: str, dsn: str, *, sysdba: bool = False):
    kwargs = {"user": user, "password": password, "dsn": dsn}
    if sysdba:
        kwargs["mode"] = oracledb.AUTH_MODE_SYSDBA
    return oracledb.connect(**kwargs)


def _ensure_test_tablespace(cur, tablespace: str) -> str:
    tablespace_ident = _oracle_identifier(tablespace).upper()
    cur.execute(
        "SELECT COUNT(*) FROM dba_tablespaces WHERE tablespace_name = :tablespace",
        {"tablespace": tablespace_ident},
    )
    if cur.fetchone()[0] > 0:
        return tablespace_ident

    cur.execute(
        """SELECT file_name
           FROM dba_data_files
           WHERE tablespace_name = 'SYSTEM'
           FETCH FIRST 1 ROW ONLY"""
    )
    system_file = cur.fetchone()[0]
    datafile = f"{system_file.rsplit('/', 1)[0]}/{tablespace_ident.lower()}01.dbf"
    cur.execute(
        f"CREATE TABLESPACE {tablespace_ident} "
        f"DATAFILE '{datafile}' SIZE 128M REUSE "
        "AUTOEXTEND ON NEXT 64M MAXSIZE 512M "
        "EXTENT MANAGEMENT LOCAL SEGMENT SPACE MANAGEMENT AUTO"
    )
    return tablespace_ident


def _unavailable(reason: str):
    if _strict_integration():
        pytest.fail(reason)
    pytest.skip(reason)


def _ensure_pageindex_user(user: str, password: str, dsn: str) -> None:
    user_error = None
    try:
        conn = _connect_oracle(user, password, dsn)
        conn.close()
        app_user_connects = True
    except oracledb.Error as exc:
        user_error = exc
        app_user_connects = False

    if app_user_connects and not _sys_provisioning_enabled(dsn):
        return
    if not _sys_provisioning_enabled(dsn):
        _unavailable(
            "Oracle app user is unavailable and SYS provisioning is disabled. "
            "Set ORACLE_GRAPH_PROVISION_SYS=1 against a local test DB to create it. "
            f"app error={user_error}"
        )

    sys_user = os.getenv("ORACLE_SYS_USER", "sys")
    sys_password = os.getenv("ORACLE_SYS_PASSWORD")
    if not sys_password:
        _unavailable("ORACLE_SYS_PASSWORD is required for SYS provisioning")
    try:
        conn = _connect_oracle(
            sys_user,
            sys_password,
            dsn,
            sysdba=sys_user.lower() == "sys",
        )
    except oracledb.Error as sys_error:
        if app_user_connects:
            return
        _unavailable(
            "Oracle is not reachable as the app user or SYS user. "
            f"app error={user_error}; sys error={sys_error}"
        )

    user_ident = _oracle_identifier(user)
    password_literal = _oracle_test_password(password)
    with conn:
        with conn.cursor() as cur:
            tablespace = _ensure_test_tablespace(
                cur, os.getenv("ORACLE_TEST_TABLESPACE", "PAGEINDEX_DATA")
            )
            cur.execute(
                "SELECT COUNT(*) FROM all_users WHERE username = :username",
                {"username": user.upper()},
            )
            exists = cur.fetchone()[0] > 0
            if exists:
                if not app_user_connects:
                    cur.execute(
                        f"ALTER USER {user_ident} IDENTIFIED BY {password_literal} ACCOUNT UNLOCK"
                    )
            else:
                cur.execute(
                    f"CREATE USER {user_ident} IDENTIFIED BY {password_literal} "
                    f"DEFAULT TABLESPACE {tablespace} TEMPORARY TABLESPACE TEMP "
                    f"QUOTA 512M ON {tablespace}"
                )
            try:
                cur.execute(f"ALTER USER {user_ident} DEFAULT TABLESPACE {tablespace}")
                cur.execute(f"ALTER USER {user_ident} QUOTA 512M ON {tablespace}")
            except oracledb.Error as exc:
                if not app_user_connects:
                    raise
                if _strict_integration():
                    pytest.fail(
                        f"Failed to prepare {tablespace} tablespace for {user}: {exc}"
                    )
            cur.execute(f"GRANT CONNECT, RESOURCE TO {user_ident}")
            cur.execute(f"GRANT CREATE PROPERTY GRAPH TO {user_ident}")

    if not app_user_connects:
        try:
            conn = _connect_oracle(user, password, dsn)
            conn.close()
        except oracledb.Error as exc:
            _unavailable(
                f"Oracle app user {user} still cannot connect after SYS setup: {exc}"
            )


def _read_lob(value):
    return value.read() if hasattr(value, "read") else value


def _public_graphstore_methods() -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(GraphStore, inspect.isfunction)
        if not name.startswith("_")
    }


def _assert_schema_ready(db: OracleDB) -> None:
    existing = {
        row["table_name"].lower()
        for row in db.fetchall("SELECT table_name FROM user_tables")
    }
    missing = REQUIRED_SCHEMA_TABLES - existing
    if missing:
        raise RuntimeError(f"Oracle schema initialization missed tables: {sorted(missing)}")


@pytest.fixture(scope="session")
def oracle_db() -> OracleDB:
    user = os.getenv("ORACLE_USER", "pageindex")
    password = os.getenv("ORACLE_PASSWORD", "pageindex")
    dsn = os.getenv("ORACLE_DSN", "localhost:1521/FREEPDB1")

    try:
        _ensure_pageindex_user(user, password, dsn)
        db = OracleDB(user=user, password=password, dsn=dsn, pool_min=1, pool_max=2)
        db.connect()
        db.init_schema()
        _assert_schema_ready(db)
    except Exception as exc:
        _unavailable(f"Oracle integration setup failed for {dsn}: {exc}")

    yield db
    db.close()


@pytest.fixture(scope="module")
def graph_seed(oracle_db: OracleDB) -> GraphSeed:
    graph = GraphStore(oracle_db)

    doc_v1 = graph.insert_document(
        "integration-report-2025.pdf",
        "Prior version for integration tests",
        "/tmp/integration-report-2025.pdf",
        doc_group="integration-report",
        doc_version=1,
    )
    doc_v2 = graph.insert_document(
        "integration-report-2026.pdf",
        "Current version for integration tests",
        "/tmp/integration-report-2026.pdf",
        doc_group="integration-report",
        doc_version=2,
    )

    graph.insert_section(
        doc_v1,
        "old-root",
        "Prior Root",
        "Prior report summary",
        "Apple Inc. appeared in the prior report.",
        0,
        20,
        0,
    )
    root = graph.insert_section(
        doc_v2,
        "root",
        "Integration Root",
        "Current report summary",
        "Apple Inc. overview with supply chain and semiconductor risks.",
        0,
        50,
        0,
    )
    risks = graph.insert_section(
        doc_v2,
        "risk",
        "Risk Factors",
        "Risk summary",
        "Apple Inc. works with Qualcomm while China and Foxconn appear in risk disclosures.",
        51,
        120,
        1,
    )
    supply = graph.insert_section(
        doc_v2,
        "supply",
        "Supply Chain",
        "Supply summary",
        "Apple Inc. sells iPhone devices while China and Foxconn appear in supply discussions.",
        121,
        200,
        1,
    )
    semiconductors = graph.insert_section(
        doc_v2,
        "chips",
        "Semiconductors",
        "Chip summary",
        "The iPhone uses Qualcomm modem technology.",
        201,
        260,
        2,
    )

    apple = graph.upsert_entity("Apple Inc.", "ORGANIZATION", "Technology company")
    assert graph.upsert_entity("Apple Inc.", "ORGANIZATION", "Duplicate") == apple
    apple_alias = graph.upsert_entity(
        "Apple Incorporated", "ORGANIZATION", "Alias candidate"
    )
    iphone = graph.upsert_entity("iPhone", "PRODUCT", "Smartphone product")
    qualcomm = graph.upsert_entity("Qualcomm", "ORGANIZATION", "Chip supplier")
    china = graph.upsert_entity("China", "LOCATION", "Market and manufacturing region")
    foxconn = graph.upsert_entity("Foxconn", "ORGANIZATION", "Manufacturing partner")
    tim_cook = graph.upsert_entity("Tim Cook", "PERSON", "Apple CEO")

    graph.insert_hierarchy_edge(root, risks)
    graph.insert_hierarchy_edge(root, supply)
    graph.insert_hierarchy_edge(risks, semiconductors)

    for entity_id in (apple, qualcomm, china, foxconn):
        graph.insert_mention_edge(risks, entity_id, "MENTIONS")
    for entity_id in (apple, iphone, china, foxconn):
        graph.insert_mention_edge(supply, entity_id, "DISCUSSES")
    for entity_id in (iphone, qualcomm):
        graph.insert_mention_edge(semiconductors, entity_id, "DEFINES")

    graph.insert_entity_relationship(apple, iphone, "PRODUCES")
    graph.insert_entity_relationship(iphone, qualcomm, "USES")
    graph.insert_entity_alias(apple, apple_alias, 0.985, confirmed=1)
    graph.update_entity_canonical(apple_alias, apple)
    graph.update_entity_embedding(apple, EMBEDDING)
    graph.update_entity_embedding(apple_alias, EMBEDDING)
    graph.insert_enriched_relationship(tim_cook, apple, "LEADS", confidence=0.83)
    graph.insert_temporal_edge(
        doc_v1,
        doc_v2,
        apple,
        "STABLE",
        old_value="Apple",
        new_value="Apple Inc.",
        confidence=0.95,
    )

    return GraphSeed(
        graph=graph,
        doc_v1=doc_v1,
        doc_v2=doc_v2,
        root=root,
        risks=risks,
        supply=supply,
        semiconductors=semiconductors,
        apple=apple,
        apple_alias=apple_alias,
        iphone=iphone,
        qualcomm=qualcomm,
        china=china,
        foxconn=foxconn,
        tim_cook=tim_cook,
    )


def test_every_public_graphstore_method_has_integration_coverage():
    assert set(PUBLIC_METHOD_COVERAGE) == _public_graphstore_methods()


def test_seeded_write_methods_persist_to_oracle(graph_seed: GraphSeed, oracle_db: OracleDB):
    doc_count = oracle_db.fetchone(
        "SELECT COUNT(*) AS c FROM documents WHERE doc_group = :grp",
        {"grp": "integration-report"},
    )
    section_count = oracle_db.fetchone(
        "SELECT COUNT(*) AS c FROM sections WHERE doc_id = :doc_id",
        {"doc_id": graph_seed.doc_v2},
    )
    hierarchy_count = oracle_db.fetchone(
        "SELECT COUNT(*) AS c FROM section_hierarchy WHERE parent_id = :root",
        {"root": graph_seed.root},
    )
    mention_count = oracle_db.fetchone(
        "SELECT COUNT(*) AS c FROM section_entities WHERE section_id = :section_id",
        {"section_id": graph_seed.risks},
    )
    relationship = oracle_db.fetchone(
        """SELECT relationship FROM entity_relationships
           WHERE source_entity = :src AND target_entity = :tgt""",
        {"src": graph_seed.apple, "tgt": graph_seed.iphone},
    )
    alias = oracle_db.fetchone(
        """SELECT similarity, confirmed FROM entity_aliases
           WHERE canonical_id = :canonical AND alias_id = :alias""",
        {"canonical": graph_seed.apple, "alias": graph_seed.apple_alias},
    )
    canonical = oracle_db.fetchone(
        "SELECT canonical_id FROM entities WHERE entity_id = :entity_id",
        {"entity_id": graph_seed.apple_alias},
    )
    embedding_count = oracle_db.fetchone(
        """SELECT COUNT(*) AS c FROM entities
           WHERE entity_id = :entity_id AND name_embedding IS NOT NULL""",
        {"entity_id": graph_seed.apple},
    )
    enriched = oracle_db.fetchone(
        """SELECT edge_source, confidence FROM entity_relationships
           WHERE source_entity = :src AND target_entity = :tgt AND relationship = 'LEADS'""",
        {"src": graph_seed.tim_cook, "tgt": graph_seed.apple},
    )
    temporal = oracle_db.fetchone(
        """SELECT change_type FROM temporal_edges
           WHERE source_doc_id = :src AND target_doc_id = :tgt AND entity_id = :entity_id""",
        {"src": graph_seed.doc_v1, "tgt": graph_seed.doc_v2, "entity_id": graph_seed.apple},
    )

    assert doc_count["c"] == 2
    assert section_count["c"] == 4
    assert hierarchy_count["c"] == 2
    assert mention_count["c"] == 4
    assert relationship["relationship"] == "PRODUCES"
    assert alias["confirmed"] == 1
    assert float(alias["similarity"]) == pytest.approx(0.985)
    assert canonical["canonical_id"] == graph_seed.apple
    assert embedding_count["c"] == 1
    assert enriched["edge_source"] == "ENRICHMENT"
    assert float(enriched["confidence"]) == pytest.approx(0.83)
    assert temporal["change_type"] == "STABLE"


def test_document_and_section_queries_use_live_rows(graph_seed: GraphSeed):
    docs = graph_seed.graph.get_all_documents()
    sections = graph_seed.graph.get_document_sections(graph_seed.doc_v2)
    sections_by_id = graph_seed.graph.get_sections_by_ids([graph_seed.supply, graph_seed.risks])
    children = graph_seed.graph.get_section_children(graph_seed.root)
    entities = graph_seed.graph.get_section_entities(graph_seed.risks)

    assert [doc["doc_version"] for doc in docs] == [1, 2]
    assert [section["title"] for section in sections] == [
        "Integration Root",
        "Risk Factors",
        "Supply Chain",
        "Semiconductors",
    ]
    assert sections_by_id[graph_seed.supply]["doc_name"] == "integration-report-2026.pdf"
    assert sections_by_id[graph_seed.risks]["text_content"].startswith("Apple Inc. works")
    assert {child["title"] for child in children} == {"Risk Factors", "Supply Chain"}
    assert {entity["name"] for entity in entities} == {
        "Apple Inc.",
        "Qualcomm",
        "China",
        "Foxconn",
    }


def test_entity_queries_and_resolution_use_live_rows(graph_seed: GraphSeed):
    all_entities = graph_seed.graph.get_all_entities()
    entity_sections = graph_seed.graph.get_entity_sections("apple")
    related_entities = graph_seed.graph.get_related_entities("Apple")
    similar = graph_seed.graph.find_similar_entities(
        EMBEDDING,
        "ORGANIZATION",
        threshold=0.01,
        exclude_id=graph_seed.apple,
    )

    assert "Apple Inc." in {entity["name"] for entity in all_entities}
    assert {section["title"] for section in entity_sections} == {
        "Risk Factors",
        "Supply Chain",
    }
    assert {entity["name"] for entity in related_entities} == {"iPhone"}
    assert any(entity["entity_id"] == graph_seed.apple_alias for entity in similar)


def test_graph_visualization_methods_use_live_rows(graph_seed: GraphSeed):
    full_graph = graph_seed.graph.get_full_graph_data()
    versioned_graph = graph_seed.graph.get_versioned_graph_data("integration-report", 2)

    node_ids = {node["id"] for node in full_graph["nodes"]}
    edge_pairs = {(edge["source"], edge["target"], edge["type"]) for edge in full_graph["edges"]}
    apple_node = next(
        node
        for node in versioned_graph["nodes"]
        if node["type"] == "entity" and node["label"] == "Apple Inc."
    )

    assert f"doc_{graph_seed.doc_v2}" in node_ids
    assert f"sec_{graph_seed.root}" in node_ids
    assert f"ent_{graph_seed.apple}" in node_ids
    assert (f"doc_{graph_seed.doc_v2}", f"sec_{graph_seed.root}", "contains") in edge_pairs
    assert (f"sec_{graph_seed.risks}", f"ent_{graph_seed.apple}", "mentions") in edge_pairs
    assert apple_node["temporal_status"] == "STABLE"


def test_sql_pgq_graph_queries_run_on_oracle_property_graph(graph_seed: GraphSeed):
    sections = graph_seed.graph.graph_query_entity_sections("Apple Inc.")
    related = graph_seed.graph.graph_query_related_entities("Apple Inc.")
    descendants = graph_seed.graph.graph_query_section_children("Integration Root")

    assert {row["section_title"] for row in sections} == {"Risk Factors", "Supply Chain"}
    assert any(row["related_name"] == "iPhone" for row in related)
    assert {row["child_title"] for row in descendants} == {
        "Risk Factors",
        "Supply Chain",
        "Semiconductors",
    }


def test_multihop_traversal_methods_run_on_oracle(graph_seed: GraphSeed):
    neighborhood = graph_seed.graph.traverse_entity_neighborhood(graph_seed.apple)
    ancestors = graph_seed.graph.traverse_section_ancestors(graph_seed.semiconductors)
    descendants = graph_seed.graph.traverse_section_descendants(graph_seed.root)
    paths = graph_seed.graph.find_entity_paths("Apple", "Qualcomm")
    multi_hop = graph_seed.graph.get_multi_hop_entities(graph_seed.apple, max_hops=2)

    assert {section["title"] for section in neighborhood["sections"]} == {
        "Risk Factors",
        "Supply Chain",
    }
    assert {"iPhone", "Qualcomm", "China", "Foxconn"}.issubset(
        {entity["name"] for entity in neighborhood["entities"]}
    )
    assert [row["title"] for row in ancestors] == ["Integration Root", "Risk Factors"]
    assert {row["title"] for row in descendants} == {
        "Risk Factors",
        "Supply Chain",
        "Semiconductors",
    }
    assert any(path["mid_name"] == "iPhone" for path in paths["paths"])
    assert any(
        entity["name"] == "iPhone" and entity["hops"] == 1
        for entity in multi_hop["entities"]
    )
    assert any(
        entity["name"] == "Qualcomm" and entity["hops"] == 2
        for entity in multi_hop["entities"]
    )


def test_enrichment_support_methods_use_live_rows(graph_seed: GraphSeed):
    isolated = graph_seed.graph.get_isolated_entities(min_mentions=2)
    pairs = graph_seed.graph.get_cooccurring_pairs(min_shared=2)
    shared_text = graph_seed.graph.get_shared_section_text(graph_seed.china, graph_seed.foxconn)

    assert {"China", "Foxconn"}.issubset({entity["name"] for entity in isolated})
    pair_names = {
        frozenset((pair["entity1_name"], pair["entity2_name"]))
        for pair in pairs
    }
    assert frozenset(("China", "Foxconn")) in pair_names
    assert "China" in shared_text
    assert "Foxconn" in shared_text


def test_temporal_methods_use_live_rows(graph_seed: GraphSeed):
    previous = graph_seed.graph.get_previous_version("integration-report", 2)
    doc_entities = graph_seed.graph.get_doc_entities(graph_seed.doc_v2)
    changes = graph_seed.graph.get_temporal_changes("integration-report", 1, 2)

    assert previous["doc_id"] == graph_seed.doc_v1
    assert {entity["name"] for entity in doc_entities} == {
        "Apple Inc.",
        "China",
        "Foxconn",
        "iPhone",
        "Qualcomm",
    }
    assert len(changes) == 1
    assert changes[0]["name"] == "Apple Inc."
    assert changes[0]["change_type"] == "STABLE"
    assert _read_lob(changes[0]["new_value"]) == "Apple Inc."


def test_session_methods_use_live_rows(graph_seed: GraphSeed):
    session_id = graph_seed.graph.create_session(
        title="Integration Session",
        metadata='{"suite": "graph"}',
    )
    turn_id = graph_seed.graph.create_turn(
        session_id,
        1,
        "What does the report say about Apple?",
        intent="LOOKUP",
    )

    graph_seed.graph.update_turn_answer(turn_id, "Apple is covered in risk and supply sections.")
    graph_seed.graph.insert_turn_entity(turn_id, graph_seed.apple, role="PRIMARY")
    graph_seed.graph.insert_turn_section(turn_id, graph_seed.risks, rank_score=0.9)

    context = graph_seed.graph.get_session_context(session_id)
    sessions = graph_seed.graph.list_sessions()
    turns = graph_seed.graph.get_session_turns(session_id)

    assert context["primary_entities"][0]["name"] == "Apple Inc."
    assert context["previous_sections"] == [graph_seed.risks]
    assert any(session["session_id"] == session_id for session in sessions)
    assert len(turns) == 1
    assert turns[0]["turn_id"] == turn_id
    assert _read_lob(turns[0]["answer"]) == "Apple is covered in risk and supply sections."
