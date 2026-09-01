"""Executor agent: runs the REAL Playwright suite of maisoncarmenta-qa.

Pivot from the V1 (which generated Playwright code on the fly): the
generated code did not consistently follow the Page Object Model and
produced more false failures (badly guessed locators) than real signal.
This agent no longer writes any test: it runs the existing suite and turns
pytest's JUnit XML report into structured results.

Also enables pytest-rerunfailures (--reruns): a test that fails then
passes within the same run is PROOF of flakiness, not a guess — see
conftest.py on the maisoncarmenta-qa side for the hook that captures this
signal (standard JUnit XML does not keep it).
"""

import json
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from orchestrator.state import QAOrchestratorState
from schemas.execution_result import ExecutionResult

# Reference to the currently running pytest subprocess, to allow immediate
# cancellation from the API (server.py) — this is the only pipeline step
# worth interrupting for real: Claude calls are short enough that cutting
# them off mid-flight wouldn't be worth the complexity.
_current_process: subprocess.Popen | None = None
_process_lock = threading.Lock()


def cancel_current_execution() -> bool:
    """Terminates the currently running pytest process, if any. Returns
    True if a process was actually interrupted."""
    with _process_lock:
        if _current_process is not None and _current_process.poll() is None:
            _current_process.terminate()
            return True
        return False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TARGET_PROJECT = PROJECT_ROOT.parent / "maisoncarmenta-qa"
TARGET_PYTHON = TARGET_PROJECT / ".venv" / "Scripts" / "python.exe"

REPORTS_DIR = PROJECT_ROOT / "reports"
JUNIT_PATH = REPORTS_DIR / "junit-report.xml"

TARGET_REPORTS_DIR = TARGET_PROJECT / "reports"
RERUN_COUNTS_PATH = TARGET_REPORTS_DIR / "rerun-counts.json"

RERUNS = 2
RERUNS_DELAY = 1

MAX_ERROR_TEXT_LENGTH = 4000


def _python_bin() -> str:
    return str(TARGET_PYTHON) if TARGET_PYTHON.exists() else "python"


def list_available_tests() -> list[str]:
    """Lists every pytest node id of the real suite, for the interface
    (checkboxes) — never hardcoded, always read from the real suite to
    stay accurate as tests are added/removed."""

    proc = subprocess.run(
        [_python_bin(), "-m", "pytest", "--collect-only", "-q"],
        cwd=TARGET_PROJECT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return [
        line.strip()
        for line in proc.stdout.splitlines()
        if line.strip() and "::" in line
    ]


def _extract_error_text(node: ET.Element | None) -> str:
    """A pytest <failure>/<error> `message` attribute is a short summary —
    the REAL detail (the offending source line, file:line path, full
    assertion diff) lives in the element's text, ignored until this fix
    (verified empirically beforehand on a real run — see the probe test
    used to inspect a real XML). It's this text that gives Triage and the
    Reporter something to actually reason about, not just the summary."""
    if node is None:
        return ""
    text = (node.text or "").strip()
    if text:
        return text[:MAX_ERROR_TEXT_LENGTH]
    return node.get("message", "")


def _parse_junit(junit_path: Path) -> list[ExecutionResult]:
    if not junit_path.exists():
        return []

    tree = ET.parse(junit_path)
    results: list[ExecutionResult] = []

    for testcase in tree.getroot().iter("testcase"):
        if testcase.find("skipped") is not None:
            continue  # an explicitly skipped test is neither a pass nor a fail

        classname = testcase.get("classname", "")
        name = testcase.get("name", "")
        file = classname.replace(".", "/") + ".py"
        test_id = f"{file}::{name}"

        failure = testcase.find("failure")
        error = testcase.find("error")
        node = failure if failure is not None else error

        results.append(
            ExecutionResult(
                test_id=test_id,
                title=name,
                passed=node is None,
                duration_seconds=float(testcase.get("time", "0")),
                error_message=_extract_error_text(node),
                file=file,
            )
        )

    return results


def _load_rerun_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def executor_node(state: QAOrchestratorState) -> QAOrchestratorState:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if RERUN_COUNTS_PATH.exists():
        RERUN_COUNTS_PATH.unlink()  # never inherit the previous run's counter

    selected = state.get("selected_tests") or []

    command = [
        _python_bin(), "-m", "pytest", "-v",
        f"--junitxml={JUNIT_PATH}",
        f"--reruns={RERUNS}",
        f"--reruns-delay={RERUNS_DELAY}",
        *selected,  # positional pytest node ids; empty = the whole suite
    ]

    global _current_process
    start = time.monotonic()
    with _process_lock:
        _current_process = subprocess.Popen(command, cwd=TARGET_PROJECT)
    try:
        _current_process.wait(timeout=600)
    finally:
        with _process_lock:
            _current_process = None
    total_duration = time.monotonic() - start

    results = _parse_junit(JUNIT_PATH)
    rerun_counts = _load_rerun_counts(RERUN_COUNTS_PATH)
    for r in results:
        r.reruns = rerun_counts.get(r.test_id, 0)

    flaky_recovered = sum(1 for r in results if r.passed and r.reruns > 0)
    scope = f"{len(selected)} selected test(s)" if selected else "the whole suite"

    return {
        **state,
        "execution_results": results,
        "messages": [
            {
                "role": "assistant",
                "content": f"[Executor] {scope}, run in {total_duration:.1f}s: "
                f"{len(results)} tests, {sum(r.passed for r in results)} passed, "
                f"{flaky_recovered} recovered after rerun (proven flakiness).",
            }
        ],
    }
