"""Tests de l'API FastAPI, via TestClient — aucun vrai sous-processus
pytest, aucun vrai appel Claude : `list_available_tests` et
`run_pipeline_cancelable` sont mockés à l'endroit où server.py les a
importés (server.xxx), pas à leur définition d'origine — piège classique du
mocking Python sinon le patch ne prend pas effet."""

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import server
from schemas.report import Report


@pytest.fixture
def client():
    return TestClient(server.app)


def _wait_until_done(client, run_id: str, timeout: float = 2.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = client.get(f"/api/run/{run_id}").json()
        if data["status"] != "running":
            return data
        time.sleep(0.02)
    raise TimeoutError(f"Le run {run_id} n'a pas terminé dans le délai imparti")


class TestGetTests:
    def test_returns_the_test_list(self, client):
        with patch.object(server, "list_available_tests", return_value=["a::b", "a::c"]):
            res = client.get("/api/tests")

        assert res.status_code == 200
        assert res.json() == ["a::b", "a::c"]

    def test_returns_500_when_collection_fails(self, client):
        with patch.object(server, "list_available_tests", side_effect=RuntimeError("pytest introuvable")):
            res = client.get("/api/tests")

        assert res.status_code == 500
        assert "pytest introuvable" in res.json()["detail"]


class TestGetLastRun:
    def test_returns_the_stored_timestamp(self, client):
        with patch.object(server, "get_last_run_timestamp", return_value="2026-08-31T10:00:00+00:00"):
            res = client.get("/api/last-run")

        assert res.json() == {"timestamp": "2026-08-31T10:00:00+00:00"}

    def test_returns_null_when_no_run_yet(self, client):
        with patch.object(server, "get_last_run_timestamp", return_value=None):
            res = client.get("/api/last-run")

        assert res.json() == {"timestamp": None}


class TestRunLifecycle:
    def test_successful_run_transitions_to_done_with_report(self, client):
        fake_report = Report(
            resume="tout va bien", total=1, reussis=1, echoues=0, details=[], recommandations=[]
        )
        with patch.object(server, "run_pipeline_cancelable", return_value=fake_report):
            run_id = client.post("/api/run", json={"specification": "", "selected_tests": None}).json()["run_id"]
            final = _wait_until_done(client, run_id)

        assert final["status"] == "done"
        assert final["report"]["resume"] == "tout va bien"
        assert final["error"] is None

    def test_pipeline_exception_transitions_to_error(self, client):
        with patch.object(server, "run_pipeline_cancelable", side_effect=RuntimeError("clé API absente")):
            run_id = client.post("/api/run", json={}).json()["run_id"]
            final = _wait_until_done(client, run_id)

        assert final["status"] == "error"
        assert "clé API absente" in final["error"]
        assert final["report"] is None

    def test_none_result_transitions_to_cancelled(self, client):
        # run_pipeline_cancelable renvoie None quand le cancel_event a été
        # levé avant qu'un rapport n'existe (voir orchestrator/runner.py).
        with patch.object(server, "run_pipeline_cancelable", return_value=None):
            run_id = client.post("/api/run", json={}).json()["run_id"]
            final = _wait_until_done(client, run_id)

        assert final["status"] == "cancelled"

    def test_unknown_run_id_returns_404(self, client):
        res = client.get("/api/run/inexistant")
        assert res.status_code == 404

    def test_run_starts_immediately_without_waiting_for_completion(self, client):
        # Le POST ne doit jamais bloquer jusqu'à la fin du pipeline — c'est
        # ce qui permet à /cancel de rester réactif pendant un run long.
        def slow_pipeline(*args, **kwargs):
            time.sleep(1.0)
            return Report(resume="", total=0, reussis=0, echoues=0, details=[], recommandations=[])

        with patch.object(server, "run_pipeline_cancelable", side_effect=slow_pipeline):
            start = time.monotonic()
            res = client.post("/api/run", json={})
            elapsed = time.monotonic() - start

        assert res.status_code == 200
        assert elapsed < 0.5  # largement avant la seconde que prendrait le pipeline


class TestCancel:
    def test_cancel_unknown_run_id_returns_404(self, client):
        res = client.post("/api/run/inexistant/cancel")
        assert res.status_code == 404

    def test_cancel_sets_the_event_and_attempts_to_kill_subprocess(self, client):
        def pipeline_checks_cancel(specification, selected_tests, cancel_event):
            # Attend que /cancel ait eu le temps d'être appelé.
            for _ in range(100):
                if cancel_event.is_set():
                    return None
                time.sleep(0.01)
            return None

        with patch.object(server, "run_pipeline_cancelable", side_effect=pipeline_checks_cancel), \
             patch.object(server, "cancel_current_execution", return_value=True) as mock_cancel:
            run_id = client.post("/api/run", json={}).json()["run_id"]
            cancel_res = client.post(f"/api/run/{run_id}/cancel")
            final = _wait_until_done(client, run_id)

        assert cancel_res.status_code == 200
        assert cancel_res.json() == {"ok": True, "killed_subprocess": True}
        mock_cancel.assert_called_once()
        assert final["status"] == "cancelled"
