"""Serveur web local : interface pour lancer le pipeline sans terminal.

Lancement : .venv\\Scripts\\python.exe server.py
Puis ouvrir http://127.0.0.1:8000 dans un navigateur.

La clé API est lue depuis un fichier .env (jamais depuis l'interface, pour
ne jamais l'exposer côté navigateur) — voir .env.example.

Chaque run tourne dans un thread d'arrière-plan (pas dans la requête HTTP
elle-même) : c'est ce qui permet à /api/run/{id}/cancel de répondre tout de
suite, même pendant qu'un run est en cours — si le run bloquait la requête
HTTP comme avant, la requête d'annulation resterait coincée derrière lui.
"""

import threading
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()  # doit s'exécuter avant tout import qui construit un client Anthropic

from agents.executeur import cancel_current_execution, list_available_tests  # noqa: E402
from orchestrator.runner import get_history, get_last_run_timestamp, run_pipeline_cancelable  # noqa: E402

WEB_DIR = Path(__file__).resolve().parent / "web"

app = FastAPI(title="Maison Carmenta — QA multi-agent")


class RunRequest(BaseModel):
    specification: str = ""
    selected_tests: Optional[list[str]] = None


class RunState:
    def __init__(self) -> None:
        self.status = "running"  # running | done | cancelled | error
        self.report: Optional[dict] = None
        self.error: Optional[str] = None
        self.cancel_event = threading.Event()


RUNS: dict[str, RunState] = {}
RUNS_LOCK = threading.Lock()


def _execute(run_id: str, specification: str, selected_tests: Optional[list[str]]) -> None:
    state = RUNS[run_id]
    try:
        report = run_pipeline_cancelable(specification, selected_tests, state.cancel_event)
    except Exception as exc:  # noqa: BLE001 — remonté tel quel à l'interface
        with RUNS_LOCK:
            state.status = "error"
            state.error = str(exc)
        return

    with RUNS_LOCK:
        if state.cancel_event.is_set() or report is None:
            state.status = "cancelled"
        else:
            state.status = "done"
            state.report = report.model_dump()


@app.get("/api/tests")
def get_tests() -> list[str]:
    try:
        return list_available_tests()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/last-run")
def get_last_run() -> dict:
    return {"timestamp": get_last_run_timestamp()}


@app.get("/api/history")
def get_run_history() -> list[dict]:
    return get_history()


@app.post("/api/run")
def post_run(body: RunRequest) -> dict:
    run_id = uuid.uuid4().hex[:12]
    RUNS[run_id] = RunState()
    thread = threading.Thread(
        target=_execute, args=(run_id, body.specification, body.selected_tests), daemon=True
    )
    thread.start()
    return {"run_id": run_id}


@app.get("/api/run/{run_id}")
def get_run(run_id: str) -> dict:
    state = RUNS.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run introuvable.")
    return {"status": state.status, "report": state.report, "error": state.error}


@app.post("/api/run/{run_id}/cancel")
def post_cancel(run_id: str) -> dict:
    state = RUNS.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run introuvable.")
    state.cancel_event.set()
    killed_subprocess = cancel_current_execution()
    return {"ok": True, "killed_subprocess": killed_subprocess}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
