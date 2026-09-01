from typing import Literal

from pydantic import BaseModel, Field


class TestCase(BaseModel):
    """A suggested test idea produced by the Analyst agent.

    Precise enough that another agent (or a human) could turn it into
    Playwright code without having to guess anything.
    """

    id: str = Field(description="Short unique identifier, e.g. TC-001")
    title: str
    description: str
    steps: list[str] = Field(description="Numbered steps, plain language")
    expected_result: str
    priority: Literal["high", "medium", "low"]


class TestCaseList(BaseModel):
    """Structured output format expected from the Analyst agent."""

    test_cases: list[TestCase]
    coverage_judged_sufficient: bool = Field(
        description=(
            "The Analyst self-assesses: do these cases reasonably cover "
            "the given specification? Used by the Supervisor to decide "
            "whether to go back to the Analyst later."
        )
    )
