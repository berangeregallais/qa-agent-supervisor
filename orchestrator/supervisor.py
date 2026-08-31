"""Le nœud Superviseur : décide, à chaque tour, quel agent doit agir.

Utilise les Structured Outputs de l'API Claude (`messages.parse` + un modèle
Pydantic) plutôt que du tool-use ou du texte libre : on veut UNE décision
fiable parmi 5 valeurs possibles, pas un appel de fonction avec effet de
bord ni un texte à parser à la main.
"""

from typing import Literal

import anthropic
from pydantic import BaseModel

from orchestrator.state import QAOrchestratorState

MODEL = "claude-opus-5"

SUPERVISOR_SYSTEM_PROMPT = """Tu es le superviseur d'une équipe d'agents de \
QA automation. Tu ne fais AUCUN travail toi-même — tu décides uniquement \
quel agent doit agir ensuite, en te basant sur l'état actuel.

Agents disponibles :
- "analyste" : propose des pistes de test suggérées à partir d'une
  spécification (jamais exécutées automatiquement). À choisir UNIQUEMENT si
  une spécification a été fournie (sinon il n'y a rien à analyser — passe
  directement à l'exécuteur) ET qu'aucune piste n'existe encore, OU que les
  pistes existantes ont été jugées insuffisantes par l'Analyste lui-même
  (couverture_jugee_suffisante = false) ET qu'on ne les a pas déjà
  régénérées une fois (regarde le journal des messages pour vérifier).
- "executeur" : lance la VRAIE suite Playwright existante (aucune
  génération de code). À choisir si aucun résultat d'exécution n'est encore
  disponible, indépendamment de l'état des pistes de l'Analyste.
- "triage" : catégorise chaque échec réel ET chaque test qui a dû être
  relancé (bug produit / test fragile / flaky / environnement). À choisir
  si des résultats d'exécution existent, qu'au moins un test a échoué OU
  qu'au moins un test a eu besoin d'un rerun pour réussir, et qu'aucun
  triage n'a encore été fait.
- "rapporteur" : compile tout en rapport final. À choisir si des résultats
  d'exécution existent ET (aucun échec ni rerun, OU le triage est déjà
  fait), et qu'aucun rapport n'a encore été rédigé.
- "FINISH" : à choisir uniquement si un rapport final existe déjà.

Ne choisis JAMAIS un agent dont le travail est déjà fait pour ce tour — \
base-toi strictement sur ce qui manque dans l'état fourni. En cas de doute \
entre reboucler vers l'Analyste et avancer vers l'Exécuteur, ne reboucle \
qu'une seule fois maximum pour éviter une boucle infinie."""


class SupervisorDecision(BaseModel):
    next_agent: Literal["analyste", "executeur", "triage", "rapporteur", "FINISH"]
    reasoning: str


def _summarize_state(state: QAOrchestratorState) -> str:
    already_looped_back = any(
        "reboucl" in str(getattr(m, "content", m)).lower()
        for m in state.get("messages", [])
    )
    execution_results = state.get("execution_results") or []
    has_failures = any(not r.passed for r in execution_results)
    has_reruns = any(r.reruns > 0 for r in execution_results)

    return (
        f"Spécification fournie : {'oui' if state.get('specification') else 'non'}\n"
        f"Nombre de pistes suggérées par l'Analyste : {len(state.get('test_cases') or [])}\n"
        f"Couverture jugée suffisante par l'Analyste : "
        f"{state.get('couverture_jugee_suffisante')}\n"
        f"Nombre de résultats d'exécution réels : {len(execution_results)}\n"
        f"Au moins un échec réel : {has_failures}\n"
        f"Au moins un test a eu besoin d'un rerun : {has_reruns}\n"
        f"Triage déjà effectué : {'oui' if state.get('triage') else 'non (ou rien à catégoriser)'}\n"
        f"Rapport final déjà généré : {'oui' if state.get('report') else 'non'}\n"
        f"A déjà rebouclé vers l'Analyste : {already_looped_back}\n"
    )


def supervisor_node(state: QAOrchestratorState) -> QAOrchestratorState:
    client = anthropic.Anthropic()

    response = client.messages.parse(
        model=MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SUPERVISOR_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": f"État actuel :\n\n{_summarize_state(state)}\n"
                "Quel agent doit agir maintenant ?",
            }
        ],
        output_format=SupervisorDecision,
    )

    decision = response.parsed_output

    return {
        **state,
        "next_agent": decision.next_agent,
        "messages": [
            {
                "role": "assistant",
                "content": f"[Superviseur] -> {decision.next_agent} ({decision.reasoning})",
            }
        ],
    }


def route_from_supervisor(state: QAOrchestratorState) -> str:
    return state["next_agent"]
