"""Agent Analyste : spécification en langage naturel -> suggestions de test.

Depuis le pivot, ces cas de test ne sont JAMAIS exécutés automatiquement —
l'Exécuteur lance la vraie suite existante, indépendamment de ce que
l'Analyste propose ici. Son rôle devient : repérer des angles de couverture
qu'un humain n'a peut-être pas encore ajoutés à la suite réelle, à valider
et écrire à la main avant tout ajout — jamais du code généré et exécuté
sans revue.

Il connaît la VRAIE liste des tests existants (via list_available_tests,
la même fonction que celle qui alimente les cases à cocher de l'interface)
pour ne jamais reproposer une piste déjà couverte — sans ça, il suggère à
l'aveugle et peut redemander ce qui existe déjà.
"""

import anthropic

from agents.executeur import list_available_tests
from orchestrator.state import QAOrchestratorState
from schemas.test_case import TestCaseList

MODEL = "claude-opus-5"

ANALYSTE_SYSTEM_PROMPT = """Tu es l'Agent Analyste d'une équipe de QA \
automation. On te fournit la liste RÉELLE des tests qui existent déjà dans \
la suite, et une spécification ou user story.

Règle impérative : ne suggère JAMAIS une piste déjà couverte par un test \
existant listé ci-dessous — vérifie systématiquement avant de proposer. Les \
noms de test sont explicites (ex: test_homepage_displays_all_collections) :
utilise-les pour déduire ce qui est déjà vérifié, pas seulement le nom du \
fichier.

Tu proposes une liste de PISTES de test NOUVELLES (chemin nominal ET au \
moins un cas limite ou négatif, non déjà couverts) — ce sont des \
suggestions destinées à être lues et validées par un humain, jamais \
exécutées automatiquement. Si la spécification est déjà entièrement \
couverte par les tests existants, renvoie une liste vide plutôt que de \
forcer une suggestion redondante. Évalue aussi honnêtement si la \
couverture suggérée (existante + nouvelle) te semble suffisante par \
rapport à la spécification."""


def _existing_tests_summary() -> str:
    try:
        tests = list_available_tests()
    except Exception:  # noqa: BLE001 — dégradation gracieuse, pas de spec sans Analyste
        return "(liste indisponible — impossible de vérifier les doublons)"

    if not tests:
        return "(aucun test existant trouvé)"
    return "\n".join(f"- {t}" for t in tests)


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
            {
                "role": "user",
                "content": (
                    f"Tests déjà existants dans la suite :\n\n{_existing_tests_summary()}\n\n"
                    f"Spécification :\n\n{state['specification']}"
                ),
            }
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
                "content": f"[Analyste] {len(result.test_cases)} piste(s) NOUVELLE(S) suggérée(s) "
                f"(non déjà couvertes) (couverture jugée suffisante : "
                f"{result.couverture_jugee_suffisante}).",
            }
        ],
    }
