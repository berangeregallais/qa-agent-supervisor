"""Agent Rapporteur : résultats réels + triage + suggestions -> rapport final."""

import anthropic

from orchestrator.state import QAOrchestratorState
from schemas.report import Report

MODEL = "claude-opus-5"

RAPPORTEUR_SYSTEM_PROMPT = """Tu es l'Agent Rapporteur d'une équipe de QA \
automation. Tu reçois trois sources, à ne jamais mélanger :
1. Les résultats RÉELS d'exécution de la vraie suite de tests (ce qui s'est
   vraiment passé).
2. Le triage des échecs réels, avec une catégorie et un score de confiance
   pour chacun (bug produit / test fragile / flaky / environnement).
3. Des pistes de test SUGGÉRÉES par l'Analyste, jamais exécutées — à ne
   présenter que comme des idées à valider par un humain, jamais comme des
   résultats.

Rédige un rapport de synthèse en français, professionnel et actionnable :
pour chaque échec réel, une recommandation concrète tenant compte de sa
catégorie de triage (ne recommande pas la même chose pour un bug produit et
pour un test fragile). Mets les suggestions de l'Analyste dans
suggestions_couverture, jamais dans les détails d'exécution."""


def rapporteur_node(state: QAOrchestratorState) -> QAOrchestratorState:
    client = anthropic.Anthropic()

    triage_by_id = {t.test_id: t for t in (state.get("triage") or [])}

    results_summary = "\n\n".join(
        f"- {r.test_id} : {'PASS' if r.passed else 'FAIL'} ({r.duree_secondes:.2f}s)\n"
        f"  Message : {r.message_erreur[:400]}\n"
        + (
            f"  Triage : {triage_by_id[r.test_id].categorie} "
            f"(confiance {triage_by_id[r.test_id].confiance:.2f}) — "
            f"{triage_by_id[r.test_id].justification}"
            if not r.passed and r.test_id in triage_by_id
            else ""
        )
        for r in state["execution_results"]
    )

    suggestions = "\n".join(
        f"- {tc.titre} : {tc.description}" for tc in (state.get("test_cases") or [])
    )

    response = client.messages.parse(
        model=MODEL,
        max_tokens=8192,
        system=[
            {
                "type": "text",
                "text": RAPPORTEUR_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    f"Résultats réels et triage :\n\n{results_summary}\n\n"
                    f"Pistes suggérées par l'Analyste (non vérifiées) :\n\n{suggestions}"
                ),
            }
        ],
        output_format=Report,
    )

    report = response.parsed_output

    return {
        **state,
        "report": report,
        "messages": [{"role": "assistant", "content": "[Rapporteur] Rapport final généré."}],
    }
