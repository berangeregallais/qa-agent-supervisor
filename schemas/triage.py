from typing import Literal

from pydantic import BaseModel, Field


class TriageEntry(BaseModel):
    """Catégorisation d'un échec réel par l'Agent Triage."""

    test_id: str
    categorie: Literal["bug_produit", "test_fragile", "flaky", "environnement"]
    confiance: float = Field(ge=0, le=1, description="0 = aucune certitude, 1 = certitude totale")
    justification: str


class TriageResult(BaseModel):
    """Format de sortie structuré attendu de l'Agent Triage."""

    entries: list[TriageEntry]
