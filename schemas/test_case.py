from typing import Literal

from pydantic import BaseModel, Field


class TestCase(BaseModel):
    """Un cas de test produit par l'Agent Analyste.

    Suffisamment précis pour qu'un autre agent (Exécuteur) en dérive du code
    Playwright sans avoir à interpréter/deviner quoi que ce soit.
    """

    id: str = Field(description="Identifiant court et unique, ex: TC-001")
    titre: str
    description: str
    etapes: list[str] = Field(description="Étapes numérotées, langage naturel")
    resultat_attendu: str
    priorite: Literal["haute", "moyenne", "basse"]


class TestCaseList(BaseModel):
    """Format de sortie structuré attendu de l'Agent Analyste."""

    test_cases: list[TestCase]
    couverture_jugee_suffisante: bool = Field(
        description=(
            "L'Analyste s'auto-évalue : est-ce que ces cas couvrent "
            "raisonnablement la spécification fournie ? Sert au Superviseur "
            "pour décider s'il faut repasser par l'Analyste plus tard."
        )
    )
