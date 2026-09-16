# Sprint 6 Retrospective — Visualisation, approval, synthesis

**Goal:** a user watches a workflow execute live, including skipped nodes and parallel
branches, and can act on an approval gate.

**Delivered:** G-1 (UI), G-2, G-3, F-7, F-8, G-4.

---

## What went well

- `wait=false` already returned the planned graph. The UI polls that record; no websocket
  was required to make progress visible.
- Approval lives on the node (`approval` JSONB) rather than a side table. A paused
  workflow is just a workflow whose next ready nodes need a person, and resume is the
  same path used after cancel.
- Synthesis prefers a documentation agent's `document` and always lists skipped and
  failed contributors. A partial run cannot look complete.

## What went wrong

- G-4 (retry/skip/approve from the UI) was scheduled in Sprint 7. Rendering buttons that
  hit 404s would have been a false demo, so the controls shipped with the page.
- Node controls are refused while a workflow is `running`, because the in-process runner
  does not reload skip/retry decisions mid-batch. Cancel first, then steer.

## Decisions worth recording

- **Code-changing nodes are the approval gate.** Research, tests, and documentation do
  not mutate the system under review; pausing them would only add latency. The planner
  sets `requires_approval` on capabilities in `_CODE` when the request asks for a gate.
- **Reject skips the branch.** It does not fail the workflow. Dependents that required
  the rejected node are skipped with a reason; an `any`-join report can still run.
- **Control endpoints are public until Sprint 9.** The actor is self-asserted
  (`decided_by`) so the decision is attributable when authentication arrives.

## Carried forward

- Three real providers and model routing (Sprint 7).
- Metrics and cost aggregation endpoints (Sprint 8).
- Authentication and workflow ownership (Sprint 9).
