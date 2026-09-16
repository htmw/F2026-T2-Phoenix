# Sprint 5 Retrospective — Conditionals, retries, cancellation

**Goal:** skip work that is not needed, recover from transient failure, and keep control
of a run that is already in flight.

**Delivered:** F-4, F-5, F-6.

---

## What went well

- Skipping is a success state with a stored reason. The headline case — security finds
  nothing, coding never runs, the report still writes — is a test, not a comment.
- Feedback is data, not an edge. Testing can send work back to coding without introducing
  a cycle; the engine reopens the target and its descendants and bounds the loop with
  `max_repair_cycles`.
- Cancellation is a request the engine honours at a batch boundary. Resume reloads the
  graph from Postgres rather than re-planning, so a resumed run cannot silently change
  shape.

## What went wrong

**Enum identity is not a database comparison.** `workflow.status is WorkflowStatus.COMPLETED`
is always false when SQLAlchemy has loaded a string. Resume then tried to walk
`workflow.task` without it being loaded and blew up with `MissingGreenlet`. Compare with
`==`, and eager-load the task.

**Test payloads must match the agent schema.** Queuing `failures: ["a string"]` for the
testing agent is invalid JSON Schema (`items` are objects). The executor retried, ate the
next queued response, and the coding agent received testing output. The tests were
asserting on a retry bug they had introduced.

## Decisions worth recording

- **A skip is success.** Downstream nodes treat it as a resolved dependency; they do not
  hang, and the UI can show why the agent was left out.
- **Repair is bounded.** A coding agent and a testing agent can disagree forever. After
  the budget the verdict stands and the workflow completes with it recorded.
- **Completed work survives cancellation.** Results already paid for stay on the node;
  only unfinished slots are marked cancelled.

## Carried forward

- Human approval and result synthesis (Sprint 6).
- Operator retry/skip from the UI (Sprint 6, pulled forward with G-4).
