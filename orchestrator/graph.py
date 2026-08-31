"""Assemble le graphe Supervisor complet.

Analyste (suggestions) -> Exécuteur (vraie suite) -> Triage (si échecs)
                                                    -> Rapporteur (sinon)

Chaque agent retourne systématiquement au Superviseur — structure
hub-and-spoke caractéristique du pattern Supervisor.
"""

from langgraph.graph import END, START, StateGraph

from agents.analyste import analyste_node
from agents.executeur import executeur_node
from agents.rapporteur import rapporteur_node
from agents.triage import triage_node
from orchestrator.state import QAOrchestratorState
from orchestrator.supervisor import route_from_supervisor, supervisor_node


def build_graph():
    graph = StateGraph(QAOrchestratorState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("analyste", analyste_node)
    graph.add_node("executeur", executeur_node)
    graph.add_node("triage", triage_node)
    graph.add_node("rapporteur", rapporteur_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "analyste": "analyste",
            "executeur": "executeur",
            "triage": "triage",
            "rapporteur": "rapporteur",
            "FINISH": END,
        },
    )

    graph.add_edge("analyste", "supervisor")
    graph.add_edge("executeur", "supervisor")
    graph.add_edge("triage", "supervisor")
    graph.add_edge("rapporteur", "supervisor")

    return graph.compile()
