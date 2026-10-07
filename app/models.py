from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)


class QueryPlan(BaseModel):
    """Safe intermediate representation produced by GenAI or fallback parsing."""

    sql: str
    interpretation: str
    confidence: float = Field(ge=0, le=1)
    assumptions: list[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    query: str
    generated_logic: str
    result: Any
    confidence_score: float
    explanation: str
    assumptions: list[str] = Field(default_factory=list)
