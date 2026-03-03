"""
Tool implementations for the airline booking agent.

Each function maps 1-to-1 to a tool schema in agent/tools.py:
  - _flight_search()      real flight search via SerpAPI (mock fallback via USE_MOCK_FLIGHTS)
  - _rag_lookup()         calls rag.retriever.query_policy()
  - _send_email_async()   async MCP call via the custom ABA MCP server (mcp-server/)
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

from flights.serpapi import search_flights as serpapi_search
from rag.retriever import query_policy

logger = logging.getLogger(__name__)

MOCK_FLIGHTS_PATH = Path(__file__).parent.parent / "data" / "mock_flights.json"

# ---------------------------------------------------------------------------
# Mock flights cache — loaded once on first call when USE_MOCK_FLIGHTS=true
# ---------------------------------------------------------------------------
_flights: list[dict] | None = None


def _load_mock_flights() -> list[dict] | None:
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


def _search_mock_flights(
    origin: str,
    destination: str,
    cabin_class: str,
    airline_preference: str | None,
) -> list[dict]:
    """Filter mock_flights.json and return matching flight dicts."""
    flights = _load_mock_flights()
    if flights is None:
        return []

    origin_lower = origin.strip().lower()
    dest_lower = destination.strip().lower()
    cabin_lower = cabin_class.strip().lower()
    airline_lower = airline_preference.strip().lower() if airline_preference else None

    results = []
    for f in flights:
        origin_match = (
            f["origin"].lower() == origin_lower
            or f["origin_city"].lower() == origin_lower
        )
        dest_match = (
            f["destination"].lower() == dest_lower
            or f["destination_city"].lower() == dest_lower
        )
        cabin_match = f["cabin_class"].lower() == cabin_lower
        airline_match = airline_lower is None or airline_lower in f["airline"].lower()

        if origin_match and dest_match and cabin_match and airline_match:
            results.append(f)

    return results[:5]


# ---------------------------------------------------------------------------
# Tool: flight_search
# ---------------------------------------------------------------------------

def _flight_search(
    origin: str,
    destination: str,
    departure_date: str = "",
    cabin_class: str = "Economy",
    airline_preference: str | None = None,
) -> str:
    """
    Search for flights and return a markdown table of results.

    When USE_MOCK_FLIGHTS=true: filters mock_flights.json (Phase 1 fallback).
    Otherwise: calls SerpAPI Google Flights for real-time data (Phase 2).

    Matching logic for mock path:
      - origin/destination matched against both IATA code and city name
      - cabin_class matched case-insensitively (default Economy)
      - airline_preference filters by partial airline name match

    Returns a markdown table or a descriptive "no flights found" message.
    """
    use_mock = os.environ.get("USE_MOCK_FLIGHTS", "false").strip().lower() == "true"

    if use_mock:
        # --- Mock path ---
        results = _search_mock_flights(origin, destination, cabin_class, airline_preference)
        if not results:
            return (
                f"No flights found from **{origin}** to **{destination}** "
                f"in {cabin_class} class"
                + (f" with {airline_preference}" if airline_preference else "")
                + "."
            )
        # Derive route label from mock data (includes city names)
        first = results[0]
        route_str = (
            f"{first['origin_city']} ({first['origin']}) → "
            f"{first['destination_city']} ({first['destination']})"
        )
    else:
        # --- Real API path (SerpAPI) ---
        if not departure_date:
            return "Please provide a departure date so I can search for available flights."

        results = serpapi_search(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            cabin_class=cabin_class,
            airline_preference=airline_preference,
        )

        # serpapi_search returns a string on error
        if isinstance(results, str):
            return results

        if not results:
            return (
                f"No flights found from **{origin}** to **{destination}** "
                f"on {departure_date} in {cabin_class} class"
                + (f" with {airline_preference}" if airline_preference else "")
                + ". Try a different date or cabin class."
            )

        route_str = f"{origin.upper()} → {destination.upper()}"

    # Build markdown table — same format for both paths
    lines = [
        "| Airline | Flight | Departure | Arrival | Duration | Stops | Price (USD) |",
        "|---------|--------|-----------|---------|----------|-------|-------------|",
    ]
    for r in results:
        arrival_note = (
            f"{r['arrival_time']} (+1)" if r.get("date_offset", 0) == 1 else r["arrival_time"]
        )
        lines.append(
            f"| {r['airline']} | {r['flight_number']} | {r['departure_time']} "
            f"| {arrival_note} | {r['duration']} | {r['stops']} | ${r['price_usd']} |"
        )

    header = f"Found **{len(results)}** flight(s) for {route_str} · {cabin_class} class:\n\n"
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
    Send an email via the custom ABA MCP server's send_email tool.

    Connects to the MCP server over streamable-HTTP (URL from MCP_SERVER_URL
    env var, e.g. http://localhost:8001/mcp), calls the send_email tool, and
    returns a status string.

    The custom MCP server handles HTML templating internally, so body_html is
    passed as-is (the agent-generated flight table HTML fragment).
    """
    mcp_url = os.environ.get("MCP_SERVER_URL")
    if not mcp_url:
        return "Email could not be sent: MCP_SERVER_URL is not configured."

    try:
        async with streamablehttp_client(mcp_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "send_email",
                    arguments={
                        "to": to,
                        "subject": subject,
                        "body_html": body_html,
                    },
                )

        # MCP tool returns errors as content strings, not exceptions.
        # Check isError flag and surface the error message if set.
        if result.isError:
            error_text = result.content[0].text if result.content else "unknown error"
            logger.error("send_email MCP tool error: %s", error_text)
            return f"Failed to send email: {error_text}"

        # Also check if the success message itself contains a failure indication
        # (defensive: MCP server returns descriptive error strings on SMTP failure)
        result_text = result.content[0].text if result.content else ""
        if result_text.startswith("Email could not be sent"):
            logger.error("send_email SMTP failure: %s", result_text)
            return result_text

        logger.info("send_email succeeded | to=%s | subject=%s", to, subject)
        return f"Email successfully sent to **{to}** with subject: \"{subject}\"."
    except Exception as exc:
        logger.error("send_email failed: %s", exc)
        return f"Failed to send email: {exc}"


def _send_email(to: str, subject: str, body_html: str) -> str:
    """
    Sync bridge around _send_email_async for use in the sync agentic loop.

    Uses asyncio.run() to call the async MCP client. Valid because the app
    runs in a single-worker sync uvicorn context with no outer event loop.
    """
    return asyncio.run(_send_email_async(to, subject, body_html))
