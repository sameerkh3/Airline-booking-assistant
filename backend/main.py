"""
FastAPI application entry point.

Run from the backend/ directory:
    uvicorn main:app --reload --port 8000

Endpoints:
    POST /api/chat   — send a message, receive assistant reply + reasoning trace
    POST /api/reset  — clear in-memory conversation history
    GET  /health     — liveness check
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.executor import run_agent
from schemas import ChatRequest, ChatResponse, ResetResponse

# Load .env from the backend/ directory (or project root if not found there)
load_dotenv()

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

    reply, reasoning = run_agent(request.message, _history)

    _history.append({"role": "assistant", "content": reply})

    return ChatResponse(reply=reply, reasoning=reasoning)


@app.post("/api/reset", response_model=ResetResponse)
def reset() -> ResetResponse:
    """Clear the in-memory conversation history."""
    _history.clear()
    return ResetResponse(status="ok")
