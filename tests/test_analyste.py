"""Tests de l'Agent Analyste — en particulier sa capacité à éviter de
suggérer des pistes déjà couvertes par de vrais tests existants, ajoutée
en même temps que ces tests (aucun test n'existait avant pour cet agent)."""

from unittest.mock import MagicMock, patch

from agents.analyste import _existing_tests_summary, analyste_node
from schemas.test_case import TestCase as TestCaseModel
from schemas.test_case import TestCaseList as TestCaseListModel


class TestExistingTestsSummary:
    def test_lists_each_existing_test(self):
        with patch("agents.analyste.list_available_tests", return_value=["a::b", "a::c"]):
            summary = _existing_tests_summary()

        assert "- a::b" in summary
        assert "- a::c" in summary

    def test_reports_when_no_tests_exist(self):
        with patch("agents.analyste.list_available_tests", return_value=[]):
            summary = _existing_tests_summary()

        assert "aucun test existant" in summary

    def test_degrades_gracefully_when_collection_fails(self):
        # Pas de spec sans Analyste : une panne de collecte des tests
        # existants ne doit jamais faire planter tout le pipeline.
        with patch("agents.analyste.list_available_tests", side_effect=RuntimeError("pytest introuvable")):
            summary = _existing_tests_summary()

        assert "indisponible" in summary


class TestAnalysteNode:
    def _fake_response(self, test_cases=None, couverture=True):
        result = TestCaseListModel(test_cases=test_cases or [], couverture_jugee_suffisante=couverture)
        return MagicMock(parsed_output=result)

    def test_existing_tests_are_included_in_the_prompt_sent_to_claude(self):
        fake_client = MagicMock()
        fake_client.messages.parse.return_value = self._fake_response()

        with patch("agents.analyste.list_available_tests", return_value=["tests/x.py::test_deja_la"]), \
             patch("agents.analyste.anthropic.Anthropic", return_value=fake_client):
            analyste_node({"specification": "une spec"})

        sent_content = fake_client.messages.parse.call_args.kwargs["messages"][0]["content"]
        assert "tests/x.py::test_deja_la" in sent_content
        assert "une spec" in sent_content

    def test_wires_llm_output_into_state(self):
        tc = TestCaseModel(
            id="TC-001", titre="Nouvelle piste", description="desc",
            etapes=["étape 1"], resultat_attendu="ok", priorite="haute",
        )
        fake_client = MagicMock()
        fake_client.messages.parse.return_value = self._fake_response(
            test_cases=[tc], couverture=False
        )

        with patch("agents.analyste.list_available_tests", return_value=[]), \
             patch("agents.analyste.anthropic.Anthropic", return_value=fake_client):
            result = analyste_node({"specification": "une spec"})

        assert result["test_cases"] == [tc]
        assert result["couverture_jugee_suffisante"] is False
        assert "1 piste" in result["messages"][0]["content"]

    def test_works_even_when_existing_tests_collection_fails(self):
        # La dégradation gracieuse de _existing_tests_summary doit se
        # propager jusqu'ici sans lever d'exception.
        fake_client = MagicMock()
        fake_client.messages.parse.return_value = self._fake_response()

        with patch("agents.analyste.list_available_tests", side_effect=RuntimeError("boom")), \
             patch("agents.analyste.anthropic.Anthropic", return_value=fake_client):
            result = analyste_node({"specification": "une spec"})

        assert result["test_cases"] == []
