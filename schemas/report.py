from typing import Literal, Optional

from pydantic import BaseModel


class ReportEntry(BaseModel):
    test_id: str
    titre: str
    statut: Literal["réussi", "échoué"]
    categorie: Optional[str] = None  # renseigné pour les échecs, via l'Agent Triage
    commentaire: str


class Report(BaseModel):
    """Le rapport final, produit par l'Agent Rapporteur.

    Deux résumés distincts, pour deux lecteurs différents — jamais un seul
    texte qui essaie de servir les deux à la fois :
    - `resume` : niveau développeur/QA, détails techniques utiles pour agir.
    - `resume_direction` : 3 lignes maximum, orienté statut/risque/décision,
      sans jargon technique — ce qu'on montrerait à quelqu'un qui doit
      décider si on met en production, pas comment corriger un test.
    """

    resume: str
    resume_direction: str
    total: int
    reussis: int
    echoues: int
    details: list[ReportEntry]
    # Idées de l'Analyste non couvertes par la suite actuelle — jamais
    # exécutées ni vérifiées, à valider par un humain avant tout ajout réel.
    suggestions_couverture: list[str] = []
    recommandations: list[str]
