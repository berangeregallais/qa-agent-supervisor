"""Agent Analyste : spécification en langage naturel -> suggestions de test.

Depuis le pivot, ces cas de test ne sont JAMAIS exécutés automatiquement —
l'Exécuteur lance la vraie suite existante, indépendamment de ce que
l'Analyste propose ici. Son rôle devient : repérer des angles de couverture
qu'un humain n'a peut-être pas encore ajoutés à la suite réelle, à valider
et écrire à la main avant tout ajout — jamais du code généré et exécuté
sans revue.
"""

import anthropic

from orchestrator.state import QAOrchestratorState
from schemas.test_case import TestCaseList

MODEL = "claude-opus-5"

ANALYSTE_SYSTEM_PROMPT = """Tu es l'Agent Analyste d'une équipe de QA \
automation. À partir d'une spécification ou d'une user story, tu proposes \
une liste de PISTES de test (chemin nominal ET au moins un cas limite ou \
négatif) — ce sont des suggestions destinées à être lues et validées par un \
humain, jamais exécutées automatiquement. Chaque piste doit être assez \
précise pour qu'un humain sache immédiatement si elle est déjà couverte par \
la suite existante ou non. Évalue aussi honnêtement si ta couverture \
suggérée te semble suffisante par rapport à la spécification."""


def analyste_node(state: QAOrchestratorState) -> QAOrchestratorState:
    client = anthropic.Anthropic()

    response = client.messages.parse(
        model=MODEL,
        max_tokens=8192,
        system=[
            {
                "type": "text",
                "text": ANALYSTE_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {"role": "user", "content": f"Spécification :\n\n{state['specification']}"}
        ],
        output_format=TestCaseList,
    )

    result = response.parsed_output

    return {
        **state,
        "test_cases": result.test_cases,
        "couverture_jugee_suffisante": result.couverture_jugee_suffisante,
        "messages": [
            {
                "role": "assistant",
                "content": f"[Analyste] {len(result.test_cases)} cas de test générés "
                f"(couverture jugée suffisante : {result.couverture_jugee_suffisante}).",
            }
        ],
    }
