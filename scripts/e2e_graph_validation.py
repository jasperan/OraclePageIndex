#!/usr/bin/env python3
"""End-to-end validation of all GraphStore methods against live Oracle DB.

Exercises every GraphStore method grouped by category.
Outputs a structured JSON report with pass/fail, timing, and row counts.
"""

import json
import sys
import time
import traceback

sys.path.insert(0, ".")

from oracle_pageindex.db import OracleDB
from oracle_pageindex.graph import GraphStore
from oracle_pageindex.llm import OllamaClient
from oracle_pageindex.utils import ConfigLoader


def timed(fn, *args, **kwargs):
    """Call fn and return (result, elapsed_ms)."""
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, (time.perf_counter() - t0) * 1000


def count(result):
    """Get a row/item count from various result types."""
    if isinstance(result, list):
        return len(result)
    if isinstance(result, dict):
        return sum(len(v) for v in result.values() if isinstance(v, list))
    if isinstance(result, int):
        return result
    return 1 if result else 0


class E2EValidator:
    def __init__(self):
        cfg = ConfigLoader().load()
        self.db = OracleDB(
            user=cfg.oracle_user,
            password=cfg.oracle_password,
            dsn=cfg.oracle_dsn,
        )
        self.graph = GraphStore(self.db)
        self.llm = OllamaClient(
            base_url=cfg.ollama_base_url,
            model=cfg.ollama_model,
            temperature=cfg.ollama_temperature,
        )
        self.results = []
        self.passed = 0
        self.failed = 0
        # Cache for IDs discovered during testing
        self.doc_id = None
        self.section_ids = []
        self.entity_ids = []
        self.entity_names = []
        self.session_id = None
        self.turn_id = None

    def test(self, category, name, fn, *args, allow_empty=False, **kwargs):
        """Run a single test, record result."""
        try:
            result, ms = timed(fn, *args, **kwargs)
            cnt = count(result)
            ok = allow_empty or cnt > 0
            status = "PASS" if ok else "WARN_EMPTY"
            self.results.append({
                "category": category,
                "method": name,
                "status": status,
                "rows": cnt,
                "time_ms": round(ms, 1),
                "error": None,
            })
            if ok:
                self.passed += 1
            else:
                self.failed += 1
            icon = "OK" if ok else "EMPTY"
            print(f"  [{icon}] {name}: {cnt} rows ({ms:.1f}ms)")
            return result
        except Exception as e:
            self.failed += 1
            self.results.append({
                "category": category,
                "method": name,
                "status": "FAIL",
                "rows": 0,
                "time_ms": 0,
                "error": str(e),
            })
            print(f"  [FAIL] {name}: {e}")
            traceback.print_exc()
            return None

    def discover_data(self):
        """Find existing data to use as test inputs."""
        print("\n=== Discovering existing data ===")
        docs = self.db.fetchall("SELECT doc_id, doc_name FROM documents FETCH FIRST 5 ROWS ONLY")
        print(f"  Documents: {len(docs)}")
        if docs:
            self.doc_id = docs[0]["doc_id"]
            print(f"  Using doc_id={self.doc_id}: {docs[0]['doc_name']}")

        sections = self.db.fetchall(
            "SELECT section_id, title FROM sections WHERE doc_id = :d FETCH FIRST 10 ROWS ONLY",
            {"d": self.doc_id}
        ) if self.doc_id else []
        print(f"  Sections: {len(sections)}")
        self.section_ids = [s["section_id"] for s in sections]

        entities = self.db.fetchall(
            "SELECT entity_id, name, entity_type FROM entities FETCH FIRST 20 ROWS ONLY"
        )
        print(f"  Entities: {len(entities)}")
        self.entity_ids = [e["entity_id"] for e in entities]
        self.entity_names = [e["name"] for e in entities]

        # Check edge tables
        for tbl in ["section_hierarchy", "section_entities", "entity_relationships"]:
            cnt = self.db.fetchone(f"SELECT COUNT(*) AS c FROM {tbl}")
            print(f"  {tbl}: {cnt['c']} rows")

        return len(docs) > 0 and len(sections) > 0

    def run_all(self):
        """Run all validation groups."""
        print("=" * 60)
        print("OraclePageIndex E2E Graph Validation")
        print("=" * 60)

        if not self.discover_data():
            print("\nERROR: No data found. Run indexing first.")
            return

        self.test_basic_queries()
        self.test_sql_pgq_queries()
        self.test_multi_hop_traversal()
        self.test_enrichment_support()
        self.test_temporal_versioning()
        self.test_sessions()
        self.test_entity_resolution()
        self.test_visualization_data()

        print("\n" + "=" * 60)
        print(f"RESULTS: {self.passed} passed, {self.failed} failed")
        print("=" * 60)

        # Write JSON report
        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "summary": {"passed": self.passed, "failed": self.failed},
            "tests": self.results,
        }
        with open("scripts/e2e_results.json", "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nDetailed results written to scripts/e2e_results.json")

    def test_basic_queries(self):
        """3B: Basic query methods."""
        print("\n--- 3B: Basic Query Methods ---")
        self.test("basic", "get_all_documents", self.graph.get_all_documents)
        self.test("basic", "get_document_sections", self.graph.get_document_sections, self.doc_id)

        if self.section_ids:
            self.test("basic", "get_section_children", self.graph.get_section_children,
                       self.section_ids[0], allow_empty=True)
            self.test("basic", "get_section_entities", self.graph.get_section_entities,
                       self.section_ids[0], allow_empty=True)

        self.test("basic", "get_all_entities", self.graph.get_all_entities)

        if self.entity_names:
            self.test("basic", "get_entity_sections", self.graph.get_entity_sections,
                       self.entity_names[0])
            self.test("basic", "get_related_entities", self.graph.get_related_entities,
                       self.entity_names[0], allow_empty=True)

    def test_sql_pgq_queries(self):
        """3C: SQL/PGQ GRAPH_TABLE queries."""
        print("\n--- 3C: SQL/PGQ Graph Queries ---")
        if not self.entity_names:
            print("  SKIP: No entities for PGQ queries")
            return

        self.test("pgq", "graph_query_entity_sections",
                   self.graph.graph_query_entity_sections, self.entity_names[0])
        self.test("pgq", "graph_query_related_entities",
                   self.graph.graph_query_related_entities, self.entity_names[0],
                   allow_empty=True)

        if self.section_ids:
            # Get title for section children query
            sec = self.db.fetchone(
                "SELECT title FROM sections WHERE section_id = :s",
                {"s": self.section_ids[0]}
            )
            if sec and sec.get("title"):
                self.test("pgq", "graph_query_section_children",
                           self.graph.graph_query_section_children, sec["title"],
                           allow_empty=True)

    def test_multi_hop_traversal(self):
        """3D: Multi-hop traversal."""
        print("\n--- 3D: Multi-Hop Traversal ---")
        if not self.entity_ids:
            print("  SKIP: No entities for traversal")
            return

        self.test("multihop", "traverse_entity_neighborhood",
                   self.graph.traverse_entity_neighborhood, self.entity_ids[0])

        if self.section_ids:
            self.test("multihop", "traverse_section_ancestors",
                       self.graph.traverse_section_ancestors, self.section_ids[-1],
                       allow_empty=True)
            self.test("multihop", "traverse_section_descendants",
                       self.graph.traverse_section_descendants, self.section_ids[0],
                       allow_empty=True)

        if len(self.entity_names) >= 2:
            self.test("multihop", "find_entity_paths",
                       self.graph.find_entity_paths,
                       self.entity_names[0], self.entity_names[1],
                       allow_empty=True)

        self.test("multihop", "get_multi_hop_entities",
                   self.graph.get_multi_hop_entities, self.entity_ids[0],
                   allow_empty=True)

    def test_enrichment_support(self):
        """3E: Enrichment support queries."""
        print("\n--- 3E: Enrichment Support ---")
        self.test("enrichment", "get_isolated_entities",
                   self.graph.get_isolated_entities, allow_empty=True)
        self.test("enrichment", "get_cooccurring_pairs",
                   self.graph.get_cooccurring_pairs, allow_empty=True)

        if len(self.entity_ids) >= 2:
            self.test("enrichment", "get_shared_section_text",
                       self.graph.get_shared_section_text,
                       self.entity_ids[0], self.entity_ids[1],
                       allow_empty=True)

    def test_temporal_versioning(self):
        """3F: Temporal versioning."""
        print("\n--- 3F: Temporal Versioning ---")
        self.test("temporal", "get_previous_version",
                   self.graph.get_previous_version, "constitutional-ai", 2,
                   allow_empty=True)
        if self.doc_id:
            self.test("temporal", "get_doc_entities",
                       self.graph.get_doc_entities, self.doc_id,
                       allow_empty=True)
        self.test("temporal", "get_temporal_changes",
                   self.graph.get_temporal_changes, "constitutional-ai", 1, 2,
                   allow_empty=True)

    def test_sessions(self):
        """3G: Session/Conversational Memory."""
        print("\n--- 3G: Session / Conversational Memory ---")
        # Create a session
        self.session_id = self.test("session", "create_session",
                                      self.graph.create_session, "E2E Test Session")
        if not self.session_id:
            print("  SKIP: Session creation failed")
            return

        # Create a turn
        self.turn_id = self.test("session", "create_turn",
                                   self.graph.create_turn, self.session_id, 1,
                                   "What is Constitutional AI?", "LOOKUP")
        if self.turn_id:
            self.test("session", "update_turn_answer",
                       self.graph.update_turn_answer, self.turn_id,
                       "Constitutional AI is a method for training AI systems.",
                       allow_empty=True)

            if self.entity_ids:
                self.test("session", "insert_turn_entity",
                           self.graph.insert_turn_entity, self.turn_id,
                           self.entity_ids[0], "REFERENCED",
                           allow_empty=True)
            if self.section_ids:
                self.test("session", "insert_turn_section",
                           self.graph.insert_turn_section, self.turn_id,
                           self.section_ids[0], 0.95,
                           allow_empty=True)

        self.test("session", "get_session_context",
                   self.graph.get_session_context, self.session_id,
                   allow_empty=True)
        self.test("session", "list_sessions", self.graph.list_sessions)
        self.test("session", "get_session_turns",
                   self.graph.get_session_turns, self.session_id)

    def test_entity_resolution(self):
        """3H: Entity Resolution."""
        print("\n--- 3H: Entity Resolution ---")
        if not self.entity_ids or not self.entity_names:
            print("  SKIP: No entities for resolution")
            return

        # Generate an embedding for the first entity
        try:
            embedding = self.llm.embed(self.entity_names[0])
            print(f"  Got embedding for '{self.entity_names[0]}': dim={len(embedding)}")
        except Exception as e:
            print(f"  SKIP embedding: {e}")
            embedding = None

        if embedding:
            self.test("resolution", "update_entity_embedding",
                       self.graph.update_entity_embedding,
                       self.entity_ids[0], embedding,
                       allow_empty=True)

            entity_type = self.db.fetchone(
                "SELECT entity_type FROM entities WHERE entity_id = :eid",
                {"eid": self.entity_ids[0]}
            )
            etype = entity_type["entity_type"] if entity_type else None

            self.test("resolution", "find_similar_entities",
                       self.graph.find_similar_entities,
                       embedding, etype, 0.5,
                       allow_empty=True)

        if len(self.entity_ids) >= 2:
            self.test("resolution", "insert_entity_alias",
                       self.graph.insert_entity_alias,
                       self.entity_ids[0], self.entity_ids[1], 0.85,
                       allow_empty=True)
            self.test("resolution", "update_entity_canonical",
                       self.graph.update_entity_canonical,
                       self.entity_ids[1], self.entity_ids[0],
                       allow_empty=True)

    def test_visualization_data(self):
        """3I: Visualization data."""
        print("\n--- 3I: Visualization Data ---")
        self.test("viz", "get_full_graph_data", self.graph.get_full_graph_data)
        self.test("viz", "get_versioned_graph_data",
                   self.graph.get_versioned_graph_data,
                   "constitutional-ai", 1, allow_empty=True)

    def close(self):
        self.db.close()


if __name__ == "__main__":
    validator = E2EValidator()
    try:
        validator.run_all()
    finally:
        validator.close()
