"""FastAPI server for OraclePageIndex graph data and query API.

Provides REST endpoints for the D3.js visualization frontend,
a natural-language query endpoint powered by Ollama + Oracle graph,
and conversational session management.

Lazy initialization: the server starts even if Oracle is unavailable,
returning empty data for graph endpoints. This lets frontend developers
work on the D3.js visualization without a live database.
"""

import asyncio
import logging
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from oracle_pageindex.db import OracleDB
from oracle_pageindex.graph import GraphStore
from oracle_pageindex.llm import OllamaClient
from oracle_pageindex.query import QueryEngine
from oracle_pageindex.utils import ConfigLoader

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VIZ_DIR = PROJECT_ROOT / "viz"

# ---------------------------------------------------------------------------
# Lazy-initialised singletons
# ---------------------------------------------------------------------------

db: OracleDB | None = None
graph: GraphStore | None = None
llm: OllamaClient | None = None
query_engine: QueryEngine | None = None


def _init_backend():
    """Attempt to create DB, GraphStore, OllamaClient and QueryEngine.

    Called once at startup.  If Oracle is unreachable we log a warning
    and leave the globals as ``None`` so the server can still serve the
    static frontend.
    """
    global db, graph, llm, query_engine

    try:
        cfg = ConfigLoader().load()
    except Exception:
        logger.exception("Failed to load config -- backend will be unavailable")
        return

    # Ollama client (lightweight, no network call on init)
    try:
        ollama_cfg = cfg.ollama if hasattr(cfg, "ollama") else {}
        llm = OllamaClient(
            base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
            model=ollama_cfg.get("model", "llama3.1"),
            temperature=ollama_cfg.get("temperature", 0),
            num_ctx=ollama_cfg.get("num_ctx", 16384),
        )
        logger.info("OllamaClient initialised (model=%s)", llm.model)
    except Exception:
        logger.exception("Failed to create OllamaClient")

    # Oracle DB + GraphStore (env vars take priority over config)
    try:
        import os as _os
        oracle_cfg = cfg.oracle if hasattr(cfg, "oracle") else {}
        db = OracleDB(
            user=_os.environ.get("ORACLE_USER", oracle_cfg.get("user", "pageindex")),
            password=_os.environ.get("ORACLE_PASSWORD", oracle_cfg.get("password", "pageindex")),
            dsn=_os.environ.get("ORACLE_DSN", oracle_cfg.get("dsn", "localhost:1521/FREEPDB1")),
            pool_min=oracle_cfg.get("pool_min", 1),
            pool_max=oracle_cfg.get("pool_max", 5),
        )
        db.connect()
        graph = GraphStore(db)
        logger.info("Oracle connection pool ready (dsn=%s)", db.dsn)
    except Exception:
        logger.exception(
            "Oracle DB unavailable -- graph endpoints will return empty data"
        )
        db = None
        graph = None

    # Query engine (needs both llm and graph)
    if llm and graph:
        query_engine = QueryEngine(llm, graph)
        logger.info("QueryEngine ready")
    else:
        logger.warning(
            "QueryEngine not created (llm=%s, graph=%s)",
            "ok" if llm else "missing",
            "ok" if graph else "missing",
        )


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="OraclePageIndex API",
    description="Graph data and natural-language query API for OraclePageIndex",
    version="0.1.0",
)

# CORS -- allow the D3.js frontend (or any origin during development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Lifecycle events
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def on_startup():
    _init_backend()


@app.on_event("shutdown")
async def on_shutdown():
    if db is not None:
        try:
            db.close()
            logger.info("Oracle connection pool closed")
        except Exception:
            logger.exception("Error closing Oracle connection pool")


# ---------------------------------------------------------------------------
# Static files & index page
# ---------------------------------------------------------------------------

if VIZ_DIR.is_dir():
    app.mount("/viz", StaticFiles(directory=str(VIZ_DIR)), name="viz")


