# Sprint 7 Retrospective — Providers, routing, message bus

**Goal:** three real providers, ranked routing with fallback, and direct agent mail.

**Delivered:** D-3, D-4, K-1.

---

## What went well

- Anthropic is a separate adapter; OpenAI-compatible vendors share one HTTP class. The
  conformance suite is the same list of tests, parametrized.
- Routing returns a ranked list, so fallback is "next best model" rather than a retry of
  the same dead vendor.
- Workflow hand-offs write `task_request` messages. The engine still schedules; the bus
  is what agents read.

## What went wrong

- The original sprint plan put the message bus in Sprint 3 and we shipped orchestration
  first. Direct communication had to be pulled forward once the product spec made it
  non-negotiable.

## Decisions worth recording

- Fallback only on unavailability, timeout, and rate limits. See ADR 0005.
- The orchestrator is a bus participant named `orchestrator`, not a required hop.
  See ADR 0004.

## Carried forward

- Memory, artifacts, metrics, office UI (Sprint 8).
- Authentication and inter-agent permission allow-lists (Sprint 9).
