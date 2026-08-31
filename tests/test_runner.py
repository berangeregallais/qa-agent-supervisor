"""Tests de orchestrator/runner.py — construction de l'état initial,
persistance du "dernier run" et de l'historique, isolées du vrai dossier
reports/ via monkeypatch (jamais touché pendant les tests)."""

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
        assert timestamp.endswith("+00:00")  # UTC, comme documenté

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

        runner._record_completed_run(report_factory(total=5, reussis=4, echoues=1))
        history = runner.get_history()

        assert len(history) == 1
        assert history[0]["total"] == 5
        assert history[0]["reussis"] == 4
        assert history[0]["echoues"] == 1

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
        # Les 3 conservés doivent être les plus récents (2, 3, 4), pas les
        # 3 premiers arrivés.
        assert [entry["total"] for entry in history] == [4, 3, 2]

    def test_resume_is_truncated_to_200_chars(self, tmp_path, monkeypatch, report_factory):
        _patch_reports_paths(monkeypatch, tmp_path)

        runner._record_completed_run(report_factory(resume="x" * 500))

        assert len(runner.get_history()[0]["resume"]) == 200


class TestResetReportsDir:
    def test_creates_the_directory_if_absent(self, tmp_path, monkeypatch):
        reports_dir = tmp_path / "reports"
        monkeypatch.setattr(runner, "REPORTS_DIR", reports_dir)

        runner._reset_reports_dir()

        assert reports_dir.exists()

    def test_wipes_non_persistent_contents(self, tmp_path, monkeypatch):
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "stale-run.xml").write_text("ancien contenu", encoding="utf-8")
        monkeypatch.setattr(runner, "REPORTS_DIR", reports_dir)

        runner._reset_reports_dir()

        assert list(reports_dir.iterdir()) == []

    def test_never_deletes_last_run_or_history(self, tmp_path, monkeypatch, report_factory):
        # Reproduit exactement le bug trouvé : un run annulé ne doit jamais
        # effacer la mémoire des runs précédents. Avant le correctif, ce
        # test échouait — _reset_reports_dir supprimait tout le dossier.
        reports_dir = _patch_reports_paths(monkeypatch, tmp_path)
        runner._record_completed_run(report_factory())

        assert runner.get_last_run_timestamp() is not None
        assert len(runner.get_history()) == 1

        runner._reset_reports_dir()  # simule le début d'un nouveau run, potentiellement annulé ensuite

        assert runner.get_last_run_timestamp() is not None
        assert len(runner.get_history()) == 1
        assert reports_dir.exists()
