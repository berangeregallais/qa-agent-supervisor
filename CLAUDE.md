# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A multi-agent pipeline (LangGraph Supervisor pattern + Claude API) that drives and analyzes an **external** Playwright/pytest suite. It contains no tests of its own against `maisoncarmenta.com` — that suite lives in the sibling repository `../maisoncarmenta-qa`, which must exist alongside this one, with its own virtualenv already installed (`maisoncarmenta-qa/.venv/Scripts/python.exe`). `agents/executor.py` hardcodes that relative path (`TARGET_PROJECT`); nothing here is reusable against another codebase without editing that constant.

## Commands

Everything below runs from this repo's own `.venv` (Windows paths; adjust `Scripts/python.exe` → `bin/python` on macOS/Linux):

```powershell
# One-time setup
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env   # then fill in ANTHROPIC_API_KEY

# Run the full test suite (of the agents themselves — mocked, no real API/pytest cost)
.venv\Scripts\python.exe -m pytest -v

# Run a single test
.venv\Scripts\python.exe -m pytest tests/test_triage.py::TestDeterministicFlakyDetection::test_recovered_flaky_is_categorized_without_any_llm_call -v

# Run the pipeline via CLI (makes REAL Claude API calls and a REAL pytest run against maisoncarmenta-qa)
.venv\Scripts\python.exe main.py "optional natural-language specification"
.venv\Scripts\python.exe main.py "" --tests "tests/test_homepage.py::test_homepage_loads[chromium]"

# Run the web interface (same real costs as above, via the browser instead of the CLI)
start.bat
# or directly:
.venv\Scripts\python.exe server.py   # then open http://127.0.0.1:8000
```

There is no build/lint step configured in this repo.

## Architecture

### The graph

`orchestrator/graph.py` wires a LangGraph `StateGraph` in the hub-and-spoke **Supervisor pattern**: every agent node always returns to `supervisor`, which decides the next node via a Claude Structured Outputs call (`orchestrator/supervisor.py`, `SupervisorDecision`). There is no fixed linear order enforced in code — the routing logic lives entirely in the Supervisor's system prompt plus `_summarize_state()`, which turns the current `QAOrchestratorState` into plain-language facts the LLM reasons over (missing results, failures present, reruns present, triage/report already done, previous loop-back already happened). When adding or changing what an agent does, update `_summarize_state()` too, or the Supervisor won't "see" the new state.

Two entry points build and run this graph:

- `orchestrator/runner.run_pipeline()` — blocking, used by `main.py` (CLI).
- `orchestrator/runner.run_pipeline_cancelable()` — iterates `graph.stream()` and checks a `threading.Event` between steps, used by `server.py` so a run can be cancelled from the web UI mid-flight. The Executor's pytest subprocess specifically is killed directly (`agents.executor.cancel_current_execution()`) since it's the only step long enough for a few seconds of lag to matter; other in-flight Claude calls are simply allowed to finish.

### The four agents (`agents/`) + the state contract (`orchestrator/state.py`)

`QAOrchestratorState` is the typed contract every node reads/writes. Work data (Pydantic models from `schemas/`) and the `messages` trace log are deliberately separate: `messages` is for human/Supervisor observability only, never a place to stash something an agent needs to function.

- **`analyst.py`** — suggests NEW test ideas from `state["specification"]`, cross-checked against the real existing suite (`executor.list_available_tests()`) so it never re-suggests something already covered. Output is never executed; it's the `test_cases` field, meant for human review.
- **`executor.py`** — runs the real `pytest` suite in `../maisoncarmenta-qa` as a subprocess, parses the resulting JUnit XML into `ExecutionResult` objects. `_extract_error_text()` deliberately prefers the `<failure>` element's full text over its truncated `message` attribute — the message attribute alone was a bug found while building this. Also reads `rerun-counts.json` (written by a `pytest_runtest_logreport` hook in `maisoncarmenta-qa`'s own `conftest.py`, since standard JUnit XML does not preserve rerun counts) to know which passing tests only passed after a retry.
- **`triage.py`** — a test that failed then passed within the same run (`passed and reruns > 0`) is categorized `"flaky"` **deterministically, with no LLM call** — that's direct proof, not a judgment call. Only tests still failing after all reruns are sent to Claude for categorization (`product_bug` / `brittle_test` / `flaky` / `environment`).
- **`reporter.py`** — produces a `Report` with two parallel summaries: `summary` (technical, for dev/QA) and `executive_summary` (max 3 sentences, no jargon, for non-technical stakeholders). Keep these genuinely separate in content, not just length.
- **`data.py`** — intentionally just a docstring, not implemented. Read it before proposing a "Data agent": the target site's catalog is hardcoded in its own source (not DB-backed) and its stock/price is read server-side, so `page.route()` can't intercept it — a safe version needs a separate staging environment, which is out of scope here.

### Key constraints that shape the code

- **No test-code generation, anywhere.** An earlier version generated Playwright code from suggested test cases; abandoned because it didn't reliably follow the Page Object Model and produced more false failures than signal. The Analyst only ever produces natural-language suggestions for a human to write by hand.
- **Only one pipeline run at a time.** `agents/executor.py` tracks a single module-level `_current_process`; `server.py`'s `POST /api/run` enforces this at the API level too (409 if a run is already `"running"` in the `RUNS` dict), both because a second concurrent subprocess would corrupt cancellation for the first run and because each run spends real Claude credits.
- **Prompt caching.** Every agent's system prompt is sent with `cache_control: {"type": "ephemeral"}` — preserve that when editing prompts, since the Supervisor alone is called multiple times per run.

### Tests (`tests/`)

Everything that touches the Anthropic API or a real `pytest` subprocess is mocked with `unittest.mock.patch` — patched at the point of use inside the module under test (e.g. `agents.triage.anthropic.Anthropic`, `server.list_available_tests`), not at the original definition. `tests/conftest.py` provides `junit_xml_factory`, `execution_result_factory`, and `report_factory` fixtures used throughout. Note that `server.RUNS` is a module-level dict shared across the whole test session; the `client` fixture in `tests/test_server.py` clears it before each test so a run left `"running"` by one test can't trip the concurrency guard in another.