@app.get("/", include_in_schema=False)
async def index():
    """Serve the D3.js visualization index page."""
    index_path = VIZ_DIR / "index.html"
    if index_path.is_file():
        return FileResponse(str(index_path))
    return {"message": "OraclePageIndex API is running. Place viz/index.html to enable the UI."}


# ---------------------------------------------------------------------------
# Graph data endpoints
# ---------------------------------------------------------------------------


@app.get("/api/graph")
async def api_graph(
    doc_group: str | None = Query(None, description="Document group for version filtering"),
    version: int | None = Query(None, description="Document version number"),
):
    """Return the full knowledge graph (nodes + edges) for D3.js.

    When ``doc_group`` and ``version`` are provided, entity nodes are
    annotated with a ``temporal_status`` field (APPEARED, DISAPPEARED,
    MODIFIED, STABLE) reflecting changes at that version.
    """
    if graph is None:
        return {"nodes": [], "edges": []}
    try:
        if doc_group and version is not None:
            return graph.get_versioned_graph_data(doc_group, version)
        return graph.get_full_graph_data()
    except Exception:
        logger.exception("Error fetching full graph data")
        return {"nodes": [], "edges": []}


@app.get("/api/documents")
async def api_documents():
    """Return all indexed documents."""
    if graph is None:
        return []
    try:
        return graph.get_all_documents()
    except Exception:
        logger.exception("Error fetching documents")
        return []


@app.get("/api/documents/{doc_id}/sections")
async def api_document_sections(doc_id: int):
    """Return all sections belonging to a document."""
    if graph is None:
        return []
    try:
        return graph.get_document_sections(doc_id)
    except Exception:
        logger.exception("Error fetching sections for doc_id=%s", doc_id)
        return []


@app.get("/api/entities")
async def api_entities():
    """Return all extracted entities."""
    if graph is None:
        return []
    try:
        return graph.get_all_entities()
    except Exception:
        logger.exception("Error fetching entities")
        return []


@app.get("/api/entities/{entity_name}/sections")
async def api_entity_sections(entity_name: str):
    """Return sections that mention the given entity."""
    if graph is None:
        return []
    try:
        return graph.get_entity_sections(entity_name)
    except Exception:
        logger.exception("Error fetching sections for entity=%s", entity_name)
        return []


@app.get("/api/entities/{entity_name}/related")
async def api_related_entities(entity_name: str):
    """Return entities related to the given entity."""
    if graph is None:
        return []
    try:
        return graph.get_related_entities(entity_name)
    except Exception:
        logger.exception("Error fetching related entities for=%s", entity_name)
        return []


# ---------------------------------------------------------------------------
# Query endpoint
# ---------------------------------------------------------------------------


@app.get("/api/query")
async def api_query(
    q: str = Query(..., min_length=1, max_length=5000, description="Natural language question"),
    session_id: int | None = Query(None, description="Conversation session ID (omit to start new session)"),
):
    """Answer a question using graph-retrieved context and Ollama reasoning.

    Pass ``session_id`` to continue an existing conversation. When omitted,
    a new session is created automatically.
    """
    if query_engine is None:
        raise HTTPException(
            status_code=503,
            detail="Query engine unavailable (Oracle or Ollama not connected)",
        )
    try:
        # QueryEngine.query() is synchronous; run in a thread to avoid
        # blocking the event loop.
        result = await asyncio.to_thread(query_engine.query, q, session_id)
        return asdict(result)
    except Exception:
        logger.exception("Query failed for q=%s", q)
        raise HTTPException(status_code=500, detail="Internal error processing query")


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------


@app.get("/api/sessions")
async def api_sessions():
    """List all conversation sessions."""
    if graph is None:
        return []
    try:
        return graph.list_sessions()
    except Exception:
        logger.exception("Error fetching sessions")
        return []


@app.get("/api/sessions/{session_id}/turns")
async def api_session_turns(session_id: int):
    """Return all turns in a conversation session."""
    if graph is None:
        return []
    try:
        return graph.get_session_turns(session_id)
    except Exception:
        logger.exception("Error fetching turns for session_id=%s", session_id)
        return []


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.server:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
