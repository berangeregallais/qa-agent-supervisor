"""Triage agent: categorizes real failures and proven flaky tests.

Two distinct mechanisms, deliberately separated:
1. A test that failed then passed within the same run (reruns > 0, passed)
   is flaky by DIRECT PROOF — no LLM call is needed, or even desirable:
   guessing what we already know for certain would add nothing and cost an
   API call for no reason.
2. A test still failing after all available reruns needs real
   interpretation (product bug? brittle test? environment?) — only then do
   we ask Claude.
"""

import anthropic

from orchestrator.state import QAOrchestratorState
from schemas.triage import TriageEntry, TriageResult

MODEL = "claude-opus-5"

TRIAGE_SYSTEM_PROMPT = """You are the Triage agent of a QA automation \
team. For each failing test, determine the most likely category:
- "product_bug": a real defect in the tested application.
- "brittle_test": a locator or assertion broken by a legitimate UI change
  — not a real bug, the test needs to be fixed.
- "flaky": a probably intermittent failure despite persisting on this run
  (e.g. a network/timing dependency that simply had bad luck on every
  attempt).
- "environment": network outage, unavailable service, quota — unrelated
  to the code under test or the application.

Give a confidence score between 0 and 1 and justify your decision in one \
sentence, based solely on the provided error message. Be honest: when in \
doubt, a low confidence score is better than false certainty."""


def triage_node(state: QAOrchestratorState) -> QAOrchestratorState:
    results = state["execution_results"]

    # 1. Direct proof, no LLM needed.
    recovered_flaky = [r for r in results if r.passed and r.reruns > 0]
    entries: list[TriageEntry] = [
        TriageEntry(
            test_id=r.test_id,
            category="flaky",
            confidence=1.0,
            justification=(
                f"Failed {r.reruns} time(s) before passing, within the same run: "
                "empirically proven flakiness, not a guess."
            ),
        )
        for r in recovered_flaky
    ]

    # 2. Persistent failures: judgment required.
    still_failing = [r for r in results if not r.passed]
    if still_failing:
        client = anthropic.Anthropic()
        failures_summary = "\n\n".join(
            f"- {r.test_id} (failed {r.reruns + 1} time(s) total, never passed)\n"
            f"  Error message: {r.error_message[:800]}"
            for r in still_failing
        )

        response = client.messages.parse(
            model=MODEL,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": TRIAGE_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {"role": "user", "content": f"Persistent failures to categorize:\n\n{failures_summary}"}
            ],
            output_format=TriageResult,
        )
        entries.extend(response.parsed_output.entries)

    return {
        **state,
        "triage": entries,
        "messages": [
            {
                "role": "assistant",
                "content": f"[Triage] {len(recovered_flaky)} flaky proven by rerun, "
                f"{len(still_failing)} persistent failure(s) categorized by analysis.",
            }
        ],
    }
