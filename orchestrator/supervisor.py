"""The Supervisor node: decides, on each turn, which agent should act next.

Uses the Claude API's Structured Outputs (`messages.parse` + a Pydantic
model) rather than tool-use or free text — we want ONE reliable decision
among 5 values, not a function call with side effects nor text to parse by
hand.
"""

from typing import Literal

import anthropic
from pydantic import BaseModel

from orchestrator.state import QAOrchestratorState

MODEL = "claude-opus-5"

SUPERVISOR_SYSTEM_PROMPT = """You are the supervisor of a QA automation \
agent team. You do NO work yourself — you only decide which agent should \
act next, based on the current state.

Available agents:
- "analyst": proposes suggested test ideas from a specification (never
  executed automatically). Choose ONLY if a specification was provided
  (otherwise there is nothing to analyze — go straight to the executor)
  AND no ideas exist yet, OR the existing ideas were judged insufficient
  by the Analyst itself (coverage_judged_sufficient = false) AND they have
  not already been regenerated once (check the message log to verify).
- "executor": runs the REAL existing Playwright suite (no code
  generation). Choose if no execution results exist yet, regardless of the
  state of the Analyst's ideas.
- "triage": categorizes every real failure AND every test that needed a
  retry (product bug / brittle test / flaky / environment). Choose if
  execution results exist, at least one test failed OR at least one test
  needed a rerun to pass, and no triage has been done yet.
- "reporter": compiles everything into a final report. Choose if
  execution results exist AND (no failure/rerun, OR triage is already
  done), and no report has been written yet.
- "FINISH": choose only if a final report already exists.

NEVER choose an agent whose work for this turn is already done — base your
decision strictly on what is missing from the given state. When in doubt
between looping back to the Analyst and moving on to the Executor, loop
back at most once to avoid an infinite loop."""


class SupervisorDecision(BaseModel):
    next_agent: Literal["analyst", "executor", "triage", "reporter", "FINISH"]
    reasoning: str


def _summarize_state(state: QAOrchestratorState) -> str:
    already_looped_back = any(
        "loop" in str(getattr(m, "content", m)).lower()
        for m in state.get("messages", [])
    )
    execution_results = state.get("execution_results") or []
    has_failures = any(not r.passed for r in execution_results)
    has_reruns = any(r.reruns > 0 for r in execution_results)

    return (
        f"Specification provided: {'yes' if state.get('specification') else 'no'}\n"
        f"Number of ideas suggested by the Analyst: {len(state.get('test_cases') or [])}\n"
        f"Coverage judged sufficient by the Analyst: "
        f"{state.get('coverage_judged_sufficient')}\n"
        f"Number of real execution results: {len(execution_results)}\n"
        f"At least one real failure: {has_failures}\n"
        f"At least one test needed a rerun: {has_reruns}\n"
        f"Triage already done: {'yes' if state.get('triage') else 'no (or nothing to categorize)'}\n"
        f"Final report already generated: {'yes' if state.get('report') else 'no'}\n"
        f"Already looped back to the Analyst: {already_looped_back}\n"
    )


def supervisor_node(state: QAOrchestratorState) -> QAOrchestratorState:
    client = anthropic.Anthropic()

    response = client.messages.parse(
        model=MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SUPERVISOR_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": f"Current state:\n\n{_summarize_state(state)}\n"
                "Which agent should act now?",
            }
        ],
        output_format=SupervisorDecision,
    )

    decision = response.parsed_output

    return {
        **state,
        "next_agent": decision.next_agent,
        "messages": [
            {
                "role": "assistant",
                "content": f"[Supervisor] -> {decision.next_agent} ({decision.reasoning})",
            }
        ],
    }


def route_from_supervisor(state: QAOrchestratorState) -> str:
    return state["next_agent"]
