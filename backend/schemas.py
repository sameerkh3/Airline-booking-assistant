"""
Pydantic request/response schemas shared across the FastAPI application.
"""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    reasoning: list[str]


class ResetResponse(BaseModel):
    status: str
