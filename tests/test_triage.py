"""Tests de l'Agent Triage.

Le point important à couvrir : la partie "flaky prouvé par rerun" ne doit
JAMAIS déclencher d'appel Claude (c'est une preuve directe, pas un
jugement) — testé en vérifiant qu'aucun mock d'API n'est nécessaire pour ce
cas. La partie "échec persistant" nécessite un jugement LLM, mocké ici pour
ne jamais dépenser un vrai appel API dans la suite de tests."""

from unittest.mock import MagicMock, patch

from agents.triage import triage_node
from schemas.triage import TriageEntry, TriageResult


def _state_with(execution_results):
    return {"execution_results": execution_results}


class TestDeterministicFlakyDetection:
    def test_no_results_produces_no_triage_and_no_api_call(self, execution_result_factory):
        # anthropic.Anthropic n'est jamais patché ici : si le code essayait
        # de l'appeler sans clé configurée, ce test échouerait tout seul —
        # c'est la preuve qu'aucun appel API n'a lieu.
        result = triage_node(_state_with([]))
        assert result["triage"] == []

    def test_all_passed_without_rerun_produces_no_triage(self, execution_result_factory):
        results = [
            execution_result_factory(test_id="a", passed=True, reruns=0),
            execution_result_factory(test_id="b", passed=True, reruns=0),
        ]
        result = triage_node(_state_with(results))
        assert result["triage"] == []

    def test_recovered_flaky_is_categorized_without_any_llm_call(self, execution_result_factory):
        results = [execution_result_factory(test_id="tests/x.py::y", passed=True, reruns=2)]

        result = triage_node(_state_with(results))

        assert len(result["triage"]) == 1
        entry = result["triage"][0]
        assert entry.test_id == "tests/x.py::y"
        assert entry.categorie == "flaky"
        assert entry.confiance == 1.0  # certitude totale : c'est une preuve, pas une estimation
        assert "2" in entry.justification

    def test_mix_of_recovered_flaky_and_clean_passes(self, execution_result_factory):
        results = [
            execution_result_factory(test_id="flaky-one", passed=True, reruns=1),
            execution_result_factory(test_id="clean-one", passed=True, reruns=0),
        ]

        result = triage_node(_state_with(results))

        assert len(result["triage"]) == 1
        assert result["triage"][0].test_id == "flaky-one"


class TestPersistentFailureTriage:
    def test_persistent_failure_is_sent_to_claude_and_result_is_used(self, execution_result_factory):
        failing = execution_result_factory(
            test_id="tests/x.py::broken", passed=False, reruns=2,
            message_erreur="AssertionError: attendu 200, reçu 404",
        )

        fake_entry = TriageEntry(
            test_id="tests/x.py::broken",
            categorie="bug_produit",
            confiance=0.9,
            justification="Statut HTTP inattendu, comportement applicatif.",
        )
        fake_response = MagicMock(parsed_output=TriageResult(entries=[fake_entry]))
        fake_client = MagicMock()
        fake_client.messages.parse.return_value = fake_response

        with patch("agents.triage.anthropic.Anthropic", return_value=fake_client):
            result = triage_node(_state_with([failing]))

        assert result["triage"] == [fake_entry]
        fake_client.messages.parse.assert_called_once()
        # Le message d'erreur réel doit être transmis au LLM, pas résumé/perdu.
        sent_content = fake_client.messages.parse.call_args.kwargs["messages"][0]["content"]
        assert "404" in sent_content

    def test_recovered_flaky_and_persistent_failure_can_coexist(self, execution_result_factory):
        recovered = execution_result_factory(test_id="flaky-one", passed=True, reruns=1)
        failing = execution_result_factory(test_id="broken-one", passed=False, reruns=2)

        fake_entry = TriageEntry(
            test_id="broken-one", categorie="environnement", confiance=0.6, justification="Timeout réseau."
        )
        fake_client = MagicMock()
        fake_client.messages.parse.return_value = MagicMock(
            parsed_output=TriageResult(entries=[fake_entry])
        )

        with patch("agents.triage.anthropic.Anthropic", return_value=fake_client):
            result = triage_node(_state_with([recovered, failing]))

        categories = {e.test_id: e.categorie for e in result["triage"]}
        assert categories["flaky-one"] == "flaky"
        assert categories["broken-one"] == "environnement"
