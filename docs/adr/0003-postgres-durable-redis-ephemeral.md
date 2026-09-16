# ADR 0003: PostgreSQL is the source of truth; Redis is ephemeral

- Status: Accepted
- Date: Sprint 0

## Context

Workflows are long-running, can pause for human approval, and must survive a process
restart. We need both a durable store and a fast coordination layer. Redis is fast and
already required for queues, so there is a temptation to keep live workflow state there.

## Decision

All workflow state that must survive — workflows, nodes, edges, tasks, executions, agent
results, events, usage records, errors — is written to PostgreSQL. Redis holds only
derived or transient data: job queues, progress for live UI updates, response caches,
rate-limit counters, and distributed locks.

A workflow must be fully reconstructible from PostgreSQL alone.

## Consequences

- Flushing Redis degrades performance and loses queued work, but never corrupts or loses
  workflow history; in-flight jobs are recoverable by re-enqueueing from Postgres state.
- Every state transition costs a database write. Accepted: workflow steps are seconds-to
  -minutes long and dominated by provider latency, so write overhead is irrelevant.
- Resumability (Section 24 of the product brief) becomes a property of the schema rather
  than a feature to bolt on later, which is why this is settled in Sprint 0 before any
  tables exist.
- Relational integrity matters here (a node belongs to a workflow; a result belongs to an
  execution) and the reporting queries we need are aggregations and joins, which is the
  second reason for PostgreSQL over a document store.
