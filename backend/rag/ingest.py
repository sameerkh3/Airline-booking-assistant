"""
RAG ingestion pipeline for airline policy documents.

Reads policy markdown files from backend/data/policies/, splits them into
section-level chunks (one chunk per ## heading), derives metadata, embeds
with sentence-transformers, and persists to a local FAISS index.

Note: ChromaDB (originally planned) does not support Python 3.14 due to a
pydantic v1 dependency. FAISS is used instead, as permitted by PRD §10.

Persistence layout (under backend/rag_store/):
    index.faiss    — FAISS flat-IP index (L2-normalised vectors → cosine sim)
    metadata.json  — list of chunk metadata dicts, indexed in the same order
    texts.json     — list of raw chunk texts, indexed in the same order

Run from the backend/ directory:
    python -m rag.ingest
"""

import json
import re
import uuid
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).parent.parent          # backend/
POLICIES_DIR = BACKEND_DIR / "data" / "policies"
STORE_DIR = BACKEND_DIR / "rag_store"
INDEX_PATH = STORE_DIR / "index.faiss"
META_PATH = STORE_DIR / "metadata.json"
TEXTS_PATH = STORE_DIR / "texts.json"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------

# Map filename stem → airline identifier (snake_case, matches PRD §8)
AIRLINE_FROM_STEM: dict[str, str] = {
    "emirates": "emirates",
    "qatar_airways": "qatar_airways",
    "pia": "pia",
}

# Keywords in section headings → policy_type label
POLICY_TYPE_KEYWORDS: list[tuple[list[str], str]] = [
    (["baggage", "allowance", "excess", "sports", "special"], "baggage"),
    (["cancellation", "cancel", "refund", "no-show", "no show"], "cancellation"),
    (["check-in", "check in", "online check"], "check_in"),
]

# Keywords in section headings → cabin_class label
CABIN_CLASS_KEYWORDS: list[tuple[list[str], str]] = [
    (["first class", "first"], "first"),
    (["business class", "business"], "business"),
    (["economy class", "economy"], "economy"),
]


def _derive_policy_type(heading: str) -> str:
    """Infer policy_type from a section heading string."""
    lower = heading.lower()
    for keywords, label in POLICY_TYPE_KEYWORDS:
        if any(kw in lower for kw in keywords):
            return label
    return "general"


def _derive_cabin_class(heading: str) -> str:
    """Infer cabin_class from a section heading string, or 'all' if not specific."""
    lower = heading.lower()
    for keywords, label in CABIN_CLASS_KEYWORDS:
        if any(kw in lower for kw in keywords):
            return label
    return "all"


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_markdown(text: str) -> list[tuple[str, str]]:
    """
    Split markdown on ## headings.

    Returns a list of (heading, full_chunk_text) tuples where full_chunk_text
    includes the heading line followed by its body paragraphs.
    """
    pattern = re.compile(r"(?=^## .+)", re.MULTILINE)
    raw_sections = pattern.split(text)

    chunks: list[tuple[str, str]] = []
    for section in raw_sections:
        section = section.strip()
        if not section:
            continue
        lines = section.splitlines()
        heading = lines[0].lstrip("# ").strip()
        chunks.append((heading, section))

    return chunks


# ---------------------------------------------------------------------------
# Main ingestion
# ---------------------------------------------------------------------------

def ingest() -> None:
    """Load policy documents, chunk, embed, and save FAISS index + metadata."""

    print(f"Loading embedding model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)

    STORE_DIR.mkdir(parents=True, exist_ok=True)

    md_files = sorted(POLICIES_DIR.glob("*.md"))
    if not md_files:
        raise FileNotFoundError(f"No .md files found in {POLICIES_DIR}")

    all_texts: list[str] = []
    all_meta: list[dict] = []

    for md_path in md_files:
        stem = md_path.stem
        airline = AIRLINE_FROM_STEM.get(stem, stem)

        text = md_path.read_text(encoding="utf-8")
        chunks = chunk_markdown(text)

        for heading, chunk_text in chunks:
            all_texts.append(chunk_text)
            all_meta.append({
                "id": str(uuid.uuid4()),
                "airline": airline,
                "policy_type": _derive_policy_type(heading),
                "cabin_class": _derive_cabin_class(heading),
                "source_file": md_path.name,
                "heading": heading,
            })

        print(f"  {airline}: {len(chunks)} chunks")

    print(f"\nEmbedding {len(all_texts)} chunks...")
    embeddings = model.encode(
        all_texts,
        show_progress_bar=True,
        normalize_embeddings=True,   # L2-norm → inner product == cosine similarity
    )

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)           # inner product index
    index.add(embeddings.astype(np.float32))  # type: ignore[arg-type]

    faiss.write_index(index, str(INDEX_PATH))
    META_PATH.write_text(json.dumps(all_meta, indent=2), encoding="utf-8")
    TEXTS_PATH.write_text(json.dumps(all_texts, indent=2), encoding="utf-8")

    print(f"\nDone.")
    print(f"  Index  → {INDEX_PATH}")
    print(f"  Meta   → {META_PATH}")
    print(f"  Texts  → {TEXTS_PATH}")
    print(f"  Total chunks: {len(all_meta)}")


if __name__ == "__main__":
    ingest()
