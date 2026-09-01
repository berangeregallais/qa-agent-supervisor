"""Tests for the FastAPI API, via TestClient — no real pytest subprocess,
no real Claude call: `list_available_tests` and `run_pipeline_cancelable`
are mocked where server.py imported them (server.xxx), not at their
original definition — the classic Python mocking trap, otherwise the patch
never takes effect."""

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import server


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
    raise TimeoutError(f"Run {run_id} did not finish within the allotted time")


class TestGetTests:
    def test_returns_the_test_list(self, client):
        with patch.object(server, "list_available_tests", return_value=["a::b", "a::c"]):
            res = client.get("/api/tests")

        assert res.status_code == 200
        assert res.json() == ["a::b", "a::c"]

    def test_returns_500_when_collection_fails(self, client):
        with patch.object(server, "list_available_tests", side_effect=RuntimeError("pytest not found")):
            res = client.get("/api/tests")

        assert res.status_code == 500
        assert "pytest not found" in res.json()["detail"]


class TestGetLastRun:
    def test_returns_the_stored_timestamp(self, client):
        with patch.object(server, "get_last_run_timestamp", return_value="2026-08-31T10:00:00+00:00"):
            res = client.get("/api/last-run")

        assert res.json() == {"timestamp": "2026-08-31T10:00:00+00:00"}

    def test_returns_null_when_no_run_yet(self, client):
        with patch.object(server, "get_last_run_timestamp", return_value=None):
            res = client.get("/api/last-run")

        assert res.json() == {"timestamp": None}


class TestGetHistory:
    def test_returns_the_stored_history(self, client):
        fake_history = [{"timestamp": "t2", "total": 5, "passed": 5, "failed": 0, "summary": "ok"}]
        with patch.object(server, "get_history", return_value=fake_history):
            res = client.get("/api/history")

        assert res.json() == fake_history

    def test_returns_empty_list_before_any_run(self, client):
        with patch.object(server, "get_history", return_value=[]):
            res = client.get("/api/history")

        assert res.json() == []


class TestRunLifecycle:
    def test_successful_run_transitions_to_done_with_report(self, client, report_factory):
        fake_report = report_factory(summary="all is well")
        with patch.object(server, "run_pipeline_cancelable", return_value=fake_report):
            run_id = client.post("/api/run", json={"specification": "", "selected_tests": None}).json()["run_id"]
            final = _wait_until_done(client, run_id)

        assert final["status"] == "done"
        assert final["report"]["summary"] == "all is well"
        assert final["error"] is None

    def test_pipeline_exception_transitions_to_error(self, client):
        with patch.object(server, "run_pipeline_cancelable", side_effect=RuntimeError("missing API key")):
            run_id = client.post("/api/run", json={}).json()["run_id"]
            final = _wait_until_done(client, run_id)

        assert final["status"] == "error"
        assert "missing API key" in final["error"]
        assert final["report"] is None

    def test_none_result_transitions_to_cancelled(self, client):
        # run_pipeline_cancelable returns None when cancel_event was set
        # before a report could be produced (see orchestrator/runner.py).
        with patch.object(server, "run_pipeline_cancelable", return_value=None):
            run_id = client.post("/api/run", json={}).json()["run_id"]
            final = _wait_until_done(client, run_id)

        assert final["status"] == "cancelled"

    def test_unknown_run_id_returns_404(self, client):
        res = client.get("/api/run/nonexistent")
        assert res.status_code == 404

    def test_run_starts_immediately_without_waiting_for_completion(self, client, report_factory):
        # The POST must never block until the pipeline finishes — that's
        # what keeps /cancel responsive during a long run.
        def slow_pipeline(*args, **kwargs):
            time.sleep(1.0)
            return report_factory()

        with patch.object(server, "run_pipeline_cancelable", side_effect=slow_pipeline):
            start = time.monotonic()
            res = client.post("/api/run", json={})
            elapsed = time.monotonic() - start

        assert res.status_code == 200
        assert elapsed < 0.5  # well before the second the pipeline would take


class TestCancel:
    def test_cancel_unknown_run_id_returns_404(self, client):
        res = client.post("/api/run/nonexistent/cancel")
        assert res.status_code == 404

    def test_cancel_sets_the_event_and_attempts_to_kill_subprocess(self, client):
        def pipeline_checks_cancel(specification, selected_tests, cancel_event):
            # Waits for /cancel to have had time to be called.
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
