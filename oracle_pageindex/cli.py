"""CLI entry point for OraclePageIndex.

Subcommands
-----------
init            Initialize the Oracle database schema.
index <file>    Index a PDF document into the knowledge graph.
query <question> Query the knowledge graph with a natural-language question.
serve           Start the FastAPI visualization server.

All subcommands accept optional ``--model`` and ``--oracle-dsn`` overrides.
"""

import argparse
import logging
import sys

from oracle_pageindex.db import OracleDB
from oracle_pageindex.graph import GraphStore
from oracle_pageindex.llm import OllamaClient
from oracle_pageindex.utils import ConfigLoader

logger = logging.getLogger("oracle_pageindex")


# ---------------------------------------------------------------------------
# Configuration helper
# ---------------------------------------------------------------------------

def get_config(args):
    """Load config.yaml and apply any CLI overrides from *args*."""
    overrides = {}
    if getattr(args, "model", None):
        overrides["ollama"] = {"model": args.model}
    if getattr(args, "oracle_dsn", None):
        overrides["oracle"] = {"dsn": args.oracle_dsn}
    loader = ConfigLoader()
    return loader.load(overrides if overrides else None)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_init(args):
    """Initialize the Oracle database schema."""
    cfg = get_config(args)
    db = OracleDB(
        user=cfg.oracle_user,
        password=cfg.oracle_password,
        dsn=cfg.oracle_dsn,
    )
    try:
        db.init_schema()
        print("Schema initialized successfully.")
    finally:
        db.close()


def cmd_index(args):
    """Index a PDF document into the knowledge graph."""
    from oracle_pageindex.indexer import Indexer

    cfg = get_config(args)
    llm = OllamaClient(
        base_url=cfg.ollama_base_url,
        model=cfg.ollama_model,
        temperature=cfg.ollama_temperature,
        num_ctx=getattr(cfg, 'ollama_num_ctx', 16384),
    )
    db = OracleDB(
        user=cfg.oracle_user,
        password=cfg.oracle_password,
        dsn=cfg.oracle_dsn,
    )
    try:
        indexer = Indexer(llm=llm, db=db, opt=cfg)
        stats = indexer.index_pdf(
            args.file,
            doc_group=getattr(args, "doc_group", None),
            doc_version=getattr(args, "doc_version", 1),
        )
        print("Indexing complete.")
        print(f"  Document:      {stats.get('doc_name', 'N/A')}")
        print(f"  Sections:      {stats.get('sections', 0)}")
        print(f"  Entities:      {stats.get('entities', 0)}")
        print(f"  Relationships: {stats.get('relationships', 0)}")
    finally:
        db.close()


def cmd_query(args):
    """Query the knowledge graph and print the answer."""
    from oracle_pageindex.query import QueryEngine

    cfg = get_config(args)
    llm = OllamaClient(
        base_url=cfg.ollama_base_url,
        model=cfg.ollama_model,
        temperature=cfg.ollama_temperature,
        num_ctx=getattr(cfg, 'ollama_num_ctx', 16384),
    )
    db = OracleDB(
        user=cfg.oracle_user,
        password=cfg.oracle_password,
        dsn=cfg.oracle_dsn,
    )
    try:
        graph = GraphStore(db)
        engine = QueryEngine(llm=llm, graph=graph)
        result = engine.query(args.question)

        print("\nAnswer:")
        print(result.get("answer", "No answer returned."))

        sources = result.get("sources", [])
        if sources:
            print("\nSources:")
            for src in sources:
                title = src.get("title", "Untitled")
                doc = src.get("doc_name", "")
                print(f"  - {title}" + (f" ({doc})" if doc else ""))

        related = result.get("related_entities", [])
        if related:
            print("\nRelated entities:")
            for ent in related:
                name = ent.get("name", "")
                etype = ent.get("entity_type", "")
                print(f"  - {name}" + (f" [{etype}]" if etype else ""))
    finally:
        db.close()


