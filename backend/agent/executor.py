"""
Agent executor — Anthropic tool-use agentic loop.

Exposes run_agent() which is called by main.py for every /api/chat request.

Flow per turn:
    1. Build messages list from history + new user message
    2. Call Claude with system prompt and tool schemas
    3. If stop_reason == "tool_use": dispatch each tool, append tool_results, loop
    4. If stop_reason == "end_turn": extract final text, return (reply, reasoning)

Tool implementations live in agent/tools_impl.py.
Tool routing lives in agent/dispatch.py.
"""

import json
import logging

import anthropic

from agent.dispatch import dispatch_tool
from agent.system_prompt import SYSTEM_PROMPT
from agent.tools import TOOLS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096

# Truncation limits for reasoning trace entries
REASONING_TEXT_LIMIT = 500
REASONING_TOOL_LIMIT = 300

# ---------------------------------------------------------------------------
# Anthropic client — initialised once at module import
# (reads ANTHROPIC_API_KEY from environment, loaded by main.py via dotenv)
# ---------------------------------------------------------------------------
_client = anthropic.Anthropic()


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
                reasoning.append(
                    f"[assistant] {block.text[:REASONING_TEXT_LIMIT]}"
                    + ("…" if len(block.text) > REASONING_TEXT_LIMIT else "")
                )
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

                tool_output = dispatch_tool(block.name, block.input)
                reasoning.append(
                    f"[tool_result] {block.name} → {tool_output[:REASONING_TOOL_LIMIT]}"
                    + ("…" if len(tool_output) > REASONING_TOOL_LIMIT else "")
                )

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
