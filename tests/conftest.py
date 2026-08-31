"""Fixtures partagées pour les tests des agents."""

import pytest

from schemas.execution_result import ExecutionResult


@pytest.fixture
def junit_xml_factory(tmp_path):
    """Écrit un JUnit XML minimal mais réaliste (format réellement produit
    par pytest, vérifié en direct plus tôt dans le projet) et renvoie son
    chemin. `cases` est une liste de dicts : name, classname, time,
    outcome ("passed" | "failed" | "error" | "skipped"), message (optionnel).
    """

    def _write(cases: list[dict]) -> "Path":  # noqa: F821 - annotation en chaîne
        testcases_xml = []
        for case in cases:
            name = case["name"]
            classname = case.get("classname", "tests.test_example")
            time = case.get("time", "1.0")
            outcome = case.get("outcome", "passed")
            message = case.get("message", "erreur simulée")

            if outcome == "passed":
                body = ""
            elif outcome == "failed":
                body = f'<failure message="{message}">{message}</failure>'
            elif outcome == "error":
                body = f'<error message="{message}">{message}</error>'
            elif outcome == "skipped":
                body = '<skipped message="skip simulé"></skipped>'
            else:
                raise ValueError(f"outcome inconnu : {outcome}")

            testcases_xml.append(
                f'<testcase classname="{classname}" name="{name}" time="{time}">{body}</testcase>'
            )

        xml = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<testsuites name="pytest tests">'
            '<testsuite name="pytest" errors="0" failures="0" skipped="0" '
            f'tests="{len(cases)}" time="1.0">'
            + "".join(testcases_xml)
            + "</testsuite></testsuites>"
        )

        path = tmp_path / "junit-report.xml"
        path.write_text(xml, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def execution_result_factory():
    """Construit un ExecutionResult avec des valeurs par défaut sensées,
    pour ne répéter que ce qui varie réellement d'un test à l'autre."""

    def _make(**overrides) -> ExecutionResult:
        defaults = dict(
            test_id="tests/test_example.py::test_something[chromium]",
            titre="test_something",
            passed=True,
            duree_secondes=1.0,
            message_erreur="",
            fichier="tests/test_example.py",
            reruns=0,
        )
        defaults.update(overrides)
        return ExecutionResult(**defaults)

    return _make
