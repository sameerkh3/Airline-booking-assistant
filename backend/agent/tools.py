"""
Anthropic tool schema definitions for the airline booking agent.

`TOOLS` is passed directly to `client.messages.create(tools=TOOLS)`.
The three tools defined here map 1-to-1 to the implementations in executor.py:
  - flight_search  → _flight_search()
  - rag_lookup     → _rag_lookup()
  - send_email     → _send_email_stub() [real MCP call wired in ABA-8]
"""

TOOLS: list[dict] = [
    {
        "name": "flight_search",
        "description": (
            "Search for available flights between two airports or cities. "
            "Returns a list of matching flights with airline, flight number, "
            "departure/arrival times, duration, stops, and price. "
            "Call this only when origin, destination, departure date, and trip type "
            "are all confirmed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {
                    "type": "string",
                    "description": (
                        "Origin airport IATA code (e.g. 'KHI') or city name "
                        "(e.g. 'Karachi'). Case-insensitive."
                    ),
                },
                "destination": {
                    "type": "string",
                    "description": (
                        "Destination airport IATA code (e.g. 'DXB') or city name "
                        "(e.g. 'Dubai'). Case-insensitive."
                    ),
                },
                "cabin_class": {
                    "type": "string",
                    "description": (
                        "Cabin class filter: 'Economy', 'Business', or 'First'. "
                        "Defaults to 'Economy' if not specified."
                    ),
                },
                "airline_preference": {
                    "type": "string",
                    "description": (
                        "Optional airline name filter (e.g. 'Emirates', 'PIA'). "
                        "If omitted, all airlines on the route are returned."
                    ),
                },
            },
            "required": ["origin", "destination"],
        },
    },
    {
        "name": "rag_lookup",
        "description": (
            "Look up airline policy information from the local knowledge base. "
            "Use this for ANY question about baggage allowances, cancellation fees, "
            "refund policies, check-in requirements, or other airline policies. "
            "Never answer policy questions from memory — always call this tool first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": (
                        "The user's policy question in natural language, "
                        "e.g. 'What is the baggage allowance for Emirates economy?'"
                    ),
                },
                "airline": {
                    "type": "string",
                    "description": (
                        "Optional airline name to narrow the search "
                        "(e.g. 'Emirates', 'Qatar Airways', 'PIA'). "
                        "Omit to search across all airlines."
                    ),
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "send_email",
        "description": (
            "Send a formatted HTML email containing flight details to the user. "
            "ONLY call this tool after the user has given explicit confirmation. "
            "Never send speculatively."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address (e.g. 'user@example.com').",
                },
                "subject": {
                    "type": "string",
                    "description": (
                        "Email subject line, e.g. "
                        "'Your Flight Options — KHI to DXB, March 15'."
                    ),
                },
                "body_html": {
                    "type": "string",
                    "description": (
                        "Full HTML email body. Must include a header, greeting, "
                        "flight results table, route summary, and disclaimer footer."
                    ),
                },
            },
            "required": ["to", "subject", "body_html"],
        },
    },
]
