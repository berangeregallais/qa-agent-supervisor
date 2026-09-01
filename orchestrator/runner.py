"""Reusable pipeline entry point — shared between the CLI (main.py) and the
web server (server.py), so the initial state is never built twice."""

import json
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from orchestrator.graph import build_graph
from orchestrator.state import QAOrchestratorState
from schemas.report import Report

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
LAST_RUN_PATH = REPORTS_DIR / "last-run.json"
HISTORY_PATH = REPORTS_DIR / "history.json"

# Files _reset_reports_dir must NEVER delete — they must survive across
# runs, including a cancelled or errored run.
_PERSISTENT_FILENAMES = {LAST_RUN_PATH.name, HISTORY_PATH.name}

MAX_HISTORY_ENTRIES = 50


def _reset_reports_dir() -> None:
    # Cleans up the previous run's artifacts (JUnit XML, rerun counter...)
    # without ever touching last-run.json or history.json: otherwise a
    # cancelled run (which never reaches _record_completed_run) would
    # erase the memory of every previous run without ever rebuilding it.
    # Real bug found while building the history feature.
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    for item in REPORTS_DIR.iterdir():
        if item.name in _PERSISTENT_FILENAMES:
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def _load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))


def get_history() -> list[dict]:
    """Returns past runs, most recent first."""
    return list(reversed(_load_history()))


def _record_completed_run(report: Report) -> None:
    """Records the run both as "last run" and in the history — a single
    call site to never do one without the other."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()

    LAST_RUN_PATH.write_text(json.dumps({"timestamp": timestamp}), encoding="utf-8")

    entries = _load_history()
    entries.append(
        {
            "timestamp": timestamp,
            "total": report.total,
            "passed": report.passed,
            "failed": report.failed,
            "summary": report.summary[:200],
        }
    )
    entries = entries[-MAX_HISTORY_ENTRIES:]  # avoid unbounded growth
    HISTORY_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def get_last_run_timestamp() -> Optional[str]:
    if not LAST_RUN_PATH.exists():
        return None
    return json.loads(LAST_RUN_PATH.read_text(encoding="utf-8")).get("timestamp")


def _initial_state(specification: str, selected_tests: Optional[list[str]]) -> QAOrchestratorState:
    return {
        "specification": specification,
        "selected_tests": selected_tests or [],
        "test_cases": [],
        "coverage_judged_sufficient": None,
        "execution_results": [],
        "triage": [],
        "report": None,
        "next_agent": "analyst",
        "messages": [],
        "test_data_handles": None,
    }


def run_pipeline(specification: str = "", selected_tests: Optional[list[str]] = None) -> Report:
    """Runs the full graph and returns the final report (CLI usage, not
    cancelable — see run_pipeline_cancelable for the web server usage)."""
    _reset_reports_dir()

    graph = build_graph()
    final_state = graph.invoke(
        _initial_state(specification, selected_tests), config={"recursion_limit": 25}
    )

    if final_state["report"] is None:
        raise RuntimeError("The pipeline stopped without producing a report.")

    _record_completed_run(final_state["report"])
    return final_state["report"]


def run_pipeline_cancelable(
    specification: str,
    selected_tests: Optional[list[str]],
    cancel_event: threading.Event,
) -> Optional[Report]:
    """Like run_pipeline, but stops between two graph steps if
    `cancel_event` is set during execution. Returns None if cancelled
    before a report could be produced.

    Accepted limitation: the CURRENT step is not interrupted instantly (an
    in-flight Claude call runs to completion, a few seconds at most) —
    only the next step is prevented from starting. The exception is the
    Executor, whose pytest subprocess can be killed directly (see
    agents/executor.cancel_current_execution), since it's the only step
    long enough for the wait to be annoying.
    """
    _reset_reports_dir()

    graph = build_graph()
    initial = _initial_state(specification, selected_tests)
    accumulated_state: dict = dict(initial)

    for step in graph.stream(initial, config={"recursion_limit": 25}):
        for node_output in step.values():
            accumulated_state.update(node_output)

        if cancel_event.is_set():
            return None

    report = accumulated_state.get("report")
    if report is not None:
        _record_completed_run(report)
    return report
