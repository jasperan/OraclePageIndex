<div align="center">

# OraclePageIndex

### Document Intelligence with Oracle AI Database Property Graphs

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Oracle 26ai](https://img.shields.io/badge/Oracle-26ai_Free-red.svg)](https://www.oracle.com/database/free/)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-green.svg)](https://ollama.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Transform documents into navigable knowledge graphs stored in Oracle Database using SQL Property Graphs.**
**Graph-based reasoning, not vectors.**

</div>

---

OraclePageIndex is an Oracle AI Database-powered fork of [PageIndex](https://github.com/VectifyAI/PageIndex) by VectifyAI. Instead of relying on vector similarity search, it builds a **property graph** of documents, sections, entities, and their relationships directly inside Oracle Database 26ai Free. Queries traverse the graph using **SQL/PGQ** (SQL Property Graph Queries) and are augmented by an LLM (Ollama) for natural-language answers. The result is explainable, traceable, and structurally aware document intelligence -- no embeddings required.

---

## Why Oracle Property Graphs?

| | Traditional RAG | OraclePageIndex |
|---|---|---|
| **Storage** | Vector embeddings in a vector DB | Property graph in Oracle Database |
| **Retrieval** | Cosine similarity on chunks | Graph traversal via SQL/PGQ |
| **Reasoning** | Semantic similarity (approximate) | Structural + relational reasoning (exact) |
| **Explainability** | Opaque distance scores | Named edges, traversable paths |
| **Relationships** | Lost during chunking | First-class citizens (edges) |
| **Query Language** | Proprietary APIs | Standard SQL with GRAPH_TABLE |
| **Schema** | Flat key-value | Rich vertex/edge types with properties |
| **Multi-hop** | Requires re-ranking hacks | Native graph path expressions |

---

## Architecture

```
                         OraclePageIndex Architecture

  +----------+       +---------+       +---------------------------+
  |          |       |         |       |   Oracle Database 26ai    |
  |   PDF    +------>+ Ollama  +------>+                           |
  | Document |       |  LLM    |       |  +---------------------+ |
  +----------+       +---------+       |  | Property Graph      | |
                      |  parse    |       |  |                     | |
                      |  extract  |       |  | [documents]---+     | |
                      |  reason   |       |  | [sections]----+     | |
                      +--------+  |       |  | [entities]----+     | |
                               |  |       |  | [relationships]     | |
                               v  v       |  +---------------------+ |
                         +---------+      +------------+--------------+
                         |         |                   |
                         | FastAPI |<------------------+
                         | Server  |     SQL/PGQ queries
                         +----+----+
                              |
                              v
                      +-------+--------+
                      |    D3.js       |
                      | Visualization  |
                      | (Force Graph)  |
                      +----------------+
```

```
PDF --> Parser --> Ollama LLM --> Entities & Sections
                                        |
                                        v
                              Oracle Property Graph
                              (SQL/PGQ GRAPH_TABLE)
                                        |
                            +-----------+-----------+
                            |                       |
                            v                       v
                     Query Engine              D3.js Graph
                   (Ollama + SQL/PGQ)        Visualization
```

---

## Quick Start

### Prerequisites

- **Docker** (for Oracle Database)
- **Python 3.11+**
- **Ollama** with a model pulled (e.g. `ollama pull llama3.1`)

### 1. Start Oracle Database

```bash
docker compose up -d
# Wait ~2 minutes for the database to initialize
docker compose logs -f oracle-db  # watch until "DATABASE IS READY TO USE"
```

### 2. Create the Database User

Connect as SYSDBA and create the `pageindex` user:

```sql
sqlplus sys/OraclePageIndex123@localhost:1521/FREEPDB1 as sysdba

CREATE USER pageindex IDENTIFIED BY pageindex
    DEFAULT TABLESPACE users
    TEMPORARY TABLESPACE temp
    QUOTA UNLIMITED ON users;

GRANT CONNECT, RESOURCE TO pageindex;
GRANT CREATE SESSION TO pageindex;
GRANT CREATE TABLE TO pageindex;
GRANT CREATE PROPERTY GRAPH TO pageindex;

EXIT;
```

### 3. Install & Initialize

```bash
# Clone and install
git clone https://github.com/jasperan/OraclePageIndex.git
cd OraclePageIndex
cp .env.example .env  # edit if needed
pip install -e .

# Initialize the schema (creates tables + property graph)
oracle-pageindex init
```

### 4. Index a Document

```bash
oracle-pageindex index /path/to/document.pdf
```

The indexer will:
1. Parse the PDF into a hierarchical section tree
2. Extract named entities from each section via Ollama
3. Store everything as vertices and edges in the Oracle Property Graph

### 5. Query the Knowledge Graph

```bash
oracle-pageindex query "What are the key financial risks mentioned in section 3?"
```

The query engine traverses the graph using SQL/PGQ, gathers relevant sections and entities, and feeds them to Ollama for a grounded, citation-backed answer.

### 6. Visualize

```bash
oracle-pageindex serve
# Open http://localhost:8000 in your browser
```

An interactive D3.js force-directed graph renders your document's knowledge graph -- sections, entities, and relationships -- all queryable and explorable.

---

## SQL/PGQ Examples

OraclePageIndex stores documents as a native SQL Property Graph. You can query it directly with standard SQL using `GRAPH_TABLE`:

**Find all entities mentioned in a specific section:**

```sql
SELECT entity_name, entity_type, section_title
FROM GRAPH_TABLE (doc_knowledge_graph
    MATCH (s IS section) -[m IS mentions]-> (e IS entity)
    WHERE s.title = 'Financial Stability'
    COLUMNS (
        e.name AS entity_name,
        e.entity_type AS entity_type,
        s.title AS section_title
    )
);
```

**Discover multi-hop entity relationships:**

```sql
SELECT src_name, relationship, tgt_name
FROM GRAPH_TABLE (doc_knowledge_graph
    MATCH (e1 IS entity) -[r IS related_to]-> (e2 IS entity)
    COLUMNS (
        e1.name AS src_name,
        r.relationship AS relationship,
        e2.name AS tgt_name
    )
);
```

**Traverse section hierarchy (parent to children):**

```sql
SELECT parent_title, child_title, child_summary
FROM GRAPH_TABLE (doc_knowledge_graph
    MATCH (p IS section) -[h IS parent_of]-> (c IS section)
    COLUMNS (
        p.title AS parent_title,
        c.title AS child_title,
        c.summary AS child_summary
    )
)
ORDER BY parent_title;
```

**Find all sections in a document with their entity counts:**

```sql
SELECT doc_name, section_title, entity_count
FROM GRAPH_TABLE (doc_knowledge_graph
    MATCH (d IS document) <-[]- (s IS section) -[m IS mentions]-> (e IS entity)
    COLUMNS (
        d.doc_name AS doc_name,
        s.title AS section_title,
        COUNT(e.entity_id) AS entity_count
    )
)
ORDER BY entity_count DESC;
```

---

## Tech Stack

| Component | Technology |
|---|---|
| **Database** | Oracle Database 26ai Free (SQL Property Graphs) |
| **Query Language** | SQL/PGQ (ISO SQL:2023 Property Graph Queries) |
| **LLM** | Ollama (llama3.1, or any supported model) |
| **Backend** | Python 3.11+, FastAPI, oracledb |
| **Frontend** | D3.js (force-directed graph visualization) |
| **PDF Parsing** | PyMuPDF, PyPDF2 |
| **Tokenization** | tiktoken |
| **Container** | Docker Compose |

---

## Project Structure

```
OraclePageIndex/
  oracle_pageindex/
    cli.py              # CLI entry point (init, index, query, serve)
    config.yaml         # Default configuration
    db.py               # Oracle Database connection & pooling
    entity_extractor.py # LLM-powered named entity extraction
    graph.py            # Property Graph CRUD (SQL/PGQ)
    indexer.py          # Document indexing pipeline
    llm.py              # Ollama LLM client
    parser.py           # PDF parsing & section tree builder
    query.py            # Graph-aware query engine
    utils.py            # Config loader, token counting, helpers
  api/
    server.py           # FastAPI server with D3.js visualization
  setup_schema.sql      # Oracle schema DDL + Property Graph definition
  docker-compose.yml    # Oracle Database 26ai Free container
  .env.example          # Environment variable template
  pyproject.toml        # Python package configuration
  run.py                # Convenience entry point
```

---

## License

[MIT](LICENSE)

---

## Credits

- **[PageIndex](https://github.com/VectifyAI/PageIndex)** by [VectifyAI](https://vectify.ai) -- the original vectorless, reasoning-based RAG framework that inspired this project.
- **[Oracle Database](https://www.oracle.com/database/free/)** -- SQL Property Graphs (SQL/PGQ) provide the graph storage and query foundation.
- **[Ollama](https://ollama.com/)** -- local LLM inference for entity extraction, summarization, and query answering.
- **[D3.js](https://d3js.org/)** -- interactive force-directed graph visualization in the browser.
