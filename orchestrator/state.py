from typing import Annotated, Literal, Optional

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from schemas.execution_result import ExecutionResult
from schemas.report import Report
from schemas.test_case import TestCase
from schemas.triage import TriageEntry

NextAgent = Literal["analyste", "executeur", "triage", "rapporteur", "FINISH"]


class QAOrchestratorState(TypedDict):
    """État partagé, passé et enrichi par chaque nœud du graphe.

    Deux catégories de champs, volontairement séparées :
    - les données de travail (typées Pydantic), lues/écrites par les agents
      pour accomplir leur tâche — le "quoi".
    - `messages`, un journal de traçabilité en langage naturel (raisonnement
      du superviseur, résumé d'activité de chaque agent) — pas consommé
      programmatiquement par les agents, seulement pour l'observabilité
      humaine et le débogage. Ne jamais y stocker une donnée dont un agent
      a besoin pour fonctionner : ça doit toujours être un champ typé dédié.
    """

    # Entrée du système
    specification: str  # peut être vide : dans ce cas, l'Analyste est sauté
    selected_tests: Optional[list[str]]  # None/vide = toute la suite

    # Suggestions de l'Analyste — jamais exécutées, juste indicatif (voir
    # agents/analyste.py). Le nom des champs est conservé pour ne pas casser
    # le schéma, mais leur rôle a changé depuis le pivot.
    test_cases: list[TestCase]
    couverture_jugee_suffisante: Optional[bool]

    # Résultats RÉELS de la suite maisoncarmenta-qa (agents/executeur.py)
    execution_results: list[ExecutionResult]

    # Catégorisation des échecs réels (agents/triage.py)
    triage: list[TriageEntry]

    report: Optional[Report]

    # Routage décidé par le superviseur à chaque tour
    next_agent: NextAgent

    # Traçabilité (accumulé automatiquement par LangGraph via add_messages)
    messages: Annotated[list, add_messages]

    # --- Réservé pour V2+, non peuplé par aucun agent actuel ---
    test_data_handles: Optional[list[str]]  # Agent Data : identifiants des
    # données de test créées, à nettoyer en fin de run
