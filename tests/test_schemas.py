"""Tests for the data contracts (Pydantic) — validation rules are the only
safeguard against a malformed LLM response silently propagating through
the rest of the pipeline."""

import pytest
from pydantic import ValidationError

from schemas.execution_result import ExecutionResult
from schemas.report import Report
from schemas.triage import TriageEntry


class TestTriageEntry:
    def test_valid_entry_is_accepted(self):
        entry = TriageEntry(
            test_id="tests/a.py::b", category="product_bug", confidence=0.8, justification="ok"
        )
        assert entry.confidence == 0.8

    @pytest.mark.parametrize("confidence", [-0.1, 1.1, 2.0, -5])
    def test_confidence_outside_zero_one_is_rejected(self, confidence):
        with pytest.raises(ValidationError):
            TriageEntry(
                test_id="x", category="flaky", confidence=confidence, justification="ok"
            )

    @pytest.mark.parametrize("confidence", [0.0, 1.0, 0.5])
    def test_confidence_boundaries_are_accepted(self, confidence):
        entry = TriageEntry(test_id="x", category="flaky", confidence=confidence, justification="ok")
        assert entry.confidence == confidence

    def test_unknown_category_is_rejected(self):
        with pytest.raises(ValidationError):
            TriageEntry(test_id="x", category="not_a_real_category", confidence=0.5, justification="ok")


class TestExecutionResult:
    def test_reruns_defaults_to_zero(self):
        result = ExecutionResult(
            test_id="x", title="x", passed=True, duration_seconds=1.0,
            error_message="", file="tests/x.py",
        )
        assert result.reruns == 0


class TestReport:
    def test_coverage_suggestions_defaults_to_empty_list(self):
        report = Report(
            summary="ok", executive_summary="ok", total=1, passed=1, failed=0,
            details=[], recommendations=[],
        )
        assert report.coverage_suggestions == []

    def test_missing_summary_is_rejected(self):
        with pytest.raises(ValidationError):
            Report(
                executive_summary="ok", total=1, passed=1, failed=0,
                details=[], recommendations=[],
            )  # summary missing

    def test_missing_executive_summary_is_rejected(self):
        with pytest.raises(ValidationError):
            Report(
                summary="ok", total=1, passed=1, failed=0,
                details=[], recommendations=[],
            )  # executive_summary missing, a common slip since summary already exists
