"""Tests for the Analyst agent — in particular its ability to avoid
suggesting ideas already covered by real existing tests, added alongside
these tests (no test existed for this agent before)."""

from unittest.mock import MagicMock, patch

from agents.analyst import _existing_tests_summary, analyst_node
from schemas.test_case import TestCase as TestCaseModel
from schemas.test_case import TestCaseList as TestCaseListModel


class TestExistingTestsSummary:
    def test_lists_each_existing_test(self):
        with patch("agents.analyst.list_available_tests", return_value=["a::b", "a::c"]):
            summary = _existing_tests_summary()

        assert "- a::b" in summary
        assert "- a::c" in summary

    def test_reports_when_no_tests_exist(self):
        with patch("agents.analyst.list_available_tests", return_value=[]):
            summary = _existing_tests_summary()

        assert "no existing tests found" in summary

    def test_degrades_gracefully_when_collection_fails(self):
        # No spec-less Analyst: a failure to collect existing tests must
        # never crash the whole pipeline.
        with patch("agents.analyst.list_available_tests", side_effect=RuntimeError("pytest not found")):
            summary = _existing_tests_summary()

        assert "unavailable" in summary


class TestAnalystNode:
    def _fake_response(self, test_cases=None, coverage=True):
        result = TestCaseListModel(test_cases=test_cases or [], coverage_judged_sufficient=coverage)
        return MagicMock(parsed_output=result)

    def test_existing_tests_are_included_in_the_prompt_sent_to_claude(self):
        fake_client = MagicMock()
        fake_client.messages.parse.return_value = self._fake_response()

        with patch("agents.analyst.list_available_tests", return_value=["tests/x.py::test_already_there"]), \
             patch("agents.analyst.anthropic.Anthropic", return_value=fake_client):
            analyst_node({"specification": "a spec"})

        sent_content = fake_client.messages.parse.call_args.kwargs["messages"][0]["content"]
        assert "tests/x.py::test_already_there" in sent_content
        assert "a spec" in sent_content

    def test_wires_llm_output_into_state(self):
        tc = TestCaseModel(
            id="TC-001", title="New idea", description="desc",
            steps=["step 1"], expected_result="ok", priority="high",
        )
        fake_client = MagicMock()
        fake_client.messages.parse.return_value = self._fake_response(
            test_cases=[tc], coverage=False
        )

        with patch("agents.analyst.list_available_tests", return_value=[]), \
             patch("agents.analyst.anthropic.Anthropic", return_value=fake_client):
            result = analyst_node({"specification": "a spec"})

        assert result["test_cases"] == [tc]
        assert result["coverage_judged_sufficient"] is False
        assert "1 NEW idea(s) suggested" in result["messages"][0]["content"]

    def test_works_even_when_existing_tests_collection_fails(self):
        # _existing_tests_summary's graceful degradation must propagate
        # here without raising an exception.
        fake_client = MagicMock()
        fake_client.messages.parse.return_value = self._fake_response()

        with patch("agents.analyst.list_available_tests", side_effect=RuntimeError("boom")), \
             patch("agents.analyst.anthropic.Anthropic", return_value=fake_client):
            result = analyst_node({"specification": "a spec"})

        assert result["test_cases"] == []
