# Airline Booking Assistant

A conversational AI assistant demonstrating agentic RAG capabilities for airline flight search and policy lookup. Built as a POC — **not a real booking system**.

**Core capabilities:**
- Natural language flight search (mocked data, Phase 1)
- RAG-based airline policy lookup (Emirates, Qatar Airways, PIA)
- Email flight results via Gmail MCP server

---

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.11+ |
| Node.js | 18+ |
| npm | 9+ |

---

## Setup

### 1. Clone and configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key — get it at [console.anthropic.com](https://console.anthropic.com/) |
| `GMAIL_EMAIL` | Gmail address that will send flight result emails |
| `GMAIL_APP_PASSWORD` | Gmail App Password (generate at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)) |
| `FRONTEND_URL` | Frontend dev server URL (default: `http://localhost:5173`) |

### 2. Backend

```bash
cd backend

# Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Populate the RAG vector store (run once before starting the server)
python -m rag.ingest

# Start the API server
uvicorn main:app --reload --port 8000
```

The backend runs at `http://localhost:8000`.

### 3. Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```

The frontend runs at `http://localhost:5173`.

---

## Project Structure

```
airline-booking-assitant/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── requirements.txt     # Python dependencies
│   ├── agent/
│   │   ├── system_prompt.py # Claude system prompt
│   │   ├── tools.py         # Tool schemas (flight_search, rag_lookup, send_email)
│   │   └── executor.py      # Agentic loop
│   ├── rag/
│   │   ├── ingest.py        # Vector store ingestion script
│   │   └── retriever.py     # ChromaDB query function
│   └── data/
│       ├── mock_flights.json # Mocked flight data (Phase 1)
│       └── policies/        # Airline policy markdown documents
├── frontend/
│   ├── package.json
│   └── src/                 # React components
├── .env.example             # Environment variable template
└── README.md
```

---

## How the RAG Vector Store Works

Policy documents for Emirates, Qatar Airways, and PIA are stored as markdown files in `backend/data/policies/`. Running `python -m rag.ingest` from the `backend/` directory reads these files, chunks them at paragraph level, embeds them with `sentence-transformers`, and stores them in a local ChromaDB instance (`backend/chroma_db/`).

The server must be restarted if you update policy documents and re-run the ingestion script.

---

## Disclaimer

This is a proof-of-concept application. Flight prices and availability are not real. Do not use for actual bookings.
