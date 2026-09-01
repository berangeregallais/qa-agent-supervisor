from typing import Literal, Optional

from pydantic import BaseModel


class ReportEntry(BaseModel):
    test_id: str
    title: str
    status: Literal["passed", "failed"]
    category: Optional[str] = None  # set for failures, via the Triage agent
    comment: str


class Report(BaseModel):
    """The final report, produced by the Reporter agent.

    Two distinct summaries, for two different readers — never a single
    text trying to serve both at once:
    - `summary`: developer/QA level, technical details useful to act on.
    - `executive_summary`: 3 sentences max, status/risk/decision oriented,
      no technical jargon — what you'd show someone who needs to decide
      whether to ship, not how to fix a test.
    """

    summary: str
    executive_summary: str
    total: int
    passed: int
    failed: int
    details: list[ReportEntry]
    # Ideas from the Analyst not covered by the current suite — never
    # executed or verified, to be validated by a human before any real
    # addition.
    coverage_suggestions: list[str] = []
    recommendations: list[str]
