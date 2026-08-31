"""Agent Détecteur (V2, NON implémenté) — interface réservée.

Rôle prévu : recevoir `execution_results` en entrée, examiner les échecs
pour distinguer "vrai bug applicatif" de "test devenu fragile" (locator
obsolète, changement de structure DOM). Écrirait `state["flaky_tests"]`
(liste de test_case_id jugés fragiles plutôt que réellement cassés) pour
que le Rapporteur les catégorise différemment.

Se brancherait dans le graphe entre "executeur" et "rapporteur" : le
Superviseur router ait vers "detecteur" si `execution_results` contient des
échecs ET que `flaky_tests` est encore `None`.

def detecteur_node(state: QAOrchestratorState) -> QAOrchestratorState:
    raise NotImplementedError
"""
