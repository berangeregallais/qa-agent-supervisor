"""Shared fixtures for the agent tests."""

import pytest

from schemas.execution_result import ExecutionResult
from schemas.report import Report


@pytest.fixture
def junit_xml_factory(tmp_path):
    """Writes a minimal but realistic JUnit XML (the format actually
    produced by pytest, verified live earlier in the project) and returns
    its path. `cases` is a list of dicts: name, classname, time,
    outcome ("passed" | "failed" | "error" | "skipped"), message (optional).
    """

    def _write(cases: list[dict]) -> "Path":  # noqa: F821 - string annotation
        testcases_xml = []
        for case in cases:
            name = case["name"]
            classname = case.get("classname", "tests.test_example")
            time = case.get("time", "1.0")
            outcome = case.get("outcome", "passed")
            message = case.get("message", "simulated error")

            if outcome == "passed":
                body = ""
            elif outcome == "failed":
                body = f'<failure message="{message}">{message}</failure>'
            elif outcome == "error":
                body = f'<error message="{message}">{message}</error>'
            elif outcome == "skipped":
                body = '<skipped message="simulated skip"></skipped>'
            else:
                raise ValueError(f"unknown outcome: {outcome}")

            testcases_xml.append(
                f'<testcase classname="{classname}" name="{name}" time="{time}">{body}</testcase>'
            )

        xml = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<testsuites name="pytest tests">'
            '<testsuite name="pytest" errors="0" failures="0" skipped="0" '
            f'tests="{len(cases)}" time="1.0">'
            + "".join(testcases_xml)
            + "</testsuite></testsuites>"
        )

        path = tmp_path / "junit-report.xml"
        path.write_text(xml, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def execution_result_factory():
    """Builds an ExecutionResult with sensible defaults, so tests only
    repeat what actually varies from one case to the next."""

    def _make(**overrides) -> ExecutionResult:
        defaults = dict(
            test_id="tests/test_example.py::test_something[chromium]",
            title="test_something",
            passed=True,
            duration_seconds=1.0,
            error_message="",
            file="tests/test_example.py",
            reruns=0,
        )
        defaults.update(overrides)
        return ExecutionResult(**defaults)

    return _make


@pytest.fixture
def report_factory():
    """Builds a minimal valid Report, for tests that only need to verify
    what's DONE with the report (persistence, API), not its detailed
    content."""

    def _make(**overrides) -> Report:
        defaults = dict(
            summary="Test summary",
            executive_summary="Everything is fine.",
            total=1,
            passed=1,
            failed=0,
            details=[],
            recommendations=[],
        )
        defaults.update(overrides)
        return Report(**defaults)

    return _make
