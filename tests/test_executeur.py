"""Tests de la logique pure de l'Exécuteur — aucun appel Claude, aucun vrai
sous-processus pytest : uniquement le parsing JUnit/rerun-counts et la
gestion d'état du sous-processus, qui sont déterministes."""

from unittest.mock import MagicMock, patch

from agents import executeur


class TestParseJunit:
    def test_no_file_returns_empty_list(self, tmp_path):
        assert executeur._parse_junit(tmp_path / "absent.xml") == []

    def test_passed_test_is_reported_correctly(self, junit_xml_factory):
        path = junit_xml_factory([
            {"name": "test_ok[chromium]", "classname": "tests.test_homepage", "time": "1.23"}
        ])

        results = executeur._parse_junit(path)

        assert len(results) == 1
        r = results[0]
        assert r.test_id == "tests/test_homepage.py::test_ok[chromium]"
        assert r.fichier == "tests/test_homepage.py"
        assert r.passed is True
        assert r.duree_secondes == 1.23
        assert r.message_erreur == ""

    def test_failed_test_captures_error_message(self, junit_xml_factory):
        path = junit_xml_factory([
            {
                "name": "test_broken",
                "classname": "tests.test_homepage",
                "outcome": "failed",
                "message": "AssertionError: attendu 200, reçu 404",
            }
        ])

        results = executeur._parse_junit(path)

        assert results[0].passed is False
        assert "404" in results[0].message_erreur

    def test_error_node_treated_like_failure(self, junit_xml_factory):
        path = junit_xml_factory([
            {"name": "test_crash", "outcome": "error", "message": "ConnectionError"}
        ])

        results = executeur._parse_junit(path)

        assert results[0].passed is False
        assert results[0].message_erreur == "ConnectionError"

    def test_skipped_test_is_excluded_entirely(self, junit_xml_factory):
        path = junit_xml_factory([
            {"name": "test_ok", "outcome": "passed"},
            {"name": "test_skipped", "outcome": "skipped"},
        ])

        results = executeur._parse_junit(path)

        assert len(results) == 1
        assert results[0].titre == "test_ok"

    def test_mixed_batch_preserves_order_and_each_outcome(self, junit_xml_factory):
        path = junit_xml_factory([
            {"name": "test_a", "outcome": "passed"},
            {"name": "test_b", "outcome": "failed", "message": "boom"},
            {"name": "test_c", "outcome": "passed"},
        ])

        results = executeur._parse_junit(path)

        assert [r.titre for r in results] == ["test_a", "test_b", "test_c"]
        assert [r.passed for r in results] == [True, False, True]


class TestLoadRerunCounts:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        assert executeur._load_rerun_counts(tmp_path / "absent.json") == {}

    def test_existing_file_is_parsed(self, tmp_path):
        path = tmp_path / "rerun-counts.json"
        path.write_text('{"tests/test_x.py::test_y": 2}', encoding="utf-8")

        assert executeur._load_rerun_counts(path) == {"tests/test_x.py::test_y": 2}


class TestCancelCurrentExecution:
    def test_returns_false_when_nothing_running(self):
        executeur._current_process = None
        assert executeur.cancel_current_execution() is False

    def test_terminates_a_running_process(self):
        fake_process = MagicMock()
        fake_process.poll.return_value = None  # None = toujours en cours (convention subprocess)
        executeur._current_process = fake_process

        result = executeur.cancel_current_execution()

        assert result is True
        fake_process.terminate.assert_called_once()
        executeur._current_process = None  # ne pas polluer les tests suivants

    def test_does_not_terminate_an_already_finished_process(self):
        fake_process = MagicMock()
        fake_process.poll.return_value = 0  # déjà terminé
        executeur._current_process = fake_process

        result = executeur.cancel_current_execution()

        assert result is False
        fake_process.terminate.assert_not_called()
        executeur._current_process = None


class TestListAvailableTests:
    def test_parses_node_ids_and_ignores_summary_line(self):
        fake_stdout = (
            "tests/test_a.py::test_one[chromium]\n"
            "tests/test_a.py::test_two[chromium]\n"
            "\n"
            "2 tests collected in 0.02s\n"
        )
        fake_result = MagicMock(stdout=fake_stdout)

        with patch.object(executeur.subprocess, "run", return_value=fake_result) as mock_run:
            tests = executeur.list_available_tests()

        assert tests == [
            "tests/test_a.py::test_one[chromium]",
            "tests/test_a.py::test_two[chromium]",
        ]
        # La ligne de résumé ("2 tests collected...") n'a pas de "::" -> exclue
        assert all("::" in t for t in tests)
        mock_run.assert_called_once()
