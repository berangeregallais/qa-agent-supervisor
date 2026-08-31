"""Agent Data (V2, NON implémenté) — interface réservée.

Rôle prévu : avant l'Exécuteur, créer les données de test nécessaires (ex :
un produit de test en base, un compte utilisateur jetable) via l'API/DB du
projet cible, et retourner leurs identifiants dans
`state["test_data_handles"]`. Après le Rapporteur (ou en cas d'échec fatal
du graphe — prévoir un nœud de nettoyage dans un `finally` applicatif, pas
seulement un chemin heureux), supprimer ces mêmes données par leurs
identifiants pour ne rien laisser de résiduel en base.

Se brancherait dans le graphe entre "analyste" et "executeur" côté création,
et en tout dernier (même après "rapporteur", avant FINISH) côté nettoyage.

def data_setup_node(state: QAOrchestratorState) -> QAOrchestratorState:
    raise NotImplementedError

def data_teardown_node(state: QAOrchestratorState) -> QAOrchestratorState:
    raise NotImplementedError
"""
