"""Tests for the Supervisor: the state summary it sends to the LLM (pure
logic, the easiest part to silently break by changing the state without
updating the summary), routing, and wiring of the decision (LLM mocked)."""

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
        assert "Specification provided: no" in summary
        assert "Number of ideas suggested by the Analyst: 0" in summary
        assert "Number of real execution results: 0" in summary
        assert "Final report already generated: no" in summary

    def test_specification_presence_is_reflected(self):
        summary = _summarize_state({"specification": "a scenario"})
        assert "Specification provided: yes" in summary

    def test_detects_failures_among_execution_results(self, execution_result_factory):
        state = {
            "execution_results": [
                execution_result_factory(passed=True),
                execution_result_factory(passed=False),
            ]
        }
        summary = _summarize_state(state)
        assert "At least one real failure: True" in summary

    def test_detects_no_failures_when_all_passed(self, execution_result_factory):
        state = {"execution_results": [execution_result_factory(passed=True)]}
        summary = _summarize_state(state)
        assert "At least one real failure: False" in summary

    def test_detects_reruns_even_without_failures(self, execution_result_factory):
        # Key case: a test recovered after a rerun is NOT a failure, but
        # must still trigger a pass through Triage.
        state = {"execution_results": [execution_result_factory(passed=True, reruns=1)]}
        summary = _summarize_state(state)
        assert "At least one real failure: False" in summary
        assert "At least one test needed a rerun: True" in summary

    def test_report_presence_is_reflected(self):
        summary = _summarize_state({"report": object()})
        assert "Final report already generated: yes" in summary

    def test_detects_previous_loop_back_to_analyst(self):
        state = {"messages": [{"content": "[Supervisor] -> analyst (loop back)"}]}
        summary = _summarize_state(state)
        assert "Already looped back to the Analyst: True" in summary


class TestRouteFromSupervisor:
    def test_returns_the_next_agent_field(self):
        assert route_from_supervisor({"next_agent": "executor"}) == "executor"

    def test_returns_finish(self):
        assert route_from_supervisor({"next_agent": "FINISH"}) == "FINISH"


class TestSupervisorNode:
    def test_wires_llm_decision_into_state(self):
        decision = SupervisorDecision(next_agent="reporter", reasoning="results ready")
        fake_client = MagicMock()
        fake_client.messages.parse.return_value = MagicMock(parsed_output=decision)

        with patch("orchestrator.supervisor.anthropic.Anthropic", return_value=fake_client):
            result = supervisor_node({"specification": ""})

        assert result["next_agent"] == "reporter"
        assert "reporter" in result["messages"][0]["content"]
        assert "results ready" in result["messages"][0]["content"]

    def test_preserves_the_rest_of_the_state_unchanged(self):
        decision = SupervisorDecision(next_agent="FINISH", reasoning="done")
        fake_client = MagicMock()
        fake_client.messages.parse.return_value = MagicMock(parsed_output=decision)

        with patch("orchestrator.supervisor.anthropic.Anthropic", return_value=fake_client):
            result = supervisor_node({"specification": "keep-me", "triage": ["x"]})

        assert result["specification"] == "keep-me"
        assert result["triage"] == ["x"]
