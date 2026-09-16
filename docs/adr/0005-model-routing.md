# ADR 0005: Ranked model routing with bounded provider fallback

- Status: Accepted
- Date: Sprint 7

## Context

Agents declare traits, not vendor model ids. Several providers can satisfy the same
trait set at different prices and latencies. A single `select_model` winner that is
down would fail the agent even when a cheaper or slower alternative is healthy.

## Decision

`ProviderRegistry.rank_models` returns every eligible model, best first. Ranking is:

1. explicit preferred model, if configured and present (Fixed pin; may bypass blocks)
2. office **provider priority** (Settings routing policy)
3. preferred provider (per-agent)
4. fewest missing preferred traits
5. output cost
6. typical latency
7. model id (deterministic tie-break)

Models listed in the office **blocked_models** policy are excluded unless they are the
explicit Fixed pin for that preference.

The executor walks that list. It falls back only on `PROVIDER_UNAVAILABLE`, `TIMEOUT`,
and `RATE_LIMITED`. Authentication failures and malformed requests are properties of
the call, not the vendor, so they do not rotate.

Each choice is logged with a reason and the next alternatives. No credential appears in
those logs.

Adapters that share the OpenAI Chat Completions wire format (OpenAI, DeepSeek, xAI,
Mistral, OpenRouter) share one HTTP class. Anthropic's Messages API is a separate
adapter. Both pass the same conformance tests.

## Consequences

- Adding a vendor is catalogue + credentials, not a new executor.
- Fallback can spend more than the first pick. Agent and workflow cost ceilings still
  apply before each attempt.
- Process-local Prometheus counters reset on restart; Postgres remains the source of
  truth for "what did this cost".
- Built-in agents ship with **Auto** routing (traits only). An explicit
  `preferred_model` is an optional Fixed binding, never part of the agent's role.
- Run-level strategies productize the same router: **Auto** (bindings + traits),
  **One** (shared catalogue model for every node), **Mixed** (per-agent overrides).
- Production never registers the development FakeProvider; the catalogue API marks it
  `demo=True` when present in non-production environments.