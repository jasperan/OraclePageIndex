# OraclePageIndex Cookbook

Hands-on notebooks showcasing **OraclePageIndex** — reasoning-based, vectorless document intelligence powered by Oracle SQL Property Graphs and Ollama.

---

## Notebooks

| # | Notebook | Oracle Required | Description |
|---|----------|:-:|---|
| 1 | **[Simple Graph RAG](graph_RAG_simple.ipynb)** | No | Minimal vectorless RAG: parse a PDF into a tree with Ollama, search via LLM reasoning, generate answers. No database needed. |
| 2 | **[Oracle Graph Quickstart](oracle_graph_quickstart.ipynb)** | Yes | Full pipeline: index a PDF into an Oracle Property Graph, query with natural language and SQL/PGQ. |
| 3 | **[Graph Retrieval](graph_retrieval.ipynb)** | Yes | Deep dive into SQL/PGQ structured retrieval: entity search, relationship discovery, multi-hop traversal. |
| 4 | **[Vision RAG](vision_RAG_oracle.ipynb)** | No | Vision-based RAG: send PDF page images directly to a multimodal Ollama model — no OCR needed. |

---

## Prerequisites

**All notebooks:**
- [Ollama](https://ollama.com/) running locally with a model pulled (`ollama pull gemma3`)
- Python packages: `pip install -e .` from project root

**Notebooks 2 & 3 (Oracle):**
- Oracle Database 26ai Free running (`docker compose up -d` from project root)
- Database user `pageindex` with `CREATE PROPERTY GRAPH` grant (see main [README](../README.md))

**Notebook 4 (Vision):**
- A vision-capable Ollama model (`gemma3` supports multimodal out of the box)
- PyMuPDF: `pip install PyMuPDF`

---

## Recommended Order

1. Start with **Simple Graph RAG** to understand the core concept (tree search, no vectors)
2. Move to **Oracle Graph Quickstart** to see the full pipeline with persistent storage
3. Explore **Graph Retrieval** for advanced SQL/PGQ queries and structured retrieval
4. Try **Vision RAG** for multimodal document QA over page images

---

*Built with [OraclePageIndex](https://github.com/jasperan/OraclePageIndex) — Oracle AI Database powered document intelligence with Property Graphs.*
