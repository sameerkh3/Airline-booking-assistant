"""
FastAPI application entry point.

Run from the backend/ directory:
    uvicorn main:app --reload --port 8000

Endpoints:
    POST /api/chat   — send a message, receive assistant reply + reasoning trace
    POST /api/reset  — clear in-memory conversation history
    GET  /health     — liveness check
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env from repo root (one level above backend/) so that all env vars —
# including ANTHROPIC_API_KEY and ZAPIER_MCP_URL — are available regardless
# of which directory uvicorn is launched from.
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from agent.executor import run_agent  # noqa: E402
from schemas import ChatRequest, ChatResponse, ResetResponse  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory conversation history
# A single list is sufficient for this local POC (no multi-user sessions).
# Each entry is {"role": "user"|"assistant", "content": "<text>"}.
# ---------------------------------------------------------------------------
_history: list[dict] = []


# ---------------------------------------------------------------------------
# Lifespan: pre-warm the FAISS retriever so the first /api/chat isn't slow
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Importing retriever triggers module-level index load
    import rag.retriever  # noqa: F401
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Airline Booking Assistant API", lifespan=lifespan)

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """Liveness check."""
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """
    Process a user message through the agent and return the reply.

    Maintains server-side conversation history across turns.
    """
    _history.append({"role": "user", "content": request.message})

    try:
        reply, reasoning = run_agent(request.message, _history)
    except Exception:
        # Roll back the optimistically-appended user message so history stays clean
        _history.pop()
        logger.exception("run_agent failed for message: %.100s", request.message)
        return ChatResponse(reply="Something went wrong, please try again.", reasoning=[])

    _history.append({"role": "assistant", "content": reply})
    # Keep at most 40 messages (20 turns) to prevent unbounded memory growth
    _history[:] = _history[-40:]

    return ChatResponse(reply=reply, reasoning=reasoning)


@app.post("/api/reset", response_model=ResetResponse)
def reset() -> ResetResponse:
    """Clear the in-memory conversation history."""
    _history.clear()
    return ResetResponse(status="ok")
