from pydantic import BaseModel


class ExecutionResult(BaseModel):
    """The result of ONE real test from the maisoncarmenta-qa suite,
    produced by the Executor agent from the actual pytest run (JUnit XML)
    — no generated code or ad hoc file since the pivot away from
    generation."""

    test_id: str  # pytest node id, e.g. tests/test_homepage.py::test_homepage_loads[chromium]
    title: str
    passed: bool
    duration_seconds: float
    error_message: str
    file: str
    # Number of pytest-rerunfailures reruns before the final result. > 0
    # even on a `passed` test = empirical proof of flakiness (it failed at
    # least once before succeeding within the same run) — not a guess.
    reruns: int = 0
