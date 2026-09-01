"""Tests for the Executor's pure logic — no Claude call, no real pytest
subprocess: only JUnit/rerun-count parsing and subprocess state management,
which are deterministic."""

import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

from agents import executor


class TestExtractErrorText:
    """A pytest <failure>'s `message` attribute is a truncated summary —
    the real detail (source line, full assertion) is in the element's
    TEXT. Verified on a real pytest run before this fix (see the comment
    on _extract_error_text)."""

    def test_none_node_returns_empty_string(self):
        assert executor._extract_error_text(None) == ""

    def test_prefers_full_text_over_short_message_attribute(self):
        node = ET.fromstring(
            '<failure message="short summary">'
            "def test_x():\n>       assert 1 == 2\nE       AssertionError\n"
            "</failure>"
        )

        result = executor._extract_error_text(node)

        assert "short summary" not in result
        assert "assert 1 == 2" in result
        assert "AssertionError" in result

    def test_falls_back_to_message_when_text_is_empty(self):
        node = ET.fromstring('<failure message="only clue available"></failure>')

        assert executor._extract_error_text(node) == "only clue available"

    def test_falls_back_to_message_when_text_is_only_whitespace(self):
        node = ET.fromstring('<failure message="fallback">   \n   </failure>')

        assert executor._extract_error_text(node) == "fallback"

    def test_truncates_very_long_text(self):
        long_text = "x" * (executor.MAX_ERROR_TEXT_LENGTH + 500)
        node = ET.fromstring(f'<failure message="short">{long_text}</failure>')

        result = executor._extract_error_text(node)

        assert len(result) == executor.MAX_ERROR_TEXT_LENGTH


class TestParseJunit:
    def test_no_file_returns_empty_list(self, tmp_path):
        assert executor._parse_junit(tmp_path / "absent.xml") == []

    def test_passed_test_is_reported_correctly(self, junit_xml_factory):
        path = junit_xml_factory([
            {"name": "test_ok[chromium]", "classname": "tests.test_homepage", "time": "1.23"}
        ])

        results = executor._parse_junit(path)

        assert len(results) == 1
        r = results[0]
        assert r.test_id == "tests/test_homepage.py::test_ok[chromium]"
        assert r.file == "tests/test_homepage.py"
        assert r.passed is True
        assert r.duration_seconds == 1.23
        assert r.error_message == ""

    def test_failed_test_captures_error_message(self, junit_xml_factory):
        path = junit_xml_factory([
            {
                "name": "test_broken",
                "classname": "tests.test_homepage",
                "outcome": "failed",
                "message": "AssertionError: expected 200, got 404",
            }
        ])

        results = executor._parse_junit(path)

        assert results[0].passed is False
        assert "404" in results[0].error_message

    def test_error_node_treated_like_failure(self, junit_xml_factory):
        path = junit_xml_factory([
            {"name": "test_crash", "outcome": "error", "message": "ConnectionError"}
        ])

        results = executor._parse_junit(path)

        assert results[0].passed is False
        assert results[0].error_message == "ConnectionError"

    def test_skipped_test_is_excluded_entirely(self, junit_xml_factory):
        path = junit_xml_factory([
            {"name": "test_ok", "outcome": "passed"},
            {"name": "test_skipped", "outcome": "skipped"},
        ])

        results = executor._parse_junit(path)

        assert len(results) == 1
        assert results[0].title == "test_ok"

    def test_mixed_batch_preserves_order_and_each_outcome(self, junit_xml_factory):
        path = junit_xml_factory([
            {"name": "test_a", "outcome": "passed"},
            {"name": "test_b", "outcome": "failed", "message": "boom"},
            {"name": "test_c", "outcome": "passed"},
        ])

        results = executor._parse_junit(path)

        assert [r.title for r in results] == ["test_a", "test_b", "test_c"]
        assert [r.passed for r in results] == [True, False, True]


class TestLoadRerunCounts:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        assert executor._load_rerun_counts(tmp_path / "absent.json") == {}

    def test_existing_file_is_parsed(self, tmp_path):
        path = tmp_path / "rerun-counts.json"
        path.write_text('{"tests/test_x.py::test_y": 2}', encoding="utf-8")

        assert executor._load_rerun_counts(path) == {"tests/test_x.py::test_y": 2}


class TestCancelCurrentExecution:
    def test_returns_false_when_nothing_running(self):
        executor._current_process = None
        assert executor.cancel_current_execution() is False

    def test_terminates_a_running_process(self):
        fake_process = MagicMock()
        fake_process.poll.return_value = None  # None = still running (subprocess convention)
        executor._current_process = fake_process

        result = executor.cancel_current_execution()

        assert result is True
        fake_process.terminate.assert_called_once()
        executor._current_process = None  # don't leak state into other tests

    def test_does_not_terminate_an_already_finished_process(self):
        fake_process = MagicMock()
        fake_process.poll.return_value = 0  # already finished
        executor._current_process = fake_process

        result = executor.cancel_current_execution()

        assert result is False
        fake_process.terminate.assert_not_called()
        executor._current_process = None


class TestListAvailableTests:
    def test_parses_node_ids_and_ignores_summary_line(self):
        fake_stdout = (
            "tests/test_a.py::test_one[chromium]\n"
            "tests/test_a.py::test_two[chromium]\n"
            "\n"
            "2 tests collected in 0.02s\n"
        )
        fake_result = MagicMock(stdout=fake_stdout)

        with patch.object(executor.subprocess, "run", return_value=fake_result) as mock_run:
            tests = executor.list_available_tests()

        assert tests == [
            "tests/test_a.py::test_one[chromium]",
            "tests/test_a.py::test_two[chromium]",
        ]
        # The summary line ("2 tests collected...") has no "::" -> excluded
        assert all("::" in t for t in tests)
        mock_run.assert_called_once()
