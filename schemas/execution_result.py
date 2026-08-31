from pydantic import BaseModel


class ExecutionResult(BaseModel):
    """Le résultat d'UN test réel de la suite maisoncarmenta-qa, produit par
    l'Agent Exécuteur à partir du vrai run pytest (JUnit XML) — plus de code
    généré ni de fichier ad hoc depuis le pivot."""

    test_id: str  # nodeid pytest, ex: tests/test_homepage.py::test_homepage_loads[chromium]
    titre: str
    passed: bool
    duree_secondes: float
    message_erreur: str
    fichier: str
    # Nombre de reruns pytest-rerunfailures avant le résultat final. > 0 même
    # sur un test `passed` = preuve empirique de flakiness (a échoué au
    # moins une fois avant de réussir dans le même run) — pas une supposition.
    reruns: int = 0
