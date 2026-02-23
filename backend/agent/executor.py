"""
Agent executor — full Anthropic tool-use agentic loop (ABA-6).

Replaces the ABA-5 stub. Exposes run_agent() which is called by main.py
for every /api/chat request.

Flow per turn:
    1. Build messages list from history + new user message
    2. Call Claude with system prompt and tool schemas
    3. If stop_reason == "tool_use": dispatch each tool, append tool_results, loop
    4. If stop_reason == "end_turn": extract final text, return (reply, reasoning)

Tool implementations:
    - _flight_search()    filters backend/data/mock_flights.json
    - _rag_lookup()       calls rag.retriever.query_policy()
    - _send_email_stub()  logs and stubs; real MCP call wired in ABA-8
"""

import json
import logging
import os
from pathlib import Path

import anthropic

from agent.system_prompt import SYSTEM_PROMPT
from agent.tools import TOOLS
from rag.retriever import query_policy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MODEL = "claude-haiku-3-5-20241022"
MAX_TOKENS = 4096
MOCK_FLIGHTS_PATH = Path(__file__).parent.parent / "data" / "mock_flights.json"

# ---------------------------------------------------------------------------
# Anthropic client — initialised once at module import
# (reads ANTHROPIC_API_KEY from environment, loaded by main.py via dotenv)
# ---------------------------------------------------------------------------
_client = anthropic.Anthropic()


# ---------------------------------------------------------------------------
# Tool implementations
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
    flights = json.loads(MOCK_FLIGHTS_PATH.read_text(encoding="utf-8"))["flights"]

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

    route_str = f"{r['origin_city']} ({results[0]['origin']}) → {results[0]['destination_city']} ({results[0]['destination']})"
    header = f"Found **{len(rows)}** flight(s) for {route_str} · {cabin_class} class:\n\n"
    return header + "\n".join(lines)


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
        airline_label = chunk["airline"].replace("_", " ").title()
        policy_label = chunk["policy_type"].replace("_", " ").title()
        cabin_label = chunk["cabin_class"].replace("_", " ").title()
        parts.append(
            f"**[Source {i} — {airline_label} · {policy_label}"
            + (f" · {cabin_label}" if cabin_label != "All" else "")
            + f" (score: {chunk['score']})]**\n{chunk['text']}"
        )

    return "\n\n---\n\n".join(parts)


def _send_email_stub(to: str, subject: str, body_html: str) -> str:
    """
    Email stub — logs the call and returns success.

    The real MCP-based Gmail call is wired in ABA-8. This stub allows the
    full confirmation flow (display summary → ask → confirm → send) to work
    end-to-end even before the MCP server is integrated.
    """
    logger.info("send_email stub called | to=%s | subject=%s", to, subject)
    logger.debug("body_html length: %d chars", len(body_html))
    return f"Email successfully sent to **{to}** with subject: \"{subject}\"."


def _dispatch_tool(tool_name: str, tool_input: dict) -> str:
    """Route a tool_use block to the correct implementation."""
    if tool_name == "flight_search":
        return _flight_search(
            origin=tool_input["origin"],
            destination=tool_input["destination"],
            cabin_class=tool_input.get("cabin_class", "Economy"),
            airline_preference=tool_input.get("airline_preference"),
        )
    elif tool_name == "rag_lookup":
        return _rag_lookup(
            question=tool_input["question"],
            airline=tool_input.get("airline"),
        )
    elif tool_name == "send_email":
        return _send_email_stub(
            to=tool_input["to"],
            subject=tool_input["subject"],
            body_html=tool_input["body_html"],
        )
    else:
        return f"Unknown tool: {tool_name}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_agent(message: str, history: list[dict]) -> tuple[str, list[str]]:
    """
    Process a user message through the Anthropic tool-use agentic loop.

    Args:
        message: The latest user message (already appended to history by main.py).
        history: Full conversation history as list of {"role": ..., "content": ...}
                 dicts. The new user message is the last entry.

    Returns:
        A tuple of:
            reply     — the agent's final text response (shown in chat)
            reasoning — list of step strings for the reasoning panel (hidden by default)
    """
    reasoning: list[str] = []

    # Build the messages list from the full history (main.py has already appended
    # the new user message as the last entry before calling run_agent).
    messages = list(history)

    # Agentic loop — continues until Claude returns stop_reason == "end_turn"
    while True:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # ----------------------------------------------------------------
        # Capture assistant turn in reasoning trace
        # ----------------------------------------------------------------
        for block in response.content:
            if block.type == "text":
                reasoning.append(f"[assistant] {block.text[:500]}" + ("…" if len(block.text) > 500 else ""))
            elif block.type == "tool_use":
                reasoning.append(
                    f"[tool_call] {block.name}({json.dumps(block.input, ensure_ascii=False)})"
                )

        # ----------------------------------------------------------------
        # Terminal: model has finished responding
        # ----------------------------------------------------------------
        if response.stop_reason == "end_turn":
            # Extract the final text reply from the last assistant message
            final_text = ""
            for block in response.content:
                if block.type == "text":
                    final_text = block.text
                    break
            return final_text, reasoning

        # ----------------------------------------------------------------
        # Tool use: dispatch each tool call and collect results
        # ----------------------------------------------------------------
        if response.stop_reason == "tool_use":
            # Append the full assistant message (may contain text + tool_use blocks)
            messages.append({"role": "assistant", "content": response.content})

            # Build tool_result blocks for every tool_use in this response
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_output = _dispatch_tool(block.name, block.input)
                reasoning.append(f"[tool_result] {block.name} → {tool_output[:300]}" + ("…" if len(tool_output) > 300 else ""))

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": tool_output,
                })

            # Append the tool results as a user turn (Anthropic API convention)
            messages.append({"role": "user", "content": tool_results})
            # Loop: call Claude again with the tool results in context
            continue

        # ----------------------------------------------------------------
        # Unexpected stop reason — surface it rather than silently failing
        # ----------------------------------------------------------------
        logger.warning("Unexpected stop_reason: %s", response.stop_reason)
        return (
            "I encountered an unexpected issue. Please try again.",
            reasoning + [f"[error] Unexpected stop_reason: {response.stop_reason}"],
        )
