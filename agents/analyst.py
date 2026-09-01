"""Analyst agent: natural-language specification -> suggested test ideas.

Since the pivot, these test cases are NEVER executed automatically — the
Executor runs the real existing suite, independently of what the Analyst
proposes here. Its role becomes: spotting coverage angles a human may not
have added to the real suite yet, to be validated and written by hand
before any addition — never generated code executed without review.

It knows the REAL list of existing tests (via list_available_tests, the
same function that feeds the checkboxes in the interface) so it never
re-suggests an idea that's already covered — without that, it suggests
blindly and can ask for what already exists.
"""

import anthropic

from agents.executor import list_available_tests
from orchestrator.state import QAOrchestratorState
from schemas.test_case import TestCaseList

MODEL = "claude-opus-5"

ANALYST_SYSTEM_PROMPT = """You are the Analyst agent of a QA automation \
team. You are given the REAL list of tests that already exist in the \
suite, and a specification or user story.

Mandatory rule: NEVER suggest an idea already covered by an existing test \
listed below — always check before proposing. Test names are explicit \
(e.g. test_homepage_displays_all_collections): use them to infer what is \
already verified, not just the file name.

You propose a list of NEW test ideas (nominal path AND at least one edge \
or negative case, not already covered) — these are suggestions meant to \
be read and validated by a human, never executed automatically. If the \
specification is already fully covered by existing tests, return an empty \
list rather than forcing a redundant suggestion. Also honestly assess \
whether the suggested coverage (existing + new) seems sufficient relative \
to the specification."""


def _existing_tests_summary() -> str:
    try:
        tests = list_available_tests()
    except Exception:  # noqa: BLE001 — graceful degradation, no spec-less Analyst
        return "(list unavailable — cannot check for duplicates)"

    if not tests:
        return "(no existing tests found)"
    return "\n".join(f"- {t}" for t in tests)


def analyst_node(state: QAOrchestratorState) -> QAOrchestratorState:
    client = anthropic.Anthropic()

    response = client.messages.parse(
        model=MODEL,
        max_tokens=8192,
        system=[
            {
                "type": "text",
                "text": ANALYST_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    f"Tests already existing in the suite:\n\n{_existing_tests_summary()}\n\n"
                    f"Specification:\n\n{state['specification']}"
                ),
            }
        ],
        output_format=TestCaseList,
    )

    result = response.parsed_output

    return {
        **state,
        "test_cases": result.test_cases,
        "coverage_judged_sufficient": result.coverage_judged_sufficient,
        "messages": [
            {
                "role": "assistant",
                "content": f"[Analyst] {len(result.test_cases)} NEW idea(s) suggested "
                f"(not already covered) (coverage judged sufficient: "
                f"{result.coverage_judged_sufficient}).",
            }
        ],
    }
