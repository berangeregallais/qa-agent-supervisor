"""Agent Exécuteur : lance la VRAIE suite Playwright de maisoncarmenta-qa.

Pivot par rapport à la V1 (qui générait du code Playwright à la volée) : le
code généré ne respectait pas systématiquement le Page Object Model et
produisait plus de faux échecs (locators mal devinés) que de vrais signaux.
Cet agent n'écrit plus aucun test : il exécute la suite existante et
transforme le rapport JUnit XML de pytest en résultats structurés.

Active aussi pytest-rerunfailures (--reruns) : un test qui échoue puis
réussit dans le même run est une PREUVE de flakiness, pas une supposition —
voir conftest.py côté maisoncarmenta-qa pour le hook qui capte ce signal
(le JUnit XML standard ne le conserve pas).
"""

import json
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from orchestrator.state import QAOrchestratorState
from schemas.execution_result import ExecutionResult

# Référence au sous-processus pytest en cours, pour permettre une annulation
# immédiate depuis l'API (server.py) — c'est la seule étape du pipeline dont
# l'interruption réelle a un sens : les appels Claude, eux, sont trop courts
# pour valoir la peine d'être coupés en plein vol.
_current_process: subprocess.Popen | None = None
_process_lock = threading.Lock()


def cancel_current_execution() -> bool:
    """Termine le pytest en cours, s'il y en a un. Renvoie True si un
    processus a effectivement été interrompu."""
    with _process_lock:
        if _current_process is not None and _current_process.poll() is None:
            _current_process.terminate()
            return True
        return False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TARGET_PROJECT = PROJECT_ROOT.parent / "maisoncarmenta-qa"
TARGET_PYTHON = TARGET_PROJECT / ".venv" / "Scripts" / "python.exe"

REPORTS_DIR = PROJECT_ROOT / "reports"
JUNIT_PATH = REPORTS_DIR / "junit-report.xml"

TARGET_REPORTS_DIR = TARGET_PROJECT / "reports"
RERUN_COUNTS_PATH = TARGET_REPORTS_DIR / "rerun-counts.json"

RERUNS = 2
RERUNS_DELAY = 1


def _python_bin() -> str:
    return str(TARGET_PYTHON) if TARGET_PYTHON.exists() else "python"


def list_available_tests() -> list[str]:
    """Liste tous les node IDs pytest de la vraie suite, pour l'interface
    (cases à cocher) — jamais codée en dur, toujours lue depuis la vraie
    suite pour rester exacte si des tests sont ajoutés/retirés."""

    proc = subprocess.run(
        [_python_bin(), "-m", "pytest", "--collect-only", "-q"],
        cwd=TARGET_PROJECT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return [
        line.strip()
        for line in proc.stdout.splitlines()
        if line.strip() and "::" in line
    ]


def _parse_junit(junit_path: Path) -> list[ExecutionResult]:
    if not junit_path.exists():
        return []

    tree = ET.parse(junit_path)
    results: list[ExecutionResult] = []

    for testcase in tree.getroot().iter("testcase"):
        if testcase.find("skipped") is not None:
            continue  # un test explicitement skip n'est ni un succès ni un échec

        classname = testcase.get("classname", "")
        name = testcase.get("name", "")
        fichier = classname.replace(".", "/") + ".py"
        test_id = f"{fichier}::{name}"

        failure = testcase.find("failure")
        error = testcase.find("error")
        node = failure if failure is not None else error

        results.append(
            ExecutionResult(
                test_id=test_id,
                titre=name,
                passed=node is None,
                duree_secondes=float(testcase.get("time", "0")),
                message_erreur=(node.get("message", "") if node is not None else ""),
                fichier=fichier,
            )
        )

    return results


def _load_rerun_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def executeur_node(state: QAOrchestratorState) -> QAOrchestratorState:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if RERUN_COUNTS_PATH.exists():
        RERUN_COUNTS_PATH.unlink()  # ne pas hériter du run précédent

    selected = state.get("selected_tests") or []

    command = [
        _python_bin(), "-m", "pytest", "-v",
        f"--junitxml={JUNIT_PATH}",
        f"--reruns={RERUNS}",
        f"--reruns-delay={RERUNS_DELAY}",
        *selected,  # positional node IDs pytest ; vide = toute la suite
    ]

    global _current_process
    start = time.monotonic()
    with _process_lock:
        _current_process = subprocess.Popen(command, cwd=TARGET_PROJECT)
    try:
        _current_process.wait(timeout=600)
    finally:
        with _process_lock:
            _current_process = None
    duree_totale = time.monotonic() - start

    results = _parse_junit(JUNIT_PATH)
    rerun_counts = _load_rerun_counts(RERUN_COUNTS_PATH)
    for r in results:
        r.reruns = rerun_counts.get(r.test_id, 0)

    flaky_recovered = sum(1 for r in results if r.passed and r.reruns > 0)
    portee = f"{len(selected)} test(s) sélectionné(s)" if selected else "toute la suite"

    return {
        **state,
        "execution_results": results,
        "messages": [
            {
                "role": "assistant",
                "content": f"[Exécuteur] {portee}, exécuté en {duree_totale:.1f}s : "
                f"{len(results)} tests, {sum(r.passed for r in results)} réussis, "
                f"{flaky_recovered} récupéré(s) après rerun (flakiness prouvée).",
            }
        ],
    }