def cmd_enrich(args):
    """Run the graph enrichment agent to discover missing relationships."""
    from oracle_pageindex.enricher import GraphEnricher

    cfg = get_config(args)
    llm = OllamaClient(
        base_url=cfg.ollama_base_url,
        model=cfg.ollama_model,
        temperature=cfg.ollama_temperature,
        num_ctx=getattr(cfg, 'ollama_num_ctx', 16384),
    )
    db = OracleDB(
        user=cfg.oracle_user,
        password=cfg.oracle_password,
        dsn=cfg.oracle_dsn,
    )
    try:
        graph = GraphStore(db)
        enricher = GraphEnricher(llm=llm, graph_store=graph)
        stats = enricher.enrich(
            max_candidates=args.max_candidates,
            dry_run=args.dry_run,
            doc_id=getattr(args, "doc_id", None),
        )
        print("Enrichment complete.")
        print(f"  Candidates analyzed: {stats['candidates_analyzed']}")
        print(f"  New relationships:   {stats['new_relationships']}")
        print(f"  LLM calls:           {stats['llm_calls']}")
        if stats["relationship_types"]:
            print("  Relationship types:")
            for rtype, count in stats["relationship_types"].items():
                print(f"    {rtype}: {count}")
        if args.dry_run:
            print("  (dry run -- no edges inserted)")
    finally:
        db.close()


def cmd_serve(args):
    """Start the FastAPI visualization server."""
    import uvicorn

    host = getattr(args, "host", "0.0.0.0")
    port = getattr(args, "port", 8000)
    print(f"Starting server on {host}:{port} ...")
    uvicorn.run("api.server:app", host=host, port=port, reload=True)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="oracle-pageindex",
        description="OraclePageIndex -- Oracle AI Database powered document intelligence.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )

    # Shared optional overrides
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override the Ollama model name (e.g. llama3.1).",
    )
    parser.add_argument(
        "--oracle-dsn",
        type=str,
        default=None,
        help="Override the Oracle DSN (e.g. localhost:1521/FREEPDB1).",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # --- init ---
    sub.add_parser("init", help="Initialize the Oracle database schema.")

    # --- index ---
    p_index = sub.add_parser("index", help="Index a PDF document.")
    p_index.add_argument("file", type=str, help="Path to the PDF file to index.")
    p_index.add_argument(
        "--doc-group", type=str, default=None,
        help="Document group for temporal versioning (e.g. 'apple-10k').",
    )
    p_index.add_argument(
        "--doc-version", type=int, default=1,
        help="Version number within the document group (default: 1).",
    )

    # --- query ---
    p_query = sub.add_parser("query", help="Query the knowledge graph.")
    p_query.add_argument("question", type=str, help="Natural-language question.")

    # --- enrich ---
    p_enrich = sub.add_parser("enrich", help="Run the graph enrichment agent.")
    p_enrich.add_argument(
        "--dry-run", action="store_true",
        help="Detect gaps but don't insert new edges.",
    )
    p_enrich.add_argument(
        "--max-candidates", type=int, default=50,
        help="Maximum co-occurring pairs to examine (default: 50).",
    )
    p_enrich.add_argument(
        "--doc-id", type=int, default=None,
        help="Only examine pairs from this document.",
    )

    # --- serve ---
    p_serve = sub.add_parser("serve", help="Start the FastAPI visualization server.")
    p_serve.add_argument("--host", type=str, default="0.0.0.0", help="Bind host.")
    p_serve.add_argument("--port", type=int, default=8000, help="Bind port.")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

COMMANDS = {
    "init": cmd_init,
    "index": cmd_index,
    "query": cmd_query,
    "enrich": cmd_enrich,
    "serve": cmd_serve,
}


def main():
    parser = build_parser()
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    try:
        handler(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except Exception as exc:
        logger.error(f"Command '{args.command}' failed: {exc}", exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()
