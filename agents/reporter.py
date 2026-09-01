"""Reporter agent: real results + triage + suggestions -> final report."""

import anthropic

from orchestrator.state import QAOrchestratorState
from schemas.report import Report

MODEL = "claude-opus-5"

REPORTER_SYSTEM_PROMPT = """You are the Reporter agent of a QA automation \
team. You receive three sources, never to be mixed:
1. REAL execution results from the real test suite (what actually
   happened).
2. Triage of real failures, with a category and confidence score for
   each (product bug / brittle test / flaky / environment).
3. Test ideas SUGGESTED by the Analyst, never executed — present them
   only as ideas to validate by a human, never as results.

Write TWO distinct summaries, for two different readers — never reuse one
for the other:
- `summary`: developer/QA level. Technical details useful to act on
  (which test, which triage category, which fix angle).
- `executive_summary`: 3 sentences MAXIMUM, with absolutely no technical
  jargon (never a test name, a stack trace, or a term like "locator" or
  "flaky"). Answers only three questions: is everything broadly fine? is
  there a risk that justifies blocking a production release? what is the
  trend in one sentence, if that information is available.

For each real failure in `details`, a concrete recommendation that takes
its triage category into account (don't recommend the same thing for a
product bug and a brittle test). Put the Analyst's suggestions in
coverage_suggestions, never in the execution details."""


def reporter_node(state: QAOrchestratorState) -> QAOrchestratorState:
    client = anthropic.Anthropic()

    triage_by_id = {t.test_id: t for t in (state.get("triage") or [])}

    results_summary = "\n\n".join(
        f"- {r.test_id} : {'PASS' if r.passed else 'FAIL'} ({r.duration_seconds:.2f}s)\n"
        f"  Message: {r.error_message[:400]}\n"
        + (
            f"  Triage: {triage_by_id[r.test_id].category} "
            f"(confidence {triage_by_id[r.test_id].confidence:.2f}) — "
            f"{triage_by_id[r.test_id].justification}"
            if not r.passed and r.test_id in triage_by_id
            else ""
        )
        for r in state["execution_results"]
    )

    suggestions = "\n".join(
        f"- {tc.title} : {tc.description}" for tc in (state.get("test_cases") or [])
    )

    response = client.messages.parse(
        model=MODEL,
        max_tokens=8192,
        system=[
            {
                "type": "text",
                "text": REPORTER_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    f"Real results and triage:\n\n{results_summary}\n\n"
                    f"Ideas suggested by the Analyst (unverified):\n\n{suggestions}"
                ),
            }
        ],
        output_format=Report,
    )

    report = response.parsed_output

    return {
        **state,
        "report": report,
        "messages": [{"role": "assistant", "content": "[Reporter] Final report generated."}],
    }
