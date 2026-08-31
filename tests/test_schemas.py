"""Tests des contrats de données (Pydantic) — les règles de validation
sont le seul rempart contre une réponse LLM malformée qui se propagerait
silencieusement dans le reste du pipeline."""

import pytest
from pydantic import ValidationError

from schemas.execution_result import ExecutionResult
from schemas.report import Report
from schemas.triage import TriageEntry


class TestTriageEntry:
    def test_valid_entry_is_accepted(self):
        entry = TriageEntry(
            test_id="tests/a.py::b", categorie="bug_produit", confiance=0.8, justification="ok"
        )
        assert entry.confiance == 0.8

    @pytest.mark.parametrize("confiance", [-0.1, 1.1, 2.0, -5])
    def test_confidence_outside_zero_one_is_rejected(self, confiance):
        with pytest.raises(ValidationError):
            TriageEntry(
                test_id="x", categorie="flaky", confiance=confiance, justification="ok"
            )

    @pytest.mark.parametrize("confiance", [0.0, 1.0, 0.5])
    def test_confidence_boundaries_are_accepted(self, confiance):
        entry = TriageEntry(test_id="x", categorie="flaky", confiance=confiance, justification="ok")
        assert entry.confiance == confiance

    def test_unknown_category_is_rejected(self):
        with pytest.raises(ValidationError):
            TriageEntry(test_id="x", categorie="pas_une_vraie_categorie", confiance=0.5, justification="ok")


class TestExecutionResult:
    def test_reruns_defaults_to_zero(self):
        result = ExecutionResult(
            test_id="x", titre="x", passed=True, duree_secondes=1.0,
            message_erreur="", fichier="tests/x.py",
        )
        assert result.reruns == 0


class TestReport:
    def test_suggestions_couverture_defaults_to_empty_list(self):
        report = Report(
            resume="ok", resume_direction="ok", total=1, reussis=1, echoues=0,
            details=[], recommandations=[],
        )
        assert report.suggestions_couverture == []

    def test_missing_resume_is_rejected(self):
        with pytest.raises(ValidationError):
            Report(
                resume_direction="ok", total=1, reussis=1, echoues=0,
                details=[], recommandations=[],
            )  # resume manquant

    def test_missing_resume_direction_is_rejected(self):
        with pytest.raises(ValidationError):
            Report(
                resume="ok", total=1, reussis=1, echoues=0,
                details=[], recommandations=[],
            )  # resume_direction manquant, oubli fréquent vu que resume existe déjà
