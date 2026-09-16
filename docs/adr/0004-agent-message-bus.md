# ADR 0004: Agents communicate on a message bus, not through the orchestrator

- Status: Accepted
- Date: Sprint 7

## Context

The orchestrator already plans a DAG and executes it. The obvious design is that every
hand-off is an in-memory payload the engine copies from one node to the next. That makes
the orchestrator a telephone operator: two agents cannot talk unless a workflow step
exists, inboxes are empty after a restart, and there is no record of *who asked whom*.

The product requirement is the opposite: a security agent must be able to address the
coding agent directly, persist that message, and have the coding agent discover who
understands authentication without the user wiring them.

## Decision

Introduce a durable **message bus**. Every envelope is a typed, validated record stored
in PostgreSQL (`agent_messages`). The orchestrator is a participant (`orchestrator`),
not a required hop. Direct messages, task requests, replies, broadcasts, and errors all
use the same table. Workflow execution *also* writes to the bus: a completed node sends
a `task_request` to each downstream agent, so the inbox is the source of collaboration
history even when the engine scheduled the work.

Before each node attempt the engine runs a **hive loop** (inspired by collaborative
office agents, adapted to our DAG): drain delivered inbox mail into the agent's brief,
optionally consult peers via real provider APIs when credentials exist (skipped on
fake-only registries so tests stay hermetic), and after success post a shared blackboard
note and reply to waiting `information_request` / `task_request` peers with the correct
speech-act response type.

Mailboxes, shared/private/workflow memory, artifact *references*, presence, and an
append-only `network_events` log live beside the bus. The context manager pulls a short
relevant brief from those stores; it never dumps a conversation.

## Consequences

- Agent-to-agent traffic survives process restart and is queryable without replaying a
  workflow.
- The engine remains responsible for *when* a node runs (dependencies, skips, retries).
  The bus is responsible for *what was said*.
- Permissions between agents are currently "any registered agent may write"; that is a
  documented gap for the authentication sprint, not an accident.
