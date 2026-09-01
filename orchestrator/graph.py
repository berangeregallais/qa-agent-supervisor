"""Assembles the complete Supervisor graph.

Analyst (suggestions) -> Executor (real suite) -> Triage (if failures)
                                                 -> Reporter (otherwise)

Every agent always returns to the Supervisor — the hub-and-spoke structure
characteristic of the Supervisor pattern.
"""

from langgraph.graph import END, START, StateGraph

from agents.analyst import analyst_node
from agents.executor import executor_node
from agents.reporter import reporter_node
from agents.triage import triage_node
from orchestrator.state import QAOrchestratorState
from orchestrator.supervisor import route_from_supervisor, supervisor_node


def build_graph():
    graph = StateGraph(QAOrchestratorState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("executor", executor_node)
    graph.add_node("triage", triage_node)
    graph.add_node("reporter", reporter_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "analyst": "analyst",
            "executor": "executor",
            "triage": "triage",
            "reporter": "reporter",
            "FINISH": END,
        },
    )

    graph.add_edge("analyst", "supervisor")
    graph.add_edge("executor", "supervisor")
    graph.add_edge("triage", "supervisor")
    graph.add_edge("reporter", "supervisor")

    return graph.compile()
