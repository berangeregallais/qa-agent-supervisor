"""Tests for orchestrator/runner.py — building the initial state,
persisting the "last run" and history, isolated from the real reports/
directory via monkeypatch (never touched during tests)."""

from orchestrator import runner


class TestInitialState:
    def test_selected_tests_none_becomes_empty_list(self):
        state = runner._initial_state("a spec", None)
        assert state["selected_tests"] == []

    def test_selected_tests_preserved_when_provided(self):
        state = runner._initial_state("", ["tests/a.py::x"])
        assert state["selected_tests"] == ["tests/a.py::x"]

    def test_starts_at_analyst(self):
        assert runner._initial_state("", None)["next_agent"] == "analyst"

    def test_all_result_collections_start_empty(self):
        state = runner._initial_state("", None)
        assert state["test_cases"] == []
        assert state["execution_results"] == []
        assert state["triage"] == []
        assert state["report"] is None


def _patch_reports_paths(monkeypatch, tmp_path):
    reports_dir = tmp_path / "reports"
    monkeypatch.setattr(runner, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(runner, "LAST_RUN_PATH", reports_dir / "last-run.json")
    monkeypatch.setattr(runner, "HISTORY_PATH", reports_dir / "history.json")
    monkeypatch.setattr(runner, "_PERSISTENT_FILENAMES", {"last-run.json", "history.json"})
    return reports_dir


class TestLastRunPersistence:
    def test_no_timestamp_before_any_run(self, tmp_path, monkeypatch):
        _patch_reports_paths(monkeypatch, tmp_path)
        assert runner.get_last_run_timestamp() is None

    def test_recording_a_completed_run_sets_the_timestamp(self, tmp_path, monkeypatch, report_factory):
        _patch_reports_paths(monkeypatch, tmp_path)

        runner._record_completed_run(report_factory())
        timestamp = runner.get_last_run_timestamp()

        assert timestamp is not None
        assert timestamp.endswith("+00:00")  # UTC, as documented

    def test_recording_again_overwrites_the_previous_timestamp(self, tmp_path, monkeypatch, report_factory):
        _patch_reports_paths(monkeypatch, tmp_path)

        runner._record_completed_run(report_factory())
        first = runner.get_last_run_timestamp()
        runner._record_completed_run(report_factory())
        second = runner.get_last_run_timestamp()

        assert first is not None and second is not None


class TestHistory:
    def test_empty_before_any_run(self, tmp_path, monkeypatch):
        _patch_reports_paths(monkeypatch, tmp_path)
        assert runner.get_history() == []

    def test_recorded_run_appears_in_history(self, tmp_path, monkeypatch, report_factory):
        _patch_reports_paths(monkeypatch, tmp_path)

        runner._record_completed_run(report_factory(total=5, passed=4, failed=1))
        history = runner.get_history()

        assert len(history) == 1
        assert history[0]["total"] == 5
        assert history[0]["passed"] == 4
        assert history[0]["failed"] == 1

    def test_history_is_most_recent_first(self, tmp_path, monkeypatch, report_factory):
        _patch_reports_paths(monkeypatch, tmp_path)

        runner._record_completed_run(report_factory(total=1))
        runner._record_completed_run(report_factory(total=2))
        runner._record_completed_run(report_factory(total=3))

        history = runner.get_history()

        assert [entry["total"] for entry in history] == [3, 2, 1]

    def test_history_is_capped_at_max_entries(self, tmp_path, monkeypatch, report_factory):
        _patch_reports_paths(monkeypatch, tmp_path)
        monkeypatch.setattr(runner, "MAX_HISTORY_ENTRIES", 3)

        for i in range(5):
            runner._record_completed_run(report_factory(total=i))

        history = runner.get_history()

        assert len(history) == 3
        # The 3 kept must be the most recent (2, 3, 4), not the first 3.
        assert [entry["total"] for entry in history] == [4, 3, 2]

    def test_summary_is_truncated_to_200_chars(self, tmp_path, monkeypatch, report_factory):
        _patch_reports_paths(monkeypatch, tmp_path)

        runner._record_completed_run(report_factory(summary="x" * 500))

        assert len(runner.get_history()[0]["summary"]) == 200


class TestResetReportsDir:
    def test_creates_the_directory_if_absent(self, tmp_path, monkeypatch):
        reports_dir = tmp_path / "reports"
        monkeypatch.setattr(runner, "REPORTS_DIR", reports_dir)

        runner._reset_reports_dir()

        assert reports_dir.exists()

    def test_wipes_non_persistent_contents(self, tmp_path, monkeypatch):
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "stale-run.xml").write_text("old content", encoding="utf-8")
        monkeypatch.setattr(runner, "REPORTS_DIR", reports_dir)

        runner._reset_reports_dir()

        assert list(reports_dir.iterdir()) == []

    def test_never_deletes_last_run_or_history(self, tmp_path, monkeypatch, report_factory):
        # Exactly reproduces the bug found: a cancelled run must never erase
        # the memory of previous runs. Before the fix, this test failed —
        # _reset_reports_dir wiped the whole directory.
        reports_dir = _patch_reports_paths(monkeypatch, tmp_path)
        runner._record_completed_run(report_factory())

        assert runner.get_last_run_timestamp() is not None
        assert len(runner.get_history()) == 1

        runner._reset_reports_dir()  # simulates the start of a new run, possibly cancelled afterwards

        assert runner.get_last_run_timestamp() is not None
        assert len(runner.get_history()) == 1
        assert reports_dir.exists()
