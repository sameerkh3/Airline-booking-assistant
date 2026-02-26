"""
RAG retrieval interface for airline policy queries.

Loads the persisted FAISS index, metadata, and texts once on module import,
then exposes a single query_policy() function used by the rag_lookup agent
tool (ABA-6).

Run from the backend/ directory for a smoke-test:
    python -m rag.retriever
"""

import json
import logging
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config (must match ingest.py)
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).parent.parent
STORE_DIR = BACKEND_DIR / "rag_store"
INDEX_PATH = STORE_DIR / "index.faiss"
META_PATH = STORE_DIR / "metadata.json"
TEXTS_PATH = STORE_DIR / "texts.json"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ---------------------------------------------------------------------------
# Module-level singletons — loaded once, reused across all requests
# ---------------------------------------------------------------------------
try:
    _model = SentenceTransformer(EMBEDDING_MODEL)
    _index = faiss.read_index(str(INDEX_PATH))
    _metadata: list[dict] = json.loads(META_PATH.read_text(encoding="utf-8"))
    _texts: list[str] = json.loads(TEXTS_PATH.read_text(encoding="utf-8"))
except FileNotFoundError as exc:
    raise RuntimeError(
        f"RAG store not found ({exc.filename}). Run: python -m rag.ingest"
    ) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def query_policy(question: str, n_results: int = 3) -> list[dict]:
    """
    Retrieve the top-k policy chunks most relevant to the given question.

    Args:
        question:  Natural-language policy question from the user.
        n_results: Number of chunks to return (default 3).

    Returns:
        List of dicts, each containing:
            - text        (str)   full chunk text
            - airline     (str)   e.g. "emirates"
            - policy_type (str)   e.g. "baggage" | "cancellation" | "check_in"
            - cabin_class (str)   e.g. "economy" | "business" | "first" | "all"
            - score       (float) cosine similarity score (higher = more relevant)
    """
    query_vec = _model.encode([question], normalize_embeddings=True).astype(np.float32)
    scores, indices = _index.search(query_vec, n_results)

    chunks: list[dict] = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:           # FAISS returns -1 for missing results
            continue
        meta = _metadata[idx]
        chunks.append({
            "text": _texts[idx],
            "airline": meta.get("airline", "unknown"),
            "policy_type": meta.get("policy_type", "general"),
            "cabin_class": meta.get("cabin_class", "all"),
            "score": round(float(score), 4),
        })

    return chunks


# ---------------------------------------------------------------------------
# Smoke-test (run directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample_question = "What is Emirates economy baggage allowance?"
    print(f"Query: {sample_question}\n")
    results = query_policy(sample_question, n_results=3)

    for i, chunk in enumerate(results, 1):
        print(f"--- Result {i} ---")
        print(f"Airline     : {chunk['airline']}")
        print(f"Policy type : {chunk['policy_type']}")
        print(f"Cabin class : {chunk['cabin_class']}")
        print(f"Score       : {chunk['score']}")
        print(f"Text snippet: {chunk['text'][:200]}...")
        print()

    # Assertion for CI / manual verification
    emirates_results = [r for r in results if r["airline"] == "emirates"]
    assert len(emirates_results) >= 1, "Expected at least 1 Emirates chunk in results"
    print("Smoke-test passed: Emirates chunk found in results.")
