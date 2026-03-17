<div align="center">

# OraclePageIndex: Graph-Powered Document Intelligence

<p align="center"><b>Oracle SQL Property Graphs&nbsp; ◦ &nbsp;Multi-Hop Traversal&nbsp; ◦ &nbsp;Living Knowledge Graph&nbsp; ◦ &nbsp;Graph-Based Reasoning</b></p>

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg?style=for-the-badge)](https://www.python.org/downloads/)
[![Oracle 26ai](https://img.shields.io/badge/Oracle-26ai_Free-red.svg?style=for-the-badge)](https://www.oracle.com/database/free/)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-green.svg?style=for-the-badge)](https://ollama.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![PyPI](https://img.shields.io/badge/PyPI-oracle--pageindex-blue.svg?style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/oracle-pageindex/)

<h4 align="center">
  <a href="#-quick-start">Quick Start</a>&nbsp; • &nbsp;
  <a href="#-how-it-works">How It Works</a>&nbsp; • &nbsp;
  <a href="#-living-graph-features">Living Graph</a>&nbsp; • &nbsp;
  <a href="#-live-demo-apple-10-k-2024">Live Demo</a>&nbsp; • &nbsp;
  <a href="#-sqlpgq--the-power-of-oracle-property-graphs">SQL/PGQ</a>&nbsp; • &nbsp;
  <a href="#-oracle-property-graph-schema">Graph Schema</a>&nbsp;
</h4>

</div>

<details open>
<summary><h3>What Is This?</h3></summary>

**OraclePageIndex** turns documents into **knowledge graphs** stored natively in Oracle Database using **SQL Property Graphs** (SQL/PGQ). Unlike traditional RAG that chunks text and matches vectors, OraclePageIndex builds a structured graph of documents, sections, entities, and relationships, then traverses it with standard SQL to find answers.

It's an Oracle AI Database-powered fork of [PageIndex](https://github.com/VectifyAI/PageIndex) by VectifyAI, replacing OpenAI + JSON files with **Ollama + Oracle Property Graphs**. The result: fully local, fully open-source document intelligence with the power of a real database behind it.

**v0.2.0** introduces the **Living Graph**: multi-hop traversal, conversational memory, temporal versioning, entity resolution, graph enrichment, and transparent query visualization.

</details>

---

# Why Graphs Instead of Vectors?

Traditional vector-based RAG relies on semantic *similarity*, but **similarity isn't relevance**. When a financial analyst searches for "Apple's supply chain risks," cosine similarity might surface paragraphs about fruit supply chains. What we need is **reasoning over structure**, and that's exactly what knowledge graphs provide.

OraclePageIndex builds a **SQL Property Graph** from each document and uses Oracle's `GRAPH_TABLE` with `MATCH` patterns to traverse relationships, the same way a human expert would flip through a table of contents, cross-reference entities, and follow citations.

| | Vector RAG | OraclePageIndex (Graph RAG) |
|---|---|---|
| **How it works** | Chunk text -> embed -> cosine similarity | Parse structure -> extract entities -> graph traversal |
| **Storage** | Vector embeddings in a vector DB | Property graph in Oracle Database |
| **Retrieval** | Approximate nearest-neighbor search | Exact graph traversal via SQL/PGQ |
| **Relationships** | Lost during chunking | First-class citizens (named edges) |
| **Explainability** | Opaque similarity scores | Traceable graph paths with named relationships |
| **Multi-document** | Separate vector spaces per doc | Unified knowledge graph with cross-document links |
| **Query language** | Proprietary APIs | Standard SQL with `GRAPH_TABLE` |
| **Multi-hop reasoning** | Requires re-ranking hacks | Native recursive path expressions (`->+`) |

---

# Living Graph Features

v0.2.0 transforms OraclePageIndex from a static index into a **living knowledge graph** with 7 new capabilities.

### Multi-Hop Query Engine

The query engine now classifies questions by intent (LOOKUP, RELATIONSHIP, EXPLORATION, COMPARISON, HIERARCHICAL, TEMPORAL) and dispatches intent-specific `GRAPH_TABLE MATCH` traversals. A LOOKUP question traverses entity neighborhoods. A RELATIONSHIP question finds paths between entity pairs. An EXPLORATION question expands multi-hop entity chains.

```bash
python run.py query "How does Apple relate to China?"
# Intent: RELATIONSHIP -> find_entity_paths("Apple Inc.", "China mainland")
# Traverses: entity -> related_to -> entity, entity <- mentions <- section
```

Every query returns the SQL/PGQ queries it executed, the traversal path through the graph, and source sections with relevance ranking.

### Conversational Memory

Sessions and turns are stored as graph vertices with edges to every entity and section touched during a conversation. When you pass a `session_id`, the engine injects prior context from the same conversation, so follow-up questions resolve ambiguous references.

```bash
python run.py query "What is Apple's revenue?"           # creates session_id=1
python run.py query "What about their competitors?" --session-id 1  # resolves "their" -> Apple
```

### Temporal Document Versioning

Index multiple versions of the same document and track how entities change over time.

```bash
python run.py index annual-report-2023.pdf --doc-group apple-10k --doc-version 1
python run.py index annual-report-2024.pdf --doc-group apple-10k --doc-version 2
```

The system computes diffs between versions: which entities APPEARED, DISAPPEARED, or remained STABLE. Temporal edges connect entity versions across documents. The D3.js visualization includes a **timeline slider** that color-codes entities by temporal status (green = appeared, red = disappeared, yellow = modified).

### Vector-Assisted Entity Resolution

Entity names extracted from different documents often refer to the same thing ("Apple Inc." vs "Apple" vs "AAPL"). OraclePageIndex uses Ollama embeddings + Oracle `VECTOR_DISTANCE` to find candidate matches, then LLM confirmation to merge duplicates. Controlled via `config.yaml`:

```yaml
entity_resolution:
  enabled: true
  embedding_model: "nomic-embed-text"
  similarity_threshold: 0.3
  auto_confirm_threshold: 0.15
```

Vectors serve the graph here, not replace it. They're used strictly for entity name disambiguation, not for retrieval.

### Graph Enrichment Agent

A post-indexing pass that finds gaps in the knowledge graph and fills them. It detects **isolated entities** (mentioned in sections but with no relationship edges) and **co-occurring pairs** (entities that share sections but aren't linked). For each candidate pair, a focused LLM prompt examines shared section text and discovers relationships.

```bash
python run.py enrich              # full enrichment pass
python run.py enrich --dry-run    # preview candidates without writing
python run.py enrich --max-candidates 50  # limit scope
```

Enriched relationships are tagged with `edge_source='ENRICHMENT'` and a confidence score, so you can distinguish them from extraction-time relationships.

### Query Transparency

Every query response includes:
- **`graph_queries`**: the actual SQL/PGQ statements executed, with row counts and timing
- **`traversal_path`**: step-by-step path through the graph (which entity led to which section, via which edge)
- **`session_id`**: the conversation session for follow-ups

The D3.js visualization renders traversal paths as animated overlays on the graph, with step badges showing the order of traversal and a side panel displaying the SQL/PGQ queries.

### Interactive Graph Visualization

The D3.js frontend now includes:
- **Query bar**: type questions directly in the visualization, see traversal paths animated on the graph
- **Replay**: step through traversal animations at 400ms per step
- **Timeline slider**: scrub through document versions, entities color-coded by temporal status
- **SQL panel**: see the exact `GRAPH_TABLE MATCH` queries the engine ran

---

# Core Features

- **Graph-Based Reasoning**: Retrieval follows named relationships (MENTIONS, PARENT_OF, RELATED_TO), not opaque similarity scores.
- **Multi-Hop Traversal**: SQL/PGQ `GRAPH_TABLE MATCH` with recursive `->+` path expressions for deep graph exploration.
- **Intent Classification**: Questions classified into 6 types, each with a specialized traversal strategy.
- **Conversational Memory**: Session/turn tracking as graph vertices with entity and section edges.
- **Temporal Versioning**: Track entity changes across document versions with diff computation.
- **Entity Resolution**: Vector-assisted deduplication with LLM confirmation.
- **Graph Enrichment**: Automated gap-filling discovers relationships between isolated entities.
- **Standard SQL**: Every query is pure SQL with `GRAPH_TABLE`. No proprietary graph query language.
- **Fully Local**: Ollama for LLM + embeddings, Oracle Free for storage. No API keys, no cloud dependencies.
- **Interactive Visualization**: D3.js force-directed graph with query path overlay, timeline slider, and SQL transparency.

---

# Live Demo: Apple 10-K 2024

We indexed Apple's 121-page annual report (SEC 10-K filing, fiscal year 2024) end-to-end. Here's what Oracle's property graph captured:

### Graph Statistics

| Metric | Count |
|--------|-------|
| **Document** | 1 (Apple 10-K 2024) |
| **Sections** | 121 page-level sections with summaries |
| **Entities** | 686 unique entities extracted via LLM |
| **Mention Edges** | 951 section -> entity connections |
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

### Sample Multi-Hop Query

```bash
$ python run.py query "How does Apple relate to China?"
```

> **Intent:** RELATIONSHIP
>
> **Graph traversal:** `Apple Inc. -[OPERATES_IN]-> China mainland`, then neighborhood expansion to find shared sections discussing supply chain, manufacturing, and tariff risks.
>
> **SQL/PGQ executed:**
> ```sql
> SELECT ... FROM GRAPH_TABLE (doc_knowledge_graph
>     MATCH (e1 IS entity WHERE e1.name = :source)
>           -[r IS related_to]->
>           (e2 IS entity WHERE e2.name = :target)
>     COLUMNS (...)
> )
> ```
>
> **Answer:** Apple operates manufacturing facilities in China mainland through contract manufacturers. Key supply chain risks include tariff exposure, geopolitical tensions, and concentration risk...
>
> **Sources:** Pages 3, 9, 11, 27, 45, 76, 81, 98, 99

---

# How It Works

OraclePageIndex processes documents in two phases: **indexing** (PDF -> Property Graph) and **querying** (question -> intent classification -> graph traversal -> answer).

### Indexing Pipeline

```
  PDF Document
       |
       v
  +--------------+
  |  1. Parse     |  Extract text per page, detect structure
  +------+-------+
         v
  +--------------+
  | 2. Structure  |  Ollama builds hierarchical section tree
  +------+-------+
         v
  +---------------+
  | 3. Summarize  |  Generate concise summary per section
  +------+-------+
         v
  +------------------+
  | 4. Extract       |  Ollama identifies PERSON, ORG, TECH, CONCEPT...
  |    Entities      |
  +------+-----------+
         v
  +------------------+
  | 5. Store in      |  INSERT vertices + edges into Property Graph
  |    Oracle        |
  +------+-----------+
         v
  +------------------+
  | 6. Link          |  Ollama discovers cross-entity relationships
  |    Entities      |
  +------+-----------+
         v
  +------------------+
  | 7. Resolve       |  Vector-assisted entity deduplication (optional)
  +------+-----------+
         v
  +------------------+
  | 8. Enrich        |  Discover missing relationships (optional)
  +------------------+

  Result: A rich Oracle Property Graph with SQL/PGQ access
```

### Query Pipeline

```
  User Question: "How does Apple relate to China?"
       |
       v
  +---------------------+
  | 1. Intent           |  Classify: RELATIONSHIP
  |    Classification   |  Extract entities: ["Apple", "China"]
  +------+--------------+
         v
  +---------------------+
  | 2. Entity           |  Resolve to entity_ids via name match
  |    Resolution       |  (vector-assisted when available)
  +------+--------------+
         v
  +---------------------+
  | 3. Graph Traversal  |  GRAPH_TABLE MATCH: find_entity_paths()
  |    (intent-specific)|  traverse_entity_neighborhood()
  +------+--------------+
         v
  +---------------------+
  | 4. Context          |  Retrieve text from graph-matched sections
  |    Assembly         |  Rank by hop distance + relevance
  +------+--------------+
         v
  +---------------------+
  | 5. LLM Reasoning    |  Ollama reasons over graph-retrieved context
  +---------------------+

  -> QueryResult with answer, sources, graph_queries, traversal_path
```

---

# Quick Start

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

The key grant is `CREATE PROPERTY GRAPH`, which enables Oracle's SQL/PGQ capabilities.

### 3. Install & Initialize

```bash
pip install oracledb httpx pyyaml tiktoken PyPDF2 PyMuPDF fastapi uvicorn
```

```bash
# Initialize the schema (creates tables + Property Graph)
python run.py init
```

This creates the Oracle Property Graph `doc_knowledge_graph` with:
- **5 vertex tables**: `documents`, `sections`, `entities`, `sessions`, `turns`
- **8 edge tables**: `section_hierarchy`, `section_entities`, `entity_relationships`, `turn_entities`, `turn_sections`, `temporal_edges`, `entity_aliases`

### 4. Index a Document

```bash
python run.py index /path/to/document.pdf
```

With version tracking:
```bash
python run.py index report-2023.pdf --doc-group annual-report --doc-version 1
python run.py index report-2024.pdf --doc-group annual-report --doc-version 2
```

### 5. Enrich the Graph (optional)

```bash
python run.py enrich          # discover missing relationships
python run.py enrich --dry-run  # preview without writing
```

### 6. Query the Knowledge Graph

```bash
python run.py query "What are the key financial risks?"
```

The query engine:
1. Classifies your question by intent (LOOKUP, RELATIONSHIP, EXPLORATION, etc.)
2. Traverses the Oracle Property Graph with intent-specific `GRAPH_TABLE MATCH` patterns
3. Enriches context with related entities via multi-hop expansion
4. Reasons over the graph-retrieved context for a grounded answer

### 7. Visualize

```bash
python run.py serve
# Open http://localhost:8000
```

Interactive D3.js force-directed graph with:
- **Color-coded nodes**: Documents (blue), Sections (green), Entities (orange)
- **Edge types**: Hierarchy (solid), Mentions (dashed), Relationships (dotted)
- **Query bar**: Ask questions directly, see traversal paths animated on the graph
- **Timeline slider**: Scrub through document versions with color-coded entity changes
- **SQL panel**: View the exact SQL/PGQ queries executed

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

# SQL/PGQ: The Power of Oracle Property Graphs

The entire knowledge graph is queryable with standard SQL using `GRAPH_TABLE`. No proprietary graph query language, just SQL.

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

### Multi-Hop Entity Path (new in v0.2.0)

```sql
-- Find how two entities connect through the graph
SELECT e1.name, r1.relationship, mid.name, r2.relationship, e2.name
FROM GRAPH_TABLE (doc_knowledge_graph
    MATCH (e1 IS entity WHERE e1.name = :source)
          -[r1 IS related_to]-> (mid IS entity)
          -[r2 IS related_to]-> (e2 IS entity WHERE e2.name = :target)
    COLUMNS (e1.name, r1.relationship, mid.name, r2.relationship, e2.name)
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

The `->+` syntax is SQL/PGQ's recursive path expression, traversing the hierarchy to any depth in a single query. No recursive CTEs needed.

### Conversation History via Graph

```sql
-- Find entities discussed in a conversation session
SELECT t.question, e.name, te.role
FROM GRAPH_TABLE (doc_knowledge_graph
    MATCH (s IS session WHERE s.session_id = :sid)
          <-[st]- (t IS turn)
          -[te IS turn_entity]-> (e IS entity)
    COLUMNS (t.question, e.name, te.role)
);
```

---

# Oracle Property Graph Schema

v0.2.0 schema: **5 vertex tables + 7 edge labels** in a single property graph.

```sql
CREATE PROPERTY GRAPH doc_knowledge_graph
    VERTEX TABLES (
        documents   KEY (doc_id)      LABEL document  PROPERTIES ALL COLUMNS,
        sections    KEY (section_id)  LABEL section   PROPERTIES ALL COLUMNS,
        entities    KEY (entity_id)   LABEL entity    PROPERTIES ALL COLUMNS,
        sessions    KEY (session_id)  LABEL session   PROPERTIES ALL COLUMNS,
        turns       KEY (turn_id)     LABEL turn      PROPERTIES ALL COLUMNS
    )
    EDGE TABLES (
        section_hierarchy    LABEL parent_of     -- section -> section
        section_entities     LABEL mentions      -- section -> entity
        entity_relationships LABEL related_to    -- entity -> entity
        turn_entities        LABEL turn_entity   -- turn -> entity
        turn_sections        LABEL turn_section  -- turn -> section
        temporal_edges       LABEL changed_in    -- entity -> document
        entity_aliases       LABEL alias_of      -- entity -> entity
    );
```

<details>
<summary><strong>What's new in v0.2.0</strong></summary>
<br>

- **`sessions`** and **`turns`** vertex tables for conversational memory
- **`turn_entities`** and **`turn_sections`** edges tracking which entities/sections each conversation turn touched
- **`temporal_edges`** tracking entity changes (APPEARED, DISAPPEARED, MODIFIED, STABLE) across document versions
- **`entity_aliases`** linking duplicate entity names to canonical entities
- **`documents`** gained `doc_group` and `doc_version` columns for version tracking
- **`entities`** gained `name_embedding VECTOR(384, FLOAT32)` for entity resolution, plus `canonical_id`, `first_seen_doc`, `last_seen_doc`
- **`entity_relationships`** gained `edge_source` (EXTRACTION vs ENRICHMENT) and `confidence` score

</details>

---

# Configuration

Edit `oracle_pageindex/config.yaml`:

```yaml
ollama:
  base_url: "http://localhost:11434"
  model: "gemma3"          # Any Ollama model
  temperature: 0

oracle:
  user: "pageindex"
  password: "pageindex"  # pragma: allowlist secret
  dsn: "localhost:1521/FREEPDB1"
  pool_min: 1
  pool_max: 5

entity_resolution:
  enabled: true
  embedding_model: "nomic-embed-text"
  similarity_threshold: 0.3       # VECTOR_DISTANCE cutoff
  auto_confirm_threshold: 0.15    # below this, auto-merge without LLM
```

---

# API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | D3.js visualization |
| GET | `/api/graph` | Full knowledge graph (nodes + edges) |
| GET | `/api/graph?doc_group=X&version=N` | Version-filtered graph with temporal status |
| GET | `/api/documents` | All indexed documents |
| GET | `/api/documents/{id}/sections` | Sections for a document |
| GET | `/api/entities` | All extracted entities |
| GET | `/api/entities/{name}/sections` | Sections mentioning an entity |
| GET | `/api/entities/{name}/related` | Related entities |
| GET | `/api/query?q=...` | Natural-language query with graph traversal |
| GET | `/api/query?q=...&session_id=N` | Continue a conversation session |
| GET | `/api/sessions` | List conversation sessions |
| GET | `/api/sessions/{id}/turns` | Turns in a conversation session |

---

# Testing

179 unit tests covering all modules. All tests use mocked Oracle and Ollama connections, no running services needed.

```bash
pytest tests/ -v
```

```
tests/test_api.py              13 tests  (all FastAPI endpoints)
tests/test_db.py                3 tests  (connection pool, schema init, close)
tests/test_enricher.py          7 tests  (graph enrichment agent)
tests/test_entity_extractor.py  3 tests  (entity extraction, relationships)
tests/test_entity_resolver.py  20 tests  (vector-assisted entity resolution)
tests/test_graph.py            28 tests  (CRUD + multi-hop traversal + enrichment)
tests/test_indexer.py           8 tests  (indexing pipeline + resolution wiring)
tests/test_intent.py            9 tests  (intent classification)
tests/test_llm.py               8 tests  (sync/async chat, JSON extraction, embeddings)
tests/test_models.py            5 tests  (data classes)
tests/test_query.py            26 tests  (multi-hop query engine + sessions)
tests/test_schema.py           13 tests  (schema DDL validation)
tests/test_sessions.py          9 tests  (conversational memory CRUD)
tests/test_temporal.py         16 tests  (temporal versioning + diffs)
tests/test_utils.py            11 tests  (config, tokens, tree manipulation)
```

---

# Project Structure

```
OraclePageIndex/
  oracle_pageindex/
    cli.py              # CLI: init, index, query, serve, enrich
    config.yaml         # Ollama + Oracle + entity resolution config
    db.py               # Oracle connection pool + schema init
    enricher.py         # Graph enrichment agent (gap-filling)
    entity_extractor.py # LLM-powered entity extraction
    entity_resolver.py  # Vector-assisted entity deduplication
    graph.py            # Property Graph CRUD + SQL/PGQ queries
    indexer.py          # Full indexing pipeline with resolution + temporal
    llm.py              # Ollama API client (chat + embeddings)
    models.py           # Shared data classes (QueryResult, QueryIntent, etc.)
    parser.py           # PDF parsing + section tree builder
    query.py            # Multi-hop graph query engine with intent dispatch
    utils.py            # Config, tokens, tree manipulation
  api/
    server.py           # FastAPI + D3.js visualization server
  viz/
    index.html          # D3.js app with query bar + timeline slider
    graph.js            # Force-directed graph + traversal path overlay
    style.css           # Dark-theme styling + temporal entity colors
  tests/                # 179 tests (pytest, fully mocked)
  setup_schema.sql      # Oracle DDL: 5 vertex + 8 edge tables + Property Graph
  docker-compose.yml    # Oracle 26ai Free container
  run.py                # CLI entry point
```

---

# What Changed From PageIndex

| | PageIndex | OraclePageIndex v0.2.0 |
|---|---|---|
| **Storage** | JSON files on disk | Oracle Property Graph (SQL/PGQ) |
| **LLM** | OpenAI GPT-4o | Ollama (fully local, open-source) |
| **Retrieval** | LLM-driven tree navigation | Multi-hop SQL/PGQ graph traversal + intent classification |
| **Query engine** | Single-strategy | 6 intent-specific traversal strategies |
| **Entities** | None | Full extraction + vector-assisted deduplication |
| **Relationships** | None | Extraction + enrichment (gap-filling agent) |
| **Memory** | None | Conversational sessions stored as graph vertices |
| **Versioning** | None | Temporal tracking across document versions |
| **Visualization** | None | D3.js with query overlay, timeline slider, SQL panel |
| **Multi-document** | Separate JSON per doc | Unified knowledge graph across all documents |
| **API** | None | FastAPI with 12 endpoints |
| **Tests** | None | 179 mocked unit tests |

---

# Tech Stack

| Component | Technology |
|---|---|
| **Database** | Oracle Database 26ai Free (SQL Property Graphs, SQL/PGQ) |
| **Graph Model** | `CREATE PROPERTY GRAPH` with ISO SQL:2023 `GRAPH_TABLE` |
| **LLM** | Ollama (gemma3, llama3.1, or any supported model) |
| **Embeddings** | Ollama (nomic-embed-text for entity resolution) |
| **Backend** | Python 3.11+, FastAPI, python-oracledb |
| **Visualization** | D3.js v7 (interactive force-directed graph) |
| **PDF Parsing** | PyMuPDF, PyPDF2 |
| **Tokenization** | tiktoken |
| **Container** | Docker Compose |

---

# Credits & Acknowledgments

- **[PageIndex](https://github.com/VectifyAI/PageIndex)** by [VectifyAI](https://vectify.ai) -- the original vectorless, reasoning-based RAG framework that inspired this project.
- **[Oracle Database](https://www.oracle.com/database/free/)** -- SQL Property Graphs (SQL/PGQ) provide the graph storage and query foundation.
- **[Ollama](https://ollama.com/)** -- local open-source LLM inference.
- **[D3.js](https://d3js.org/)** -- interactive graph visualization.

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
> **One-command install** -- clone, configure, and run in a single step:
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
> # See above for setup instructions
> ```
> </details>
