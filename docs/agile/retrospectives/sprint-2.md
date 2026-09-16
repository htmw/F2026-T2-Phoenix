# Sprint 2 — Review and Retrospective

## Sprint goal

One agent runs against a real provider, with validated output and enforced limits.

**Outcome: goal met.** 23 of 23 committed points delivered.

## Review

| Story | Points | Status | Evidence |
|-------|--------|--------|----------|
| D-1 LLMProvider interface | 5 | Done | `LLMProvider` ABC with `generate`, `stream`, `estimate_cost`, `validate_configuration`, `get_model_capabilities`; shared `ErrorKind` taxonomy; conformance tests parameterised across adapters |
| D-2 First provider adapter | 5 | Done | `OpenAICompatibleProvider` plus OpenAI, DeepSeek, and xAI catalogues; request shaping, usage accounting, streaming, and status→taxonomy mapping all tested through an injected transport |
| E-1 Execute one agent end to end | 8 | Done | `POST /api/v1/agents/{id}/run` persists task → workflow → node → execution → result; `GET /workflows` and `/workflows/{id}` expose attempt-level detail |
| E-2 Agent timeouts and cost ceilings | 5 | Done | Pre-flight estimate refuses unaffordable calls without sending them; `asyncio.wait_for` enforces the agent timeout; both agent and workflow budgets enforced |

181 tests pass, lint and `mypy --strict` clean, 94% line coverage.

### Demonstrated live

A run through the Dockerised stack returned `succeeded` with `provider=fake`,
`model=fake:reasoner`, 420 input tokens, 4 output tokens, `$0.000432`, and a completed
workflow whose node carried the validated payload. The security agent's empty
`findings` list validated as success, which is the behaviour conditional skipping will
depend on in Sprint 5.

## Design decisions worth recording

**One adapter for the OpenAI-compatible protocol.** OpenAI, DeepSeek, xAI, Mistral, and
OpenRouter accept the same request shape, differing only in base URL, credential, and
model catalogue. Sharing an adapter is not premature generalisation — it is the actual
shape of the ecosystem. Anthropic and Gemini differ materially and get their own
adapters in Sprint 7.

**The fake provider is an adapter, not a mock.** It implements the full interface, is
held to the same conformance tests, and can script failures and malformed output. That
is what lets every failure path be tested deterministically at zero cost, and it means
a fresh checkout runs end to end with no credentials.

**Cost estimates assume maximum output.** The estimate guards a spend ceiling, so
erring cheap would let through calls that cannot be afforded. A refused call costs
nothing and is recorded as `budget_exceeded`.

**A failed agent is a 200, not a 500.** The transport succeeded; the agent did not.
Returning 500 would make a normal domain outcome indistinguishable from a platform bug,
and would deny the client the classified error it needs to decide what to do.

**Raw completion text is stored only on failure.** Keeping every completion is a
privacy and storage cost with no debugging benefit; keeping the ones that failed
validation is exactly the debugging data that is needed.

**Validation is separated from execution.** `output_validation` is the trust boundary:
above it, untrusted text from a non-deterministic system; below it, domain data. Code
fences and stray prose are recovered, because that is cheaper than a retry, but
malformed JSON is never guessed at.

## What went wrong

**Two tests were written wrong before the code was.** One budget test set the agent
ceiling at the schema's maximum ($100) and then asserted on the *workflow* budget
message — but the agent ceiling tripped first, so the assertion described the wrong
check. Rewritten to use a generous agent ceiling and a tiny remaining workflow budget,
which is the case that actually matters: a long workflow running out of money late.

**A test reached into `httpx` internals.** The first version of the API tests pulled the
ASGI app out of `db_client._transport.app` to override the provider registry. That is
the kind of thing that breaks on a library upgrade for no reason. Replaced with a
`fake_provider` fixture that the `db_client` fixture installs, so scripting a response
is now a one-liner in the test body.

*Lesson: if a test has to reach through a private attribute, the fixture is missing.*

**`mypy --strict` flagged stale `type: ignore` comments.** Several were added
defensively and were unnecessary once `types-jsonschema` was installed. Removed rather
than left in place; an unnecessary ignore is a future missed error.

## Carry-over

None.

## Next sprint

Sprint 3: capability analysis and agent selection from a plain-English request, then
sequential DAG execution with structured hand-off between agents.
