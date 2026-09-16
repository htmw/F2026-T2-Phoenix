# ADR 0001: Record architecture decisions

- Status: Accepted
- Date: Sprint 0

## Context

This platform has several decisions that are expensive to reverse (database choice,
provider abstraction boundary, monolith vs services, where workflow state lives). Future
sprints — and future contributors — need the *reasoning*, not just the result, otherwise
settled questions get reopened or a good decision gets undone because its constraint was
invisible.

## Decision

Record significant architectural decisions as short numbered files in `docs/adr/`.
An ADR captures context, the decision, and consequences. ADRs are immutable once
accepted; a change is a new ADR that supersedes the old one.

"Significant" means: hard to reverse, affects module boundaries, or constrains later
sprints. Routine implementation choices do not need an ADR.

## Consequences

- Sprint work that changes architecture must add an ADR; this is part of the Definition
  of Done.
- `docs/architecture.md` describes the current system; ADRs explain how it got there.
