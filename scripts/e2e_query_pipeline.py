#!/usr/bin/env python3
"""End-to-end test of the full query pipeline: all 6 intent types + conversational memory.

Runs after indexing is complete. Exercises QueryEngine against live Oracle + Ollama.
"""

import json
import sys
import time

sys.path.insert(0, ".")

from oracle_pageindex.db import OracleDB
from oracle_pageindex.graph import GraphStore
from oracle_pageindex.llm import OllamaClient
from oracle_pageindex.query import QueryEngine
from oracle_pageindex.utils import ConfigLoader


def run_query_pipeline():
    cfg = ConfigLoader().load()
    db = OracleDB(user=cfg.oracle_user, password=cfg.oracle_password, dsn=cfg.oracle_dsn)
    llm = OllamaClient(
        base_url=cfg.ollama_base_url,
        model=cfg.ollama_model,
        temperature=cfg.ollama_temperature,
        num_ctx=getattr(cfg, "ollama_num_ctx", 16384),
    )
    graph = GraphStore(db)
    engine = QueryEngine(llm=llm, graph=graph)

    # 6 intent-specific queries
    queries = [
        ("LOOKUP", "What is Constitutional AI?"),
        ("RELATIONSHIP", "How does RLHF relate to Constitutional AI?"),
        ("EXPLORATION", "What are the key training techniques described in this paper?"),
        ("COMPARISON", "Compare the harmlessness and helpfulness objectives."),
        ("HIERARCHICAL", "What are the main sections and subtopics of this paper?"),
        ("TEMPORAL", "How did the approach evolve from earlier methods?"),
    ]

    results = []
    session_id = None  # will be set by first query

    print("=" * 60)
    print("OraclePageIndex Query Pipeline E2E Test")
    print("=" * 60)

    for expected_intent, question in queries:
        print(f"\n--- Query ({expected_intent}) ---")
        print(f"Q: {question}")

        t0 = time.perf_counter()
        try:
            result = engine.query(question, session_id=session_id)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            # Capture session from first query
            if session_id is None and result.session_id is not None:
                session_id = result.session_id
                print(f"Session created: {session_id}")

            answer_preview = (result.answer or "")[:300]
            print(f"A: {answer_preview}...")
            print(f"Sources: {len(result.sources)}")
            print(f"Related entities: {len(result.related_entities)}")
            print(f"Graph queries: {len(result.graph_queries)}")
            print(f"Traversal steps: {len(result.traversal_path)}")
            print(f"Time: {elapsed_ms:.0f}ms")

            entry = {
                "expected_intent": expected_intent,
                "question": question,
                "answer_preview": answer_preview,
                "sources_count": len(result.sources),
                "related_entities_count": len(result.related_entities),
                "graph_queries_count": len(result.graph_queries),
                "traversal_steps_count": len(result.traversal_path),
                "session_id": result.session_id,
                "elapsed_ms": round(elapsed_ms, 1),
                "status": "PASS" if result.answer and len(result.answer) > 20 else "WEAK",
                "graph_queries_detail": [
                    {"purpose": gq.purpose, "rows": gq.rows_returned, "ms": round(gq.execution_ms, 1)}
                    for gq in result.graph_queries
                ],
            }
            results.append(entry)

        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            print(f"ERROR: {e}")
            results.append({
                "expected_intent": expected_intent,
                "question": question,
                "status": "FAIL",
                "error": str(e),
                "elapsed_ms": round(elapsed_ms, 1),
            })

    # Test conversational memory: follow-up query using session
    print("\n--- Conversational Memory Test ---")
    if session_id:
        followup = "What specific methods were mentioned earlier about training?"
        print(f"Q (follow-up, session={session_id}): {followup}")
        t0 = time.perf_counter()
        try:
            result = engine.query(followup, session_id=session_id)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            print(f"A: {(result.answer or '')[:300]}...")
            print(f"Session context used: session_id={result.session_id}")
            results.append({
                "expected_intent": "FOLLOW_UP",
                "question": followup,
                "answer_preview": (result.answer or "")[:300],
                "session_id": result.session_id,
                "elapsed_ms": round(elapsed_ms, 1),
                "status": "PASS" if result.answer and len(result.answer) > 20 else "WEAK",
            })
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({
                "expected_intent": "FOLLOW_UP",
                "question": followup,
                "status": "FAIL",
                "error": str(e),
            })

    # Summary
    passed = sum(1 for r in results if r.get("status") == "PASS")
    failed = sum(1 for r in results if r.get("status") == "FAIL")
    weak = sum(1 for r in results if r.get("status") == "WEAK")

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} PASS, {weak} WEAK, {failed} FAIL")
    print("=" * 60)

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "session_id": session_id,
        "summary": {"passed": passed, "weak": weak, "failed": failed},
        "queries": results,
    }
    with open("scripts/e2e_query_results.json", "w") as f:
        json.dump(report, f, indent=2)
    print("Results written to scripts/e2e_query_results.json")

    db.close()


if __name__ == "__main__":
    run_query_pipeline()
