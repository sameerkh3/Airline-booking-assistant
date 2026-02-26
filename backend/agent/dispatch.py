"""
Tool dispatcher for the airline booking agent.

Routes tool_use blocks from the Anthropic API to the correct implementation
in tools_impl.py.
"""

import logging

from agent.tools_impl import _flight_search, _rag_lookup, _send_email

logger = logging.getLogger(__name__)


def dispatch_tool(tool_name: str, tool_input: dict) -> str:
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
        return _send_email(
            to=tool_input["to"],
            subject=tool_input["subject"],
            body_html=tool_input["body_html"],
        )
    else:
        logger.warning("Unknown tool called: %s", tool_name)
        return f"Unknown tool: {tool_name}"
