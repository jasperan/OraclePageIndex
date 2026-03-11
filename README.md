<div align="center">

# OraclePageIndex: Graph-Powered Document Intelligence

<p align="center"><b>Oracle SQL Property Graphs&nbsp; ◦ &nbsp;No Vector DB&nbsp; ◦ &nbsp;No Embeddings&nbsp; ◦ &nbsp;Graph-Based Reasoning</b></p>

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg?style=for-the-badge)](https://www.python.org/downloads/)
[![Oracle 26ai](https://img.shields.io/badge/Oracle-26ai_Free-red.svg?style=for-the-badge)](https://www.oracle.com/database/free/)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-green.svg?style=for-the-badge)](https://ollama.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![PyPI](https://img.shields.io/badge/PyPI-oracle--pageindex-blue.svg?style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/oracle-pageindex/)

<h4 align="center">
  <a href="#-quick-start">Quick Start</a>&nbsp; • &nbsp;
  <a href="#-how-it-works">How It Works</a>&nbsp; • &nbsp;
  <a href="#-live-demo-apple-10-k-2024">Live Demo</a>&nbsp; • &nbsp;
  <a href="#-sqlpgq--the-power-of-oracle-property-graphs">SQL/PGQ</a>&nbsp; • &nbsp;
  <a href="#-oracle-property-graph-schema">Graph Schema</a>&nbsp;
</h4>

</div>

<details open>
<summary><h3>What Is This?</h3></summary>

**OraclePageIndex** turns documents into **knowledge graphs** stored natively in Oracle Database using **SQL Property Graphs** (SQL/PGQ). Unlike traditional RAG that chunks text and matches vectors, OraclePageIndex builds a structured graph of documents, sections, entities, and relationships — then traverses it with standard SQL to find answers.

It's an Oracle AI Database-powered fork of [PageIndex](https://github.com/VectifyAI/PageIndex) by VectifyAI, replacing OpenAI + JSON files with **Ollama + Oracle Property Graphs**. The result: fully local, fully open-source document intelligence with the power of a real database behind it.

</details>

---

# 📑 Why Graphs Instead of Vectors?

Traditional vector-based RAG relies on semantic *similarity* — but **similarity ≠ relevance**. When a financial analyst searches for "Apple's supply chain risks," cosine similarity might surface paragraphs about fruit supply chains. What we need is **reasoning over structure**, and that's exactly what knowledge graphs provide.

OraclePageIndex builds a **SQL Property Graph** from each document and uses Oracle's `GRAPH_TABLE` with `MATCH` patterns to traverse relationships — the same way a human expert would flip through a table of contents, cross-reference entities, and follow citations.

| | Vector RAG | OraclePageIndex (Graph RAG) |
|---|---|---|
| **How it works** | Chunk text → embed → cosine similarity | Parse structure → extract entities → graph traversal |
| **Storage** | Vector embeddings in a vector DB | Property graph in Oracle Database |
| **Retrieval** | Approximate nearest-neighbor search | Exact graph traversal via SQL/PGQ |
| **Relationships** | Lost during chunking | First-class citizens (named edges) |
| **Explainability** | Opaque similarity scores | Traceable graph paths with named relationships |
| **Multi-document** | Separate vector spaces per doc | Unified knowledge graph with cross-document links |
| **Query language** | Proprietary APIs | Standard SQL with `GRAPH_TABLE` |
| **Multi-hop reasoning** | Requires re-ranking hacks | Native recursive path expressions (`->+`) |

### 🎯 Core Features

- **No Vector DB**: Uses document structure and LLM reasoning for retrieval, powered by Oracle SQL Property Graphs.
- **No Chunking**: Documents are organized into natural sections, not arbitrary fixed-size chunks.
- **Graph-Based Reasoning**: Retrieval follows named relationships (MENTIONS, PARENT_OF, RELATED_TO) — not opaque similarity scores.
- **Standard SQL**: Every query is pure SQL with `GRAPH_TABLE`. No proprietary graph query language to learn.
- **Fully Local**: Ollama for LLM inference, Oracle Free for storage. No API keys, no cloud dependencies.
- **Entity Extraction**: LLM-powered extraction of people, organizations, technologies, locations, concepts, and more.
- **Interactive Visualization**: D3.js force-directed graph with color-coded nodes, searchable entities, and multiple layouts.

---

# 📈 Live Demo: Apple 10-K 2024

We indexed Apple's 121-page annual report (SEC 10-K filing, fiscal year 2024) end-to-end. Here's what Oracle's property graph captured:

### Graph Statistics

| Metric | Count |
|--------|-------|
| **Document** | 1 (Apple 10-K 2024) |
| **Sections** | 121 page-level sections with summaries |
| **Entities** | 686 unique entities extracted via LLM |
| **Mention Edges** | 951 section → entity connections |
| **Entity Relationships** | 33 cross-entity links |
| **D3.js Graph** | 808 nodes, 1,105 edges |

<details open>
<summary><b>Entity Types Extracted</b></summary>

The LLM extracted structured entities across categories:

- **Organizations**: Apple Inc., SEC, Standard & Poor's, Bank of New York Mellon
- **Products**: iPhone 16 Pro, iPhone 16, iPhone SE, Apple Watch Series 10, Mac
- **Technologies**: iOS, macOS, Apple Intelligence, XBRL
- **People**: Timothy D. Cook, Luca Maestri, Arthur D. Levinson, board members
- **Locations**: China mainland, India, Japan, South Korea, Taiwan, Vietnam
- **Concepts**: Risk Factors, Cybersecurity, Human Capital, Net Sales, Tariffs
- **Financial**: Common Stock, Equity Awards, RSUs, Commercial Paper, Term Debt

</details>

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

# 🌲 How It Works

OraclePageIndex processes documents in two phases: **indexing** (PDF → Property Graph) and **querying** (question → graph traversal → answer).

### Indexing Pipeline

```
  PDF Document
       │
       ▼
  ┌─────────────┐
  │  1. Parse    │  Extract text per page, detect structure
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │ 2. Structure │  Ollama builds hierarchical section tree
  └──────┬──────┘
         ▼
  ┌──────────────┐
  │ 3. Summarize │  Generate concise summary per section
  └──────┬──────┘
         ▼
  ┌──────────────────┐
  │ 4. Extract       │  Ollama identifies PERSON, ORG, TECH, CONCEPT...
  │    Entities      │
  └──────┬───────────┘
         ▼
  ┌──────────────────┐
  │ 5. Store in      │  INSERT vertices + edges into Property Graph
  │    Oracle        │
  └──────┬───────────┘
         ▼
  ┌──────────────────┐
  │ 6. Link          │  Ollama discovers cross-entity relationships
  │    Entities      │
  └──────────────────┘

  Result: A rich Oracle Property Graph with SQL/PGQ access
```

### Query Pipeline

```
  User Question: "What products does Apple sell?"
       │
       ▼
  ┌────────────────────┐
  │ 1. Concept         │  Ollama extracts: ["Apple", "products"]
  │    Extraction      │
  └──────┬─────────────┘
         ▼
  ┌────────────────────┐
  │ 2. Graph Traversal │  SQL/PGQ finds matching entities + sections
  └──────┬─────────────┘
         ▼
  ┌────────────────────┐
  │ 3. Context         │  Retrieve text from graph-matched sections
  │    Assembly        │
  └──────┬─────────────┘
         ▼
  ┌────────────────────┐
  │ 4. LLM Reasoning   │  Ollama reasons over graph-retrieved context
  └────────────────────┘

  → Answer with sources and related entities from the graph
```

### Architecture

```
                       OraclePageIndex Architecture

+----------+       +---------+       +───────────────────────────+
│          │       │         │       │   Oracle Database 26ai    │
│   PDF    ├──────►│ Ollama  ├──────►│                           │
│ Document │       │  LLM    │       │  ┌─────────────────────┐  │
+----------+       +---------+       │  │ Property Graph      │  │
                    │  parse    │       │  │                     │  │
                    │  extract  │       │  │ [documents]───┐     │  │
                    │  reason   │       │  │ [sections]────┤     │  │
                    +--------+  │       │  │ [entities]────┤     │  │
                             │  │       │  │ [relationships]     │  │
                             ▼  ▼       │  └─────────────────────┘  │
                       +---------+      +────────────┬──────────────+
                       │         │                   │
                       │ FastAPI │◄──────────────────┘
                       │ Server  │     SQL/PGQ queries
                       +----┬----+
                            │
                            ▼
                    ┌───────────────┐
                    │    D3.js      │
                    │ Visualization │
                    │ (Force Graph) │
                    └───────────────┘
```

---

# ⚙️ Quick Start

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

The key grant is `CREATE PROPERTY GRAPH` — this enables Oracle's SQL/PGQ capabilities.

### 3. Install & Initialize

```bash
pip install oracledb httpx pyyaml tiktoken PyPDF2 PyMuPDF fastapi uvicorn
```

```bash
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

<details>
<summary><strong>Example output</strong></summary>

```
Indexing complete.
  Document:      apple-10k-2024.pdf
  Sections:      121
  Entities:      686
  Relationships: 33
```

</details>

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

<details>
<summary><strong>Optional CLI parameters</strong></summary>
<br>

```bash
# Override model or Oracle DSN
python run.py --model llama3.1 --oracle-dsn myhost:1521/MYPDB index doc.pdf

# Verbose logging
python run.py -v query "What is the revenue?"

# Custom server host/port
python run.py serve --host 0.0.0.0 --port 9000
```

</details>

---

# 🔌 SQL/PGQ — The Power of Oracle Property Graphs

The entire knowledge graph is queryable with standard SQL using `GRAPH_TABLE`. This is what makes Oracle special — no proprietary graph query language, just SQL.

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

The `->+` syntax is SQL/PGQ's recursive path expression — it traverses the hierarchy to any depth in a single query. No recursive CTEs needed.

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

# 🗂️ Oracle Property Graph Schema

```sql
CREATE PROPERTY GRAPH doc_knowledge_graph
    VERTEX TABLES (
        documents   KEY (doc_id)     LABEL document  PROPERTIES ALL COLUMNS,
        sections    KEY (section_id) LABEL section   PROPERTIES ALL COLUMNS,
        entities    KEY (entity_id)  LABEL entity    PROPERTIES ALL COLUMNS
    )
    EDGE TABLES (
        section_hierarchy   -- parent_of: section → section
            KEY (edge_id)
            SOURCE KEY (parent_id) REFERENCES sections (section_id)
            DESTINATION KEY (child_id) REFERENCES sections (section_id)
            LABEL parent_of PROPERTIES ALL COLUMNS,
        section_entities    -- mentions: section → entity
            KEY (edge_id)
            SOURCE KEY (section_id) REFERENCES sections (section_id)
            DESTINATION KEY (entity_id) REFERENCES entities (entity_id)
            LABEL mentions PROPERTIES ALL COLUMNS,
        entity_relationships -- related_to: entity → entity
            KEY (edge_id)
            SOURCE KEY (source_entity) REFERENCES entities (entity_id)
            DESTINATION KEY (target_entity) REFERENCES entities (entity_id)
            LABEL related_to PROPERTIES ALL COLUMNS
    );
```

<details>
<summary><strong>Relational tables (under the Property Graph)</strong></summary>
<br>

Oracle SQL Property Graphs are defined on top of standard relational tables. You always retain full relational SQL access to the same data.

```sql
-- Vertex tables
CREATE TABLE documents (
    doc_id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    doc_name        VARCHAR2(500) NOT NULL,
    doc_description CLOB,
    source_path     VARCHAR2(1000),
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP
);

CREATE TABLE sections (
    section_id    NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    doc_id        NUMBER NOT NULL REFERENCES documents(doc_id),
    node_id       VARCHAR2(10),
    title         VARCHAR2(1000),
    summary       CLOB,
    text_content  CLOB,
    start_index   NUMBER,
    end_index     NUMBER,
    depth_level   NUMBER DEFAULT 0
);

CREATE TABLE entities (
    entity_id     NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          VARCHAR2(500) NOT NULL,
    entity_type   VARCHAR2(100),
    description   CLOB,
    CONSTRAINT uq_entity UNIQUE (name, entity_type)
);

-- Edge tables
CREATE TABLE section_hierarchy (
    edge_id   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_id NUMBER NOT NULL REFERENCES sections(section_id),
    child_id  NUMBER NOT NULL REFERENCES sections(section_id)
);

CREATE TABLE section_entities (
    edge_id    NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    section_id NUMBER NOT NULL REFERENCES sections(section_id),
    entity_id  NUMBER NOT NULL REFERENCES entities(entity_id),
    relevance  VARCHAR2(20) DEFAULT 'MENTIONS'
);

CREATE TABLE entity_relationships (
    edge_id       NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_entity NUMBER NOT NULL REFERENCES entities(entity_id),
    target_entity NUMBER NOT NULL REFERENCES entities(entity_id),
    relationship  VARCHAR2(100) DEFAULT 'RELATED_TO'
);
```

</details>

---

# 🛠️ Configuration

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

---

# 🧪 Testing

The project includes 30 unit tests covering all core modules. All tests use mocked Oracle and Ollama connections — no running services needed.

```bash
pytest tests/ -v
```

```
tests/test_db.py                3 tests  (connection pool, schema init, close)
tests/test_entity_extractor.py  3 tests  (entity extraction, relationships, edge cases)
tests/test_graph.py            19 tests  (all CRUD operations + SQL/PGQ queries)
tests/test_llm.py               5 tests  (sync/async chat, JSON extraction)
```

---

# 🗺️ Project Structure

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

# 🔄 What Changed From PageIndex

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

# 🛠️ Tech Stack

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

# ⭐ Credits & Acknowledgments

- **[PageIndex](https://github.com/VectifyAI/PageIndex)** by [VectifyAI](https://vectify.ai) — the original vectorless, reasoning-based RAG framework that inspired this project.
- **[Oracle Database](https://www.oracle.com/database/free/)** — SQL Property Graphs (SQL/PGQ) provide the graph storage and query foundation.
- **[Ollama](https://ollama.com/)** — local open-source LLM inference.
- **[D3.js](https://d3js.org/)** — interactive graph visualization.

Leave a star if you find this useful!

---

<div align="center">

[![GitHub](https://img.shields.io/badge/GitHub-jasperan-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/jasperan)&nbsp;
[![LinkedIn](https://img.shields.io/badge/LinkedIn-jasperan-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/jasperan/)&nbsp;
[![Oracle](https://img.shields.io/badge/Oracle_Database-Free-F80000?style=for-the-badge&logo=oracle&logoColor=white)](https://www.oracle.com/database/free/)

[MIT License](LICENSE)

</div>


## Installation

<!-- one-command-install -->
> **One-command install** — clone, configure, and run in a single step:
>
> ```bash
> curl -fsSL https://raw.githubusercontent.com/jasperan/OraclePageIndex/main/install.sh | bash
> ```
>
> <details><summary>Advanced options</summary>
>
> Override install location:
> ```bash
> PROJECT_DIR=/opt/myapp curl -fsSL https://raw.githubusercontent.com/jasperan/OraclePageIndex/main/install.sh | bash
> ```
>
> Or install manually:
> ```bash
> git clone https://github.com/jasperan/OraclePageIndex.git
> cd OraclePageIndex
> # See below for setup instructions
> ```
> </details>
