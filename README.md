# multi-agent-qa

A multi-agent pipeline (LangGraph + Claude API) that runs and analyzes the
Playwright tests of the **`maisoncarmenta-qa`** project — orchestration,
not duplication: this project contains no tests of its own.

## How the two projects fit together

```text
../maisoncarmenta-qa/     <- the REAL Playwright tests (Page Objects,
                              fixtures, pytest.ini). Can run standalone,
                              without this project.
./  (multi-agent-qa)      <- drives maisoncarmenta-qa from the outside:
                              runs pytest against it, reads its JUnit
                              report, has Claude agents analyze the
                              results, and displays everything in a web
                              interface.
```

The two folders must be **siblings** (side by side, same parent
directory) — `agents/executor.py` references `maisoncarmenta-qa` via a
relative path (`../maisoncarmenta-qa`).

## The pipeline

```text
Supervisor (LangGraph, Supervisor pattern)
  ├─ Analyst   : coverage suggestions from a spec — never executed
  ├─ Executor  : runs `pytest` against the REAL suite (no code generation)
  ├─ Triage    : categorizes real failures and flaky tests (via rerun)
  └─ Reporter  : final synthesis (results + suggestions, never mixed)
```

Brief history: a first version generated Playwright code on the fly from
suggested test cases. Abandoned — the generated code did not consistently
follow the Page Object Model and produced more false failures than real
signal. The current pivot runs the real suite instead.

## Installation (one-time)

```powershell
cd multi-agent-qa
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
notepad .env   # paste your ANTHROPIC_API_KEY
```

`maisoncarmenta-qa` must already have its own environment installed (see
its own README) — `agents/executor.py` uses
`maisoncarmenta-qa/.venv/Scripts/python.exe` directly.

## Running it

**Web interface (recommended)**: double-click `start.bat`. It
automatically opens `http://127.0.0.1:8000` once the server has started.

**Command line**:

```powershell
.venv\Scripts\python.exe main.py "optional natural-language specification"
.venv\Scripts\python.exe main.py "" --tests "tests/test_homepage.py::test_homepage_loads[chromium]"
```

## Cost

Every run makes real calls to the Claude API (Opus 5) — no free mode. The
interface shows an estimate before running, but it's an order of
magnitude, not an exact invoice.

## Tests (of the agents themselves, not of maisoncarmenta.com)

```powershell
.venv\Scripts\python.exe -m pytest -v
```

81 tests, no real Claude call and no real pytest subprocess — everything
touching the Anthropic API or a real `pytest` is mocked
(`unittest.mock`). What's covered:

- **Pure logic**: JUnit XML parsing (including the full failure text, not
  just the short summary), reading the rerun counter, building the
  initial state, persisting the "last run" and history.
- **Deterministic Triage decision**: a test recovered after a rerun is
  categorized "flaky" by direct proof, without ever calling Claude —
  tested by verifying no API mock is needed for that specific case.
- **Analyst non-duplication**: it receives the real list of existing
  tests and must never re-suggest an already-covered idea — tested on the
  content of the sent prompt, and validated once by a real Claude call
  (see commit history).
- **Wiring of the agents that call Claude** (Analyst, Supervisor, Triage
  on persistent failure, Reporter): the Anthropic client is mocked, and
  we verify the simulated decision/output is correctly wired into the
  state — not the quality of the decision itself (see "Roadmap").
- **The FastAPI API** via `TestClient`: full lifecycle of a run (running →
  done/error/cancelled), history, 404 on an unknown run, cancel
  responsiveness while a "long" run is simulated in progress.

## Structure

```text
agents/         one file per agent (analyst, executor, triage, reporter)
orchestrator/   state.py (data contract), supervisor.py, graph.py, runner.py
schemas/        Pydantic models shared between agents
tests/          tests of the agents themselves (see "Tests" above)
web/            interface (served by server.py)
server.py       FastAPI API + serves the interface
main.py         CLI entry point
reports/        generated on every run (JUnit XML, history) — never committed
```

## Roadmap

- **LangSmith evaluation** — the pytest suite above verifies the agents
  are correctly *wired* (state flows through correctly), but not that
  their LLM decisions are *good* (does the Supervisor route correctly in
  an ambiguous case? are the Analyst's suggestions relevant?).
  `langsmith.evaluate()` is built for that: running an agent over a set
  of examples and scoring the quality of its responses, tracked over
  time. Requires a separate LangSmith account and a real reference
  example set — deliberately not done today to avoid rushing either the
  example set or the existing pytest suite.
- **Lightweight Validator agent** (checking that an assertion can
  actually fail, a lightweight form of mutation testing) — mentioned in
  the architecture but never implemented.
- **Data agent — deliberately not implemented, not just "not done yet."**
  Two real constraints of the site block a safe version:
  1. The product catalog (title, description, images) is hardcoded in the
     site's own `src/lib/catalogue.ts`, not in a database — creating a
     "test product" would require modifying and redeploying the site's
     code, outside the scope of a test agent.
  2. Stock/price (the only data actually in Supabase) is read
     **server-side** (Next.js Server Component), before the page ever
     reaches the browser — `page.route()` cannot intercept anything here
     (a limitation already hit while testing forms). Any controlled test
     data would mean writing directly to the **production** Supabase,
     with a real risk (a real customer could see test stock/price during
     the run's window).

  A safe Data agent needs a separate staging environment (a second Vercel
  deployment + a second Supabase project) — an infrastructure project of
  its own, not an agent to add.
- Slack/email notifications when a real `product_bug` is detected,
  cumulative cost tracked over time.
