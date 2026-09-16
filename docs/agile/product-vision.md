# Product Vision

## Vision statement

For knowledge workers and engineering teams who face requests too complex for a single
AI call, the **AI Agent Orchestration Platform** is an orchestration engine that decomposes
a request, activates only the specialised agents it actually requires, runs them in the
right order — in parallel, in sequence, or conditionally — and synthesises one validated
result. Unlike multi-model chat tools that broadcast the same prompt to several models,
our platform decides *what work is needed, who does it, and in what order*.

## Problem

A request like "analyse this repository, find security vulnerabilities, fix the important
ones, write tests, and generate a report" is not one task. It is seven, with dependencies,
branches, and different skill requirements. Today users decompose it manually: prompt one
model, copy the output, prompt another, notice something failed, start over. Existing
multi-model tools make this worse by running every model on every request, which multiplies
cost without adding coordination.

## Solution approach

1. **Capability-driven selection.** Derive required capabilities from the request; activate
   only the agents that provide them. Not running an agent is a first-class outcome.
2. **Workflow graphs.** Model work as a DAG so parallelism, joins, and conditional branches
   are native rather than simulated.
3. **Structured hand-offs.** Agents exchange validated typed data, not transcripts.
4. **Provider independence.** One interface over many model providers, so each agent can be
   powered by the model best suited to it — reasoning, coding, or cheap classification.
5. **Transparency.** The user watches the workflow execute, sees which agents were chosen
   and skipped, what each cost, and can retry, skip, or approve steps.

## Target users

- **Individual practitioner** — submits complex multi-step work, wants it done without
  manual orchestration.
- **Engineering team** — needs repeatable pipelines (security review → fix → test → report)
  with auditability.
- **Platform operator** — needs to control cost, observe failures, and add new agents or
  providers without modifying the engine.

## What success looks like

- The system reliably *excludes* irrelevant agents; a single-capability request runs exactly
  one agent.
- Parallelisable steps run concurrently, and total latency reflects that.
- A failed agent or malformed model output is recovered from without losing the workflow.
- Every workflow can report its cost, duration, slowest agent, retries, and token usage.
- Adding an agent or a provider requires no change to orchestration code.

## Explicit non-goals

- Not a general-purpose chatbot or a model-comparison playground.
- Not a prompt marketplace.
- Not an autonomous system acting without user-visible workflows and approval points.
- Not a training or fine-tuning platform.

## Guiding constraints

Correctness over speed of delivery. Cost is a first-class concern, not an afterthought.
Model output is untrusted input. Secrets never reach the client. The whole environment runs
with one command.
