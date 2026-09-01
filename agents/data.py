"""Data agent (V2, NOT implemented) — reserved interface, deliberately not
built against production. See README.md -> "Roadmap" for the full
reasoning.

Two real constraints of the target site block a safe version today:
1. The product catalog (title, description, images) is hardcoded in the
   site's own codebase (catalogue.ts), not in a database — "creating a
   test product" would require modifying and redeploying the site's code,
   outside the scope of a test agent.
2. Stock/price (the only data actually in Supabase) is read SERVER-SIDE
   (Next.js Server Component), before the page ever reaches the browser —
   page.route() cannot intercept anything here. Any controlled test data
   would mean writing directly to the PRODUCTION Supabase, with a real
   risk (a real customer could see test stock/price during the run).

A safe Data agent needs a separate staging environment (a second Vercel
deployment + a second Supabase project) — an infrastructure project of its
own, not an agent to add.

Intended role, if that infrastructure existed: before the Executor, create
the needed test data (e.g. a test product, a disposable user account) via
the target project's API/DB, and return their identifiers in
`state["test_data_handles"]`. After the Reporter (or on a fatal graph
failure — a cleanup node inside an application-level `finally`, not just
the happy path), delete that same data by its identifiers so nothing is
left behind.

Would plug into the graph between "analyst" and "executor" on the creation
side, and last of all (even after "reporter", before FINISH) on the
cleanup side.

def data_setup_node(state: QAOrchestratorState) -> QAOrchestratorState:
    raise NotImplementedError

def data_teardown_node(state: QAOrchestratorState) -> QAOrchestratorState:
    raise NotImplementedError
"""
