"""
Agent executor — stub implementation (ABA-5).

This module exposes run_agent(), which is called by main.py for every chat
request. The stub simply echoes back the user's message so the FastAPI server
is immediately runnable and end-to-end testable before the real agentic loop
is wired up in ABA-6.

ABA-6 will replace the body of run_agent() with the full Anthropic tool-use
loop (flight_search, rag_lookup, send_email).
"""


def run_agent(message: str, history: list[dict]) -> tuple[str, list[str]]:
    """
    Process a user message and return the agent's reply with reasoning trace.

    Args:
        message: The latest user message.
        history: Conversation history as a list of {"role": ..., "content": ...}
                 dicts (not yet used by this stub).

    Returns:
        A tuple of:
            reply     — the assistant's response string
            reasoning — list of reasoning/tool-call step strings for the UI panel
    """
    reply = f"[stub] You said: {message}"
    reasoning = ["stub reasoning step — agent not yet implemented (ABA-6)"]
    return reply, reasoning
