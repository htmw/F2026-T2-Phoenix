# Sprint 4 Retrospective — Parallel workflows

**Goal:** independent agents run concurrently with a working join, measurably faster than
the sequential sum, with a failing branch that does not corrupt its siblings.

**Delivered:** F-3. 260 tests, lint and strict type checks clean.

---

## What went well

- The dependency-driven engine from Sprint 3 needed no redesign. Scheduling already asked
  "which nodes have all their dependencies satisfied"; running that set concurrently
  instead of one at a time was a change to dispatch, not to the loop.
- Wall clock is measured, not assumed. A provider with a real `asyncio.sleep` and an
  in-flight counter means "these ran in parallel" is an observation: five 0.2s nodes in a
  fan-out finish in roughly three stages, and the counter proves three siblings overlapped.
- The executor's existing contract — every failure becomes an `AgentOutput`, nothing
  raises — made sibling isolation nearly free. `asyncio.gather` cannot propagate an
  exception that is never raised, so one branch cannot cancel the others.

## What went wrong

**Stage barriers could never produce parallelism.** The first implementation grouped nodes
by stage rank and made every stage a barrier. It passed its own unit tests and was
useless: each built-in agent has a distinct rank, so every real plan was still a chain.
The HTTP test that asked "does a broad request produce a fan-out" failed, which is the
only reason it was caught. The lesson is that the test that exercises the actual product
path is worth more than three that exercise the mechanism.

The fix replaced ranks-as-schedule with capability *consumption*: code work consumes
research and security findings, tests and reviews consume code changes, documentation
consumes everything. Two agents that consume nothing from each other have no edge, so
they run together. Ranks survive only as the acyclicity guarantee — an edge may run only
from a lower rank to a higher one — which means no consumption rule can produce a cycle.
This is also the shape the product promised: audit and research at once, then fix, then
test and review at once.

**Transitive edges were quietly expensive.** Deriving edges pairwise gave testing a
shortcut edge from planning even though coding already carried planning's output forward.
Harmless for correctness, but each redundant edge hands a node a payload it never asked
for, which is tokens and money. Added a transitive reduction, with documentation
deliberately exempt: a report that only saw the final branch would silently omit work the
user paid for.

**Concurrency and one database session do not mix.** An `AsyncSession` is not safe for
concurrent use, and the first draft had each concurrent node writing its own execution
record. Execution is now concurrent while persistence is serialised after the batch
returns. That is not a compromise: the wall-clock time is in the provider calls, and
serialising the writes costs microseconds.

## Decisions worth recording

- **A batch may overshoot a workflow budget.** Concurrent calls cannot reserve budget
  against each other, so every member of a batch is checked against the remainder from
  before the batch ran. The overshoot is bounded by the cost of one batch, each agent's
  own hard ceiling still applies, and the real spend is recorded. The alternative —
  dividing the remaining budget by the batch size — refuses legitimately expensive nodes.
- **Fan-out is bounded** (`MAX_PARALLEL_AGENTS`, default 4). Unbounded fan-out would
  exhaust provider connections or trip a rate limit that fails every branch at once,
  turning a parallelism win into a total loss.
- **A failed branch stops the workflow but keeps its siblings' results.** Work that was
  paid for and completed is persisted and visible. The workflow still fails rather than
  returning a partial result that reads as complete.
- **A join node receives all of its predecessors' payloads.** Tested directly, because
  "the report describes only half the work" is the failure mode that would be hardest to
  notice in output that looks plausible.

## Carried forward

- Retries, conditional skips, and escalation (Sprint 5). Today one node failure ends the
  workflow after its batch completes.
- Cancellation cannot be honest until execution moves off the request thread (Sprint 5).
