from typing import Annotated, Literal, Optional

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from schemas.execution_result import ExecutionResult
from schemas.report import Report
from schemas.test_case import TestCase
from schemas.triage import TriageEntry

NextAgent = Literal["analyst", "executor", "triage", "reporter", "FINISH"]


class QAOrchestratorState(TypedDict):
    """Shared state, passed and enriched by every node of the graph.

    Two categories of fields, deliberately separated:
    - work data (Pydantic-typed), read/written by agents to do their job
      — the "what".
    - `messages`, a plain-language trace log (Supervisor reasoning,
      per-agent activity summary) — never consumed programmatically by
      agents, only for human observability/debugging. Never store a value
      an agent needs to function in here — that should always be a
      dedicated typed field.
    """

    # System input
    specification: str  # may be empty: in that case, the Analyst is skipped
    selected_tests: Optional[list[str]]  # None/empty = the whole suite

    # Analyst suggestions — never executed, purely indicative (see
    # agents/analyst.py). Field names kept for schema stability, but their
    # role changed after the pivot.
    test_cases: list[TestCase]
    coverage_judged_sufficient: Optional[bool]

    # REAL results from the maisoncarmenta-qa suite (agents/executor.py)
    execution_results: list[ExecutionResult]

    # Categorization of real failures (agents/triage.py)
    triage: list[TriageEntry]

    report: Optional[Report]

    # Routing decided by the Supervisor on each turn
    next_agent: NextAgent

    # Trace log (accumulated automatically by LangGraph via add_messages)
    messages: Annotated[list, add_messages]

    # --- Reserved for V2+, not populated by any current agent ---
    test_data_handles: Optional[list[str]]  # Data agent: identifiers of
    # test data created, to clean up at the end of the run
