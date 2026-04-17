#!/usr/bin/env python3
"""Baseline vector RAG for fair comparison against OraclePageIndex.

Uses the same PDF, same Ollama model, same questions.
Chunks text -> embeds with nomic-embed-text -> cosine similarity retrieval -> LLM answer.
"""

import json
import math
import sys
import time

sys.path.insert(0, ".")

import httpx
import pymupdf

OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
CHAT_MODEL = "gemma4"
CHUNK_SIZE = 500  # tokens (approximate by words)
CHUNK_OVERLAP = 50
TOP_K = 5


def extract_pages(pdf_path: str) -> list[str]:
    """Extract text per page from a PDF."""
    doc = pymupdf.open(pdf_path)
    pages = [page.get_text() or "" for page in doc]
    doc.close()
    return pages


def chunk_text(pages: list[str], chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[dict]:
    """Split pages into overlapping chunks."""
    full_text = "\n\n".join(f"[Page {i+1}]\n{p}" for i, p in enumerate(pages) if p.strip())
    words = full_text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_text = " ".join(words[start:end])
        chunks.append({
            "id": len(chunks),
            "text": chunk_text,
            "word_count": end - start,
        })
        start += chunk_size - overlap
    return chunks


def get_embedding(text: str) -> list[float]:
    """Get embedding from Ollama."""
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": text},
        timeout=300.0,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"][0]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve_top_k(query_embedding: list[float], chunk_embeddings: list[dict], k: int = TOP_K) -> list[dict]:
    """Retrieve top-k chunks by cosine similarity."""
    scored = []
    for chunk in chunk_embeddings:
        sim = cosine_similarity(query_embedding, chunk["embedding"])
        scored.append({**chunk, "similarity": sim})
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:k]


def chat(question: str, context: str) -> str:
    """Send question + context to Ollama for answering."""
    prompt = f"""Answer the question based on the provided context. Be specific and cite relevant details.

Context:
{context}

Question: {question}

Answer:"""
    resp = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": CHAT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=300.0,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def run_baseline_rag(pdf_path: str, questions: list[str]) -> dict:
    """Run the full baseline RAG pipeline."""
    print("=" * 60)
    print("Baseline Vector RAG")
    print("=" * 60)

    # 1. Extract and chunk
    t0 = time.perf_counter()
    pages = extract_pages(pdf_path)
    chunks = chunk_text(pages)
    parse_ms = (time.perf_counter() - t0) * 1000
    print(f"\nParsed {len(pages)} pages into {len(chunks)} chunks ({parse_ms:.0f}ms)")

    # 2. Embed all chunks
    t0 = time.perf_counter()
    print(f"Embedding {len(chunks)} chunks with {EMBED_MODEL}...")
    for i, chunk in enumerate(chunks):
        chunk["embedding"] = get_embedding(chunk["text"])
        if (i + 1) % 10 == 0:
            print(f"  Embedded {i+1}/{len(chunks)}")
    embed_ms = (time.perf_counter() - t0) * 1000
    print(f"Embedding complete ({embed_ms:.0f}ms)")

    # 3. Query
    results = []
    for q in questions:
        print(f"\nQuery: {q}")
        t0 = time.perf_counter()

        # Embed query
        q_emb = get_embedding(q)

        # Retrieve
        top_chunks = retrieve_top_k(q_emb, chunks)
        retrieval_ms = (time.perf_counter() - t0) * 1000

        # Build context
        context = "\n\n---\n\n".join(c["text"] for c in top_chunks)

        # Answer
        t1 = time.perf_counter()
        answer = chat(q, context)
        reasoning_ms = (time.perf_counter() - t1) * 1000

        total_ms = (time.perf_counter() - t0) * 1000

        result = {
            "question": q,
            "answer": answer[:500],
            "top_k_similarities": [round(c["similarity"], 4) for c in top_chunks],
            "chunks_retrieved": len(top_chunks),
            "retrieval_ms": round(retrieval_ms, 1),
            "reasoning_ms": round(reasoning_ms, 1),
            "total_ms": round(total_ms, 1),
        }
        results.append(result)
        print(f"  Answer: {answer[:200]}...")
        print(f"  Retrieval: {retrieval_ms:.0f}ms | Reasoning: {reasoning_ms:.0f}ms")

    report = {
        "system": "baseline_vector_rag",
        "pdf": pdf_path,
        "pages": len(pages),
        "chunks": len(chunks),
        "chunk_size": CHUNK_SIZE,
        "embed_model": EMBED_MODEL,
        "chat_model": CHAT_MODEL,
        "parse_ms": round(parse_ms, 1),
        "embed_ms": round(embed_ms, 1),
        "queries": results,
    }

    with open("scripts/baseline_rag_results.json", "w") as f:
        json.dump(report, f, indent=2)
    print("\nResults written to scripts/baseline_rag_results.json")
    return report


# Standard comparison questions (same for both systems)
COMPARISON_QUESTIONS = [
    # LOOKUP
    "What is Constitutional AI?",
    # RELATIONSHIP
    "How does RLHF relate to Constitutional AI?",
    # EXPLORATION
    "What are the key training techniques described in this paper?",
    # COMPARISON
    "Compare the harmlessness and helpfulness objectives in the paper.",
    # HIERARCHICAL
    "What are the main sections and their subtopics?",
    # TEMPORAL (baseline can't really do this, but ask anyway for fairness)
    "How did the approach evolve from earlier methods?",
]


if __name__ == "__main__":
    pdf = sys.argv[1] if len(sys.argv) > 1 else "/home/ubuntu/git/forks/claude-cookbooks-daniela-fork/misc/data/Constitutional AI.pdf"
    run_baseline_rag(pdf, COMPARISON_QUESTIONS)
