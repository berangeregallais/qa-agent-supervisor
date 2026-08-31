"""Agent Triage : catégorise les échecs réels et les tests flaky prouvés.

Deux mécanismes distincts, volontairement séparés :
1. Un test qui a échoué puis réussi dans le même run (reruns > 0, passed) est
   flaky par PREUVE directe — aucun appel LLM n'est nécessaire, ni
   souhaitable : deviner ce qu'on sait déjà avec certitude n'apporterait
   rien et coûterait un appel API pour rien.
2. Un test encore en échec après tous les reruns disponibles nécessite une
   vraie interprétation (bug produit ? test fragile ? environnement ?) — là,
   et seulement là, on interroge Claude.
"""

import anthropic

from orchestrator.state import QAOrchestratorState
from schemas.triage import TriageEntry, TriageResult

MODEL = "claude-opus-5"

TRIAGE_SYSTEM_PROMPT = """Tu es l'Agent Triage d'une équipe de QA \
automation. On te soumet uniquement des tests ENCORE en échec après \
plusieurs tentatives (le cas des tests qui ont fini par réussir après un \
rerun est déjà traité ailleurs, avec certitude — tu ne le vois jamais ici).

Pour chaque échec persistant, détermine la catégorie la plus probable :
- "bug_produit" : un vrai défaut de l'application testée.
- "test_fragile" : un locator ou une assertion cassée par un changement \
d'UI légitime — pas un vrai bug, le test doit être corrigé.
- "flaky" : un échec probablement intermittent malgré la persistance sur ce \
run (ex. dépendance réseau/timing qui a simplement eu de la malchance à \
chaque tentative).
- "environnement" : panne réseau, service indisponible, quota — sans \
rapport avec le code testé ou l'application.

Donne un score de confiance entre 0 et 1 et justifie ta décision en une \
phrase, à partir du seul message d'erreur fourni. Sois honnête : en cas de \
doute, un score de confiance bas vaut mieux qu'une fausse certitude."""


def triage_node(state: QAOrchestratorState) -> QAOrchestratorState:
    results = state["execution_results"]

    # 1. Preuve directe, aucun LLM nécessaire.
    recovered_flaky = [r for r in results if r.passed and r.reruns > 0]
    entries: list[TriageEntry] = [
        TriageEntry(
            test_id=r.test_id,
            categorie="flaky",
            confiance=1.0,
            justification=(
                f"A échoué {r.reruns} fois avant de réussir, dans le même run : "
                "flakiness prouvée empiriquement, pas supposée."
            ),
        )
        for r in recovered_flaky
    ]

    # 2. Échecs définitifs : jugement nécessaire.
    still_failing = [r for r in results if not r.passed]
    if still_failing:
        client = anthropic.Anthropic()
        failures_summary = "\n\n".join(
            f"- {r.test_id} (a échoué {r.reruns + 1} fois au total, sans jamais réussir)\n"
            f"  Message d'erreur : {r.message_erreur[:800]}"
            for r in still_failing
        )

        response = client.messages.parse(
            model=MODEL,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": TRIAGE_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {"role": "user", "content": f"Échecs persistants à catégoriser :\n\n{failures_summary}"}
            ],
            output_format=TriageResult,
        )
        entries.extend(response.parsed_output.entries)

    return {
        **state,
        "triage": entries,
        "messages": [
            {
                "role": "assistant",
                "content": f"[Triage] {len(recovered_flaky)} flaky prouvé(s) par rerun, "
                f"{len(still_failing)} échec(s) persistant(s) catégorisé(s) par analyse.",
            }
        ],
    }
