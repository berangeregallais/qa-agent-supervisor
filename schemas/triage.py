from typing import Literal

from pydantic import BaseModel, Field


class TriageEntry(BaseModel):
    """Categorization of a real failure by the Triage agent."""

    test_id: str
    category: Literal["product_bug", "brittle_test", "flaky", "environment"]
    confidence: float = Field(ge=0, le=1, description="0 = no confidence, 1 = full confidence")
    justification: str


class TriageResult(BaseModel):
    """Structured output format expected from the Triage agent."""

    entries: list[TriageEntry]
