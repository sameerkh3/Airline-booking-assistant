"""
Tool implementations for the airline booking agent.

Each function maps 1-to-1 to a tool schema in agent/tools.py:
  - _flight_search()      filters backend/data/mock_flights.json
  - _rag_lookup()         calls rag.retriever.query_policy()
  - _send_email_async()   async MCP call via Zapier Gmail
  - _send_email()         sync bridge for use in the agentic loop
"""

import asyncio
import json
import logging
import os
from pathlib import Path

import anthropic  # noqa: F401 — keep for type consistency across agent package
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from agent.email_template import build_email_html
from rag.retriever import query_policy

logger = logging.getLogger(__name__)

MOCK_FLIGHTS_PATH = Path(__file__).parent.parent / "data" / "mock_flights.json"

# ---------------------------------------------------------------------------
# Flights cache — loaded once on first call, reused on subsequent calls
# ---------------------------------------------------------------------------
_flights: list[dict] | None = None


def _load_flights() -> list[dict] | None:
    """Load mock flights from disk once and cache in module-level variable."""
    global _flights
    if _flights is not None:
        return _flights
    try:
        _flights = json.loads(MOCK_FLIGHTS_PATH.read_text(encoding="utf-8"))["flights"]
        return _flights
    except (FileNotFoundError, json.JSONDecodeError):
        logger.exception("Failed to load mock_flights.json from %s", MOCK_FLIGHTS_PATH)
        return None


# ---------------------------------------------------------------------------
# Tool: flight_search
# ---------------------------------------------------------------------------

def _flight_search(
    origin: str,
    destination: str,
    cabin_class: str = "Economy",
    airline_preference: str | None = None,
) -> str:
    """
    Filter mock_flights.json and return a markdown table of matching flights.

    Matching logic:
      - origin and destination matched case-insensitively against both the
        IATA code field (e.g. "KHI") and the city name field (e.g. "Karachi")
      - cabin_class matched case-insensitively (default Economy)
      - airline_preference optionally filters by partial airline name match

    Returns a markdown table or a "no flights found" message.
    """
    flights = _load_flights()
    if flights is None:
        return "Flight data is temporarily unavailable."

    origin_lower = origin.strip().lower()
    dest_lower = destination.strip().lower()
    cabin_lower = cabin_class.strip().lower() if cabin_class else "economy"
    airline_lower = airline_preference.strip().lower() if airline_preference else None

    results = []
    for f in flights:
        # Origin match: IATA code or city name
        origin_match = (
            f["origin"].lower() == origin_lower
            or f["origin_city"].lower() == origin_lower
        )
        # Destination match: IATA code or city name
        dest_match = (
            f["destination"].lower() == dest_lower
            or f["destination_city"].lower() == dest_lower
        )
        # Cabin class match
        cabin_match = f["cabin_class"].lower() == cabin_lower
        # Airline preference (partial match)
        airline_match = (
            airline_lower is None
            or airline_lower in f["airline"].lower()
        )

        if origin_match and dest_match and cabin_match and airline_match:
            results.append(f)

    if not results:
        return (
            f"No flights found from **{origin}** to **{destination}** "
            f"in {cabin_class} class"
            + (f" with {airline_preference}" if airline_preference else "")
            + ". The mock dataset covers: JFK↔LHR, DXB↔LHR, KHI↔DXB, "
            "LHE↔LHR, ISB↔JED, JFK↔YYZ."
        )

    # Build markdown table (up to 5 results)
    rows = results[:5]
    lines = [
        "| Airline | Flight | Departure | Arrival | Duration | Stops | Price (USD) |",
        "|---------|--------|-----------|---------|----------|-------|-------------|",
    ]
    for r in rows:
        arrival_note = f"{r['arrival_time']} (+1)" if r.get("date_offset", 0) == 1 else r["arrival_time"]
        lines.append(
            f"| {r['airline']} | {r['flight_number']} | {r['departure_time']} "
            f"| {arrival_note} | {r['duration']} | {r['stops']} | ${r['price_usd']} |"
        )

    first = results[0]
    route_str = f"{first['origin_city']} ({first['origin']}) → {first['destination_city']} ({first['destination']})"
    header = f"Found **{len(rows)}** flight(s) for {route_str} · {cabin_class} class:\n\n"
    return header + "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: rag_lookup
# ---------------------------------------------------------------------------

def _rag_lookup(question: str, airline: str | None = None) -> str:
    """
    Query the FAISS policy vector store and return formatted results.

    Retrieves top-3 chunks. If `airline` is provided, it is appended to the
    question to bias the embedding search toward that airline's chunks.
    """
    # Bias the query toward the specified airline if provided
    query = f"{airline} {question}" if airline else question

    chunks = query_policy(query, n_results=3)

    if not chunks:
        return "No relevant policy information found in the knowledge base."

    parts = []
    for i, chunk in enumerate(chunks, 1):
        airline_label = chunk.get("airline", "unknown").replace("_", " ").title()
        policy_label = chunk.get("policy_type", "general").replace("_", " ").title()
        cabin_label = chunk.get("cabin_class", "all").replace("_", " ").title()
        parts.append(
            f"**[Source {i} — {airline_label} · {policy_label}"
            + (f" · {cabin_label}" if cabin_label != "All" else "")
            + f" (score: {chunk['score']})]**\n{chunk['text']}"
        )

    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Tool: send_email
# ---------------------------------------------------------------------------

async def _send_email_async(to: str, subject: str, body_html: str) -> str:
    """
    Send an email via the Zapier MCP gmail_send_email tool.

    Connects to the Zapier MCP server (URL from ZAPIER_MCP_URL env var),
    calls gmail_send_email with the HTML body, and returns a status string.
    """
    zapier_url = os.environ.get("ZAPIER_MCP_URL")
    if not zapier_url:
        return "Email could not be sent: ZAPIER_MCP_URL is not configured."

    # Wrap body_html in the full HTML email template
    full_html = build_email_html(subject, body_html)

    try:
        async with streamablehttp_client(zapier_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "gmail_send_email",
                    arguments={
                        "instructions": f"Send an email to {to} with subject '{subject}'",
                        "to": [to],
                        "subject": subject,
                        "body": full_html,
                        "body_type": "html",
                    },
                )
        logger.info("gmail_send_email succeeded | to=%s | subject=%s", to, subject)
        return f"Email successfully sent to **{to}** with subject: \"{subject}\"."
    except Exception as exc:
        logger.error("gmail_send_email failed: %s", exc)
        return f"Failed to send email: {exc}"


def _send_email(to: str, subject: str, body_html: str) -> str:
    """
    Sync bridge around _send_email_async for use in the sync agentic loop.

    Uses asyncio.run() to call the async Zapier MCP client. Valid because
    the app runs in a single-worker sync uvicorn context with no outer event loop.
    """
    return asyncio.run(_send_email_async(to, subject, body_html))
