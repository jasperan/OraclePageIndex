<div align="center">

# OraclePageIndex

### Document Intelligence Powered by Oracle AI Database Property Graphs

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Oracle 26ai](https://img.shields.io/badge/Oracle-26ai_Free-red.svg)](https://www.oracle.com/database/free/)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-green.svg)](https://ollama.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Transform PDFs into navigable knowledge graphs using Oracle SQL Property Graphs.**
**Graph-based reasoning. No vectors. No embeddings.**

[Quick Start](#quick-start) | [How It Works](#how-it-works) | [Live Demo](#live-demo-apple-10-k-2024) | [SQL/PGQ Examples](#sqlpgq--the-power-of-oracle-property-graphs)

</div>

---

## What Is This?

OraclePageIndex turns documents into **knowledge graphs** stored natively in Oracle Database using **SQL Property Graphs** (SQL/PGQ). Unlike traditional RAG systems that chunk text and match vectors, OraclePageIndex builds a structured graph of documents, sections, entities, and relationships -- then traverses it with standard SQL to find answers.

It's an Oracle AI Database-powered fork of [PageIndex](https://github.com/VectifyAI/PageIndex) by VectifyAI, demonstrating that **Oracle Database's graph capabilities** are a powerful alternative to vector search for document intelligence.

### Why Graphs Instead of Vectors?

| | Vector RAG | OraclePageIndex (Graph RAG) |
|---|---|---|
| **How it works** | Chunk text → embed → cosine similarity | Parse structure → extract entities → graph traversal |
| **Storage** | Vector embeddings in a vector DB | Property graph in Oracle Database |
| **Retrieval** | Approximate nearest-neighbor search | Exact graph traversal via SQL/PGQ |
| **Relationships** | Lost during chunking | First-class citizens (named edges) |
| **Explainability** | Opaque similarity scores | Traceable graph paths with named relationships |
| **Multi-document** | Separate vector spaces per doc | Unified knowledge graph with cross-document links |
| **Query Language** | Proprietary APIs | Standard SQL with `GRAPH_TABLE` |
| **Multi-hop reasoning** | Requires re-ranking hacks | Native recursive path expressions (`->+`) |

---

## Live Demo: Apple 10-K 2024

We indexed Apple's 121-page annual report (SEC 10-K filing, fiscal year 2024) end-to-end. Here's what Oracle's property graph captured:

### Graph Statistics

| Metric | Count |
|--------|-------|
| **Document** | 1 (Apple 10-K 2024) |
| **Sections** | 121 page-level sections with summaries |
| **Entities** | 686 unique entities extracted via LLM |
| **Mention Edges** | 951 section-entity connections |
| **Entity Relationships** | 33 cross-entity links |
| **D3.js Graph** | 808 nodes, 1,105 edges |

### Entity Types Extracted

The LLM extracted structured entities across categories:

- **Organizations**: Apple Inc., SEC, Standard & Poor's, Bank of New York Mellon
- **Products**: iPhone 16 Pro, iPhone 16, iPhone SE, Apple Watch Series 10, Mac
- **Technologies**: iOS, macOS, Apple Intelligence, XBRL
- **People**: Timothy D. Cook, Luca Maestri, Arthur D. Levinson, board members
- **Locations**: China mainland, India, Japan, South Korea, Taiwan, Vietnam
- **Concepts**: Risk Factors, Cybersecurity, Human Capital, Net Sales, Tariffs
- **Financial**: Common Stock, Equity Awards, RSUs, Commercial Paper, Term Debt

### Sample SQL/PGQ Query: Apple's Relationships

```sql
SELECT e2.name, e2.entity_type, r.relationship
FROM GRAPH_TABLE (doc_knowledge_graph
    MATCH (e1 IS entity WHERE e1.name = 'Apple Inc.')
          -[r IS related_to]-> (e2 IS entity)
    COLUMNS (e2.name, e2.entity_type, r.relationship)
);
```

**Result:**

| Entity | Type | Relationship |
|--------|------|-------------|
| Form 10-K | CONCEPT | USED_BY |
| SEC | ORGANIZATION | RELATED_TO |
| Securities Exchange Act of 1934 | LAW | RELATED_TO |
| Net Sales | METRIC | RELATED_TO |
| Product Introductions | CONCEPT | RELATED_TO |
| Human Capital | CONCEPT | RELATED_TO |
| China mainland | LOCATION | OPERATES_IN |
| India | LOCATION | OPERATES_IN |
| Japan | LOCATION | OPERATES_IN |
| South Korea | LOCATION | OPERATES_IN |
| Taiwan | LOCATION | OPERATES_IN |
| Vietnam | LOCATION | OPERATES_IN |

### Sample Query & Answer

```bash
$ python run.py query "What are the main risk factors for Apple?"
```

> **Answer:** Based on the knowledge graph, Apple's main risk factors include:
> - **Supply Chain Risks**: Heavy reliance on manufacturing in China, South Korea, Taiwan, India, and Vietnam
> - **Financial Risks**: Commercial paper interest rate exposure, term debt obligations, currency exchange fluctuations
> - **Product Risks**: Dependence on successful product introductions; component shortages
> - **Legal & Regulatory**: Subject to Securities Exchange Act; SEC reporting requirements
>
> **Sources:** Pages 3, 9, 11, 27, 45, 76, 81, 98, 99, 108, 110, 121
>
> **Related Entities:** Apple Inc., China mainland, India, Japan, South Korea, Taiwan, Vietnam, Net Sales, Product Introductions, Tariffs, SEC

---

## How It Works

### Indexing Pipeline

```
  PDF Document
       |
       v
  [1. Parse]  Extract text per page, detect structure
       |
       v
  [2. Structure]  Ollama builds hierarchical section tree
       |
       v
  [3. Summarize]  Generate concise summary per section
       |
       v
  [4. Extract Entities]  Ollama identifies PERSON, ORG, TECH, CONCEPT...
       |
       v
  [5. Store in Oracle]  INSERT vertices + edges into Property Graph
       |
       v
  [6. Link Entities]  Ollama discovers cross-entity relationships

  Result: A rich Oracle Property Graph with SQL/PGQ access
```

### Query Pipeline

```
  User Question: "What products does Apple sell?"
       |
       v
  [1. Concept Extraction]  Ollama extracts: ["Apple", "products"]
       |
       v
  [2. Graph Traversal]  SQL/PGQ finds matching entities + sections
       |
       v
  [3. Context Assembly]  Retrieve text from graph-matched sections
       |
       v
  [4. LLM Reasoning]  Ollama reasons over graph-retrieved context
       |
       v
  Answer with sources and related entities from the graph
```

### Architecture

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

---

## Quick Start

### Prerequisites

- **Docker** (for Oracle Database 26ai Free)
- **Python 3.11+**
- **Ollama** with a model pulled (e.g., `ollama pull gemma3` or `ollama pull llama3.1`)

### 1. Start Oracle Database

```bash
docker compose up -d
# Wait ~2 minutes for initialization
docker compose logs -f oracle-db  # watch until "DATABASE IS READY TO USE"
```

### 2. Create the Database User

```bash
# Connect as SYSDBA (replace password with yours from docker-compose.yml)
docker exec -i <container-name> sqlplus -s "/ as sysdba" <<'EOF'
ALTER SESSION SET CONTAINER = FREEPDB1;
ALTER PROFILE DEFAULT LIMIT PASSWORD_VERIFY_FUNCTION NULL;
CREATE USER pageindex IDENTIFIED BY pageindex;
GRANT CONNECT, RESOURCE TO pageindex;
GRANT UNLIMITED TABLESPACE TO pageindex;
GRANT CREATE PROPERTY GRAPH TO pageindex;
EXIT;
EOF
```

The key grant is `CREATE PROPERTY GRAPH` -- this enables Oracle's SQL/PGQ capabilities.

### 3. Install & Initialize

```bash
pip install oracledb httpx pyyaml tiktoken PyPDF2 PyMuPDF fastapi uvicorn

# Initialize the schema (creates 6 tables + Property Graph)
python run.py init
```

This creates the Oracle Property Graph `doc_knowledge_graph` with:
- **3 vertex tables**: `documents`, `sections`, `entities`
- **3 edge tables**: `section_hierarchy`, `section_entities`, `entity_relationships`

### 4. Index a Document

```bash
python run.py index /path/to/document.pdf
```

Example output:
```
Indexing complete.
  Document:      apple-10k-2024.pdf
  Sections:      121
  Entities:      686
  Relationships: 33
```

### 5. Query the Knowledge Graph

```bash
python run.py query "What are the key financial risks?"
```

The query engine:
1. Extracts concepts from your question via Ollama
2. Traverses the Oracle Property Graph to find matching sections
3. Enriches context with related entities
4. Reasons over the graph-retrieved context for a grounded answer

### 6. Visualize

```bash
python run.py serve
# Open http://localhost:8000
```

Interactive D3.js force-directed graph with:
- **Color-coded nodes**: Documents (blue), Sections (green), Entities (orange)
- **Edge types**: Hierarchy (solid), Mentions (dashed), Relationships (dotted)
- **Click** any node for details, **search** for entities, **toggle** layouts

---

## SQL/PGQ -- The Power of Oracle Property Graphs

The entire knowledge graph is queryable with standard SQL using `GRAPH_TABLE`. This is what makes Oracle special -- no proprietary graph query language, just SQL.

### Find Sections Mentioning an Entity

```sql
SELECT s.title, e.name AS entity, d.doc_name
FROM GRAPH_TABLE (doc_knowledge_graph
    MATCH (e IS entity WHERE e.name = 'iPhone')
          <-[m IS mentions]- (s IS section)
    COLUMNS (s.title, e.name, s.doc_id)
) gt
JOIN documents d ON d.doc_id = gt.doc_id;
```

### Discover Entity Relationships

```sql
SELECT e1.name AS source, r.relationship, e2.name AS target, e2.entity_type
FROM GRAPH_TABLE (doc_knowledge_graph
    MATCH (e1 IS entity WHERE e1.name = 'Apple Inc.')
          -[r IS related_to]-> (e2 IS entity)
    COLUMNS (e1.name, r.relationship, e2.name, e2.entity_type)
);
```

### Recursive Section Hierarchy Traversal

```sql
-- Find ALL descendants of a section (multi-hop!)
SELECT child.title, child.summary
FROM GRAPH_TABLE (doc_knowledge_graph
    MATCH (parent IS section WHERE parent.title = 'Introduction')
          -[h IS parent_of]->+ (child IS section)
    COLUMNS (child.title, child.summary)
);
```

The `->+` syntax is SQL/PGQ's recursive path expression -- it traverses the hierarchy to any depth in a single query. No recursive CTEs needed.

### Cross-Document Entity Discovery

```sql
-- Find all documents and sections that discuss a concept
SELECT d.doc_name, s.title, m.relevance, e.entity_type
FROM GRAPH_TABLE (doc_knowledge_graph
    MATCH (e IS entity WHERE e.name = 'Cybersecurity')
          <-[m IS mentions]- (s IS section)
    COLUMNS (e.entity_type, m.relevance, s.title, s.doc_id)
) gt
JOIN documents d ON d.doc_id = gt.doc_id
ORDER BY gt.relevance;
```

---

## Oracle Property Graph Schema

```sql
CREATE PROPERTY GRAPH doc_knowledge_graph
    VERTEX TABLES (
        documents   KEY (doc_id)     LABEL document  PROPERTIES ALL COLUMNS,
        sections    KEY (section_id) LABEL section   PROPERTIES ALL COLUMNS,
        entities    KEY (entity_id)  LABEL entity    PROPERTIES ALL COLUMNS
    )
    EDGE TABLES (
        section_hierarchy   -- parent_of: section -> section
            KEY (edge_id)
            SOURCE KEY (parent_id) REFERENCES sections (section_id)
            DESTINATION KEY (child_id) REFERENCES sections (section_id)
            LABEL parent_of PROPERTIES ALL COLUMNS,
        section_entities    -- mentions: section -> entity
            KEY (edge_id)
            SOURCE KEY (section_id) REFERENCES sections (section_id)
            DESTINATION KEY (entity_id) REFERENCES entities (entity_id)
            LABEL mentions PROPERTIES ALL COLUMNS,
        entity_relationships -- related_to: entity -> entity
            KEY (edge_id)
            SOURCE KEY (source_entity) REFERENCES entities (entity_id)
            DESTINATION KEY (target_entity) REFERENCES entities (entity_id)
            LABEL related_to PROPERTIES ALL COLUMNS
    );
```

---

## Configuration

Edit `oracle_pageindex/config.yaml`:

```yaml
ollama:
  base_url: "http://localhost:11434"
  model: "gemma3"          # Any Ollama model
  temperature: 0

oracle:
  user: "pageindex"
  password: "pageindex"
  dsn: "localhost:1521/FREEPDB1"
  pool_min: 1
  pool_max: 5
```

Or override via CLI:

```bash
python run.py --model llama3.1 --oracle-dsn myhost:1521/MYPDB index doc.pdf
```

---

## Tech Stack

| Component | Technology |
|---|---|
| **Database** | Oracle Database 26ai Free (SQL Property Graphs, SQL/PGQ) |
| **Graph Model** | `CREATE PROPERTY GRAPH` with ISO SQL:2023 `GRAPH_TABLE` |
| **LLM** | Ollama (gemma3, llama3.1, or any supported model) |
| **Backend** | Python 3.11+, FastAPI, python-oracledb |
| **Visualization** | D3.js v7 (interactive force-directed graph) |
| **PDF Parsing** | PyMuPDF, PyPDF2 |
| **Tokenization** | tiktoken |
| **Container** | Docker Compose |

---

## Project Structure

```
OraclePageIndex/
  oracle_pageindex/
    cli.py              # CLI: init, index, query, serve
    config.yaml         # Ollama + Oracle configuration
    db.py               # Oracle connection pool + schema init
    entity_extractor.py # LLM-powered entity extraction
    graph.py            # Property Graph CRUD + SQL/PGQ queries
    indexer.py          # Full indexing pipeline
    llm.py              # Ollama API client
    parser.py           # PDF parsing + section tree builder
    query.py            # Graph-powered query engine
    utils.py            # Config, tokens, tree manipulation
  api/
    server.py           # FastAPI + D3.js visualization server
  viz/
    index.html          # D3.js single-page app
    graph.js            # Force-directed graph rendering
    style.css           # Dark-theme styling
  tests/                # 30 tests (pytest)
  setup_schema.sql      # Oracle DDL + Property Graph definition
  docker-compose.yml    # Oracle 26ai Free container
  run.py                # CLI entry point
```

---

## What Changed From PageIndex

| | PageIndex | OraclePageIndex |
|---|---|---|
| **Storage** | JSON files on disk | Oracle Property Graph (SQL/PGQ) |
| **LLM** | OpenAI GPT-4o | Ollama (fully local, open-source) |
| **Retrieval** | LLM-driven tree navigation | SQL/PGQ graph traversal + LLM reasoning |
| **Entities** | None | Full named entity extraction + cross-doc linking |
| **Relationships** | None | Entity relationship discovery (RELATED_TO, PART_OF, OPERATES_IN, ...) |
| **Visualization** | None | Interactive D3.js force-directed graph |
| **Multi-document** | Separate JSON per doc | Unified knowledge graph across all documents |
| **API** | None | FastAPI serving graph data + queries |
| **Query interface** | None | Natural-language queries with source citations |

---

## License

[MIT](LICENSE)

---

## Credits

- **[PageIndex](https://github.com/VectifyAI/PageIndex)** by [VectifyAI](https://vectify.ai) -- the original vectorless, reasoning-based RAG framework.
- **[Oracle Database](https://www.oracle.com/database/free/)** -- SQL Property Graphs (SQL/PGQ) provide the graph storage and query foundation.
- **[Ollama](https://ollama.com/)** -- local open-source LLM inference.
- **[D3.js](https://d3js.org/)** -- interactive graph visualization.
