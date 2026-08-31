"""Tests du Superviseur : le résumé d'état qu'il envoie au LLM (logique
pure, la partie la plus facile à casser silencieusement en modifiant le
state sans mettre à jour le résumé), le routage, et le câblage de la
décision (LLM mocké)."""

from unittest.mock import MagicMock, patch

from orchestrator.supervisor import (
    SupervisorDecision,
    _summarize_state,
    route_from_supervisor,
    supervisor_node,
)


class TestSummarizeState:
    def test_empty_state_reports_nothing_done(self):
        summary = _summarize_state({})
        assert "Spécification fournie : non" in summary
        assert "Nombre de pistes suggérées par l'Analyste : 0" in summary
        assert "Nombre de résultats d'exécution réels : 0" in summary
        assert "Rapport final déjà généré : non" in summary

    def test_specification_presence_is_reflected(self):
        summary = _summarize_state({"specification": "un scénario"})
        assert "Spécification fournie : oui" in summary

    def test_detects_failures_among_execution_results(self, execution_result_factory):
        state = {
            "execution_results": [
                execution_result_factory(passed=True),
                execution_result_factory(passed=False),
            ]
        }
        summary = _summarize_state(state)
        assert "Au moins un échec réel : True" in summary

    def test_detects_no_failures_when_all_passed(self, execution_result_factory):
        state = {"execution_results": [execution_result_factory(passed=True)]}
        summary = _summarize_state(state)
        assert "Au moins un échec réel : False" in summary

    def test_detects_reruns_even_without_failures(self, execution_result_factory):
        # Cas clé : un test récupéré après rerun n'est PAS un échec, mais
        # doit quand même déclencher le passage par le Triage.
        state = {"execution_results": [execution_result_factory(passed=True, reruns=1)]}
        summary = _summarize_state(state)
        assert "Au moins un échec réel : False" in summary
        assert "Au moins un test a eu besoin d'un rerun : True" in summary

    def test_report_presence_is_reflected(self):
        summary = _summarize_state({"report": object()})
        assert "Rapport final déjà généré : oui" in summary

    def test_detects_previous_loop_back_to_analyste(self):
        state = {"messages": [{"content": "[Superviseur] -> analyste (rebouclage)"}]}
        summary = _summarize_state(state)
        assert "A déjà rebouclé vers l'Analyste : True" in summary


class TestRouteFromSupervisor:
    def test_returns_the_next_agent_field(self):
        assert route_from_supervisor({"next_agent": "executeur"}) == "executeur"

    def test_returns_finish(self):
        assert route_from_supervisor({"next_agent": "FINISH"}) == "FINISH"


class TestSupervisorNode:
    def test_wires_llm_decision_into_state(self):
        decision = SupervisorDecision(next_agent="rapporteur", reasoning="résultats prêts")
        fake_client = MagicMock()
        fake_client.messages.parse.return_value = MagicMock(parsed_output=decision)

        with patch("orchestrator.supervisor.anthropic.Anthropic", return_value=fake_client):
            result = supervisor_node({"specification": ""})

        assert result["next_agent"] == "rapporteur"
        assert "rapporteur" in result["messages"][0]["content"]
        assert "résultats prêts" in result["messages"][0]["content"]

    def test_preserves_the_rest_of_the_state_unchanged(self):
        decision = SupervisorDecision(next_agent="FINISH", reasoning="terminé")
        fake_client = MagicMock()
        fake_client.messages.parse.return_value = MagicMock(parsed_output=decision)

        with patch("orchestrator.supervisor.anthropic.Anthropic", return_value=fake_client):
            result = supervisor_node({"specification": "garder-moi", "triage": ["x"]})

        assert result["specification"] == "garder-moi"
        assert result["triage"] == ["x"]
