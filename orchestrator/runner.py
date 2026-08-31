"""Point d'entrée réutilisable du pipeline — partagé entre le CLI (main.py)
et le serveur web (server.py), pour ne jamais dupliquer la construction de
l'état initial."""

import json
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from orchestrator.graph import build_graph
from orchestrator.state import QAOrchestratorState
from schemas.report import Report

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
LAST_RUN_PATH = REPORTS_DIR / "last-run.json"
HISTORY_PATH = REPORTS_DIR / "history.json"

# Fichiers que _reset_reports_dir ne doit JAMAIS supprimer — ils doivent
# survivre à travers les runs, y compris un run annulé ou en erreur.
_PERSISTENT_FILENAMES = {LAST_RUN_PATH.name, HISTORY_PATH.name}

MAX_HISTORY_ENTRIES = 50


def _reset_reports_dir() -> None:
    # Nettoie les artefacts du run précédent (JUnit XML, compteur de
    # reruns...) sans jamais toucher last-run.json ni history.json : sinon
    # un run annulé (qui ne va jamais jusqu'à _record_completed_run)
    # effacerait la mémoire de tous les runs précédents sans jamais la
    # reconstruire. Bug réel trouvé en construisant l'historique.
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    for item in REPORTS_DIR.iterdir():
        if item.name in _PERSISTENT_FILENAMES:
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def _load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))


def get_history() -> list[dict]:
    """Renvoie les runs passés, du plus récent au plus ancien."""
    return list(reversed(_load_history()))


def _record_completed_run(report: Report) -> None:
    """Enregistre le run à la fois comme "dernier run" et dans l'historique
    — un seul point d'appel pour ne jamais faire l'un sans l'autre."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()

    LAST_RUN_PATH.write_text(json.dumps({"timestamp": timestamp}), encoding="utf-8")

    entries = _load_history()
    entries.append(
        {
            "timestamp": timestamp,
            "total": report.total,
            "reussis": report.reussis,
            "echoues": report.echoues,
            "resume": report.resume[:200],
        }
    )
    entries = entries[-MAX_HISTORY_ENTRIES:]  # évite une croissance illimitée
    HISTORY_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def get_last_run_timestamp() -> Optional[str]:
    if not LAST_RUN_PATH.exists():
        return None
    return json.loads(LAST_RUN_PATH.read_text(encoding="utf-8")).get("timestamp")


def _initial_state(specification: str, selected_tests: Optional[list[str]]) -> QAOrchestratorState:
    return {
        "specification": specification,
        "selected_tests": selected_tests or [],
        "test_cases": [],
        "couverture_jugee_suffisante": None,
        "execution_results": [],
        "triage": [],
        "report": None,
        "next_agent": "analyste",
        "messages": [],
        "test_data_handles": None,
    }


def run_pipeline(specification: str = "", selected_tests: Optional[list[str]] = None) -> Report:
    """Lance le graphe complet et renvoie le rapport final (usage CLI, pas
    annulable — voir run_pipeline_cancelable pour l'usage serveur web)."""
    _reset_reports_dir()

    graph = build_graph()
    final_state = graph.invoke(
        _initial_state(specification, selected_tests), config={"recursion_limit": 25}
    )

    if final_state["report"] is None:
        raise RuntimeError("Le pipeline s'est arrêté sans produire de rapport.")

    _record_completed_run(final_state["report"])
    return final_state["report"]


def run_pipeline_cancelable(
    specification: str,
    selected_tests: Optional[list[str]],
    cancel_event: threading.Event,
) -> Optional[Report]:
    """Comme run_pipeline, mais s'arrête entre deux étapes du graphe si
    `cancel_event` est levé pendant l'exécution. Renvoie None si annulé
    avant qu'un rapport n'ait pu être produit.

    Limite assumée : l'étape EN COURS n'est pas interrompue instantanément
    (un appel Claude en cours va à son terme, quelques secondes tout au
    plus) — seule la prochaine étape est empêchée de démarrer. L'exception
    est l'Exécuteur, dont le sous-processus pytest peut être tué directement
    (voir agents/executeur.cancel_current_execution), car c'est la seule
    étape assez longue pour que l'attente soit gênante.
    """
    _reset_reports_dir()

    graph = build_graph()
    initial = _initial_state(specification, selected_tests)
    accumulated_state: dict = dict(initial)

    for step in graph.stream(initial, config={"recursion_limit": 25}):
        for node_output in step.values():
            accumulated_state.update(node_output)

        if cancel_event.is_set():
            return None

    report = accumulated_state.get("report")
    if report is not None:
        _record_completed_run(report)
    return report
