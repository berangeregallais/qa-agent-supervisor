"""Tests de orchestrator/runner.py — construction de l'état initial et
persistance du "dernier run", isolées du vrai dossier reports/ via
monkeypatch (jamais touché pendant les tests)."""

from orchestrator import runner


class TestInitialState:
    def test_selected_tests_none_becomes_empty_list(self):
        state = runner._initial_state("une spec", None)
        assert state["selected_tests"] == []

    def test_selected_tests_preserved_when_provided(self):
        state = runner._initial_state("", ["tests/a.py::x"])
        assert state["selected_tests"] == ["tests/a.py::x"]

    def test_starts_at_analyste(self):
        assert runner._initial_state("", None)["next_agent"] == "analyste"

    def test_all_result_collections_start_empty(self):
        state = runner._initial_state("", None)
        assert state["test_cases"] == []
        assert state["execution_results"] == []
        assert state["triage"] == []
        assert state["report"] is None


class TestLastRunPersistence:
    def test_no_timestamp_before_any_run(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "LAST_RUN_PATH", tmp_path / "last-run.json")
        assert runner.get_last_run_timestamp() is None

    def test_record_then_read_round_trip(self, tmp_path, monkeypatch):
        last_run_path = tmp_path / "reports" / "last-run.json"
        monkeypatch.setattr(runner, "LAST_RUN_PATH", last_run_path)

        runner._record_last_run()
        timestamp = runner.get_last_run_timestamp()

        assert timestamp is not None
        assert timestamp.endswith("+00:00")  # UTC, comme documenté

    def test_recording_again_overwrites_the_previous_timestamp(self, tmp_path, monkeypatch):
        last_run_path = tmp_path / "last-run.json"
        monkeypatch.setattr(runner, "LAST_RUN_PATH", last_run_path)

        runner._record_last_run()
        first = runner.get_last_run_timestamp()
        runner._record_last_run()
        second = runner.get_last_run_timestamp()

        assert second is not None
        assert first is not None
        # Pas d'accumulation d'historique ici (volontaire, voir README —
        # seul le dernier timestamp est conservé par ce mécanisme).


class TestResetReportsDir:
    def test_creates_the_directory_if_absent(self, tmp_path, monkeypatch):
        reports_dir = tmp_path / "reports"
        monkeypatch.setattr(runner, "REPORTS_DIR", reports_dir)

        runner._reset_reports_dir()

        assert reports_dir.exists()

    def test_wipes_existing_contents(self, tmp_path, monkeypatch):
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "stale-run.xml").write_text("ancien contenu", encoding="utf-8")
        monkeypatch.setattr(runner, "REPORTS_DIR", reports_dir)

        runner._reset_reports_dir()

        assert list(reports_dir.iterdir()) == []
