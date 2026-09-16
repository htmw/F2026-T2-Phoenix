# Definition of Done

"It compiles" and "it worked when I ran it" are not Done. A backlog item is Done only when
every item below is true. This list is checked at Sprint Review; anything unchecked sends
the story back to the backlog.

## Implementation
- [ ] All acceptance criteria on the story are satisfied.
- [ ] Error paths are handled deliberately — no bare `except`, no ignored promise
      rejection, no failure that surfaces as an unexplained 500.
- [ ] External input, **including every LLM response**, is validated before it can affect
      control flow or reach the database.
- [ ] No new hard-coded agent, provider, model name, or credential.
- [ ] Configuration is read from settings, not inlined in business logic.

## Tests
- [ ] Unit tests cover the new logic, including at least one failure case.
- [ ] Integration tests cover any new database, Redis, or HTTP boundary.
- [ ] No test depends on a paid API call; all provider calls are mocked or faked.
- [ ] The full suite passes locally and in CI.

## Quality gates
- [ ] `make lint`, `make typecheck`, and `make test` pass with no new warnings.
- [ ] Formatting applied (`ruff format`, frontend formatter).
- [ ] No commented-out code or debug prints left behind.

## Observability
- [ ] New operations emit structured logs with the relevant correlation ids.
- [ ] Logs contain no secrets, no API keys, and no full prompt/response bodies by default.
- [ ] Anything that costs money records its token usage and estimated cost.

## Security
- [ ] No secret is committed; `.env` remains ignored and `.env.example` is updated.
- [ ] No provider key or key-derived value can reach the frontend.
- [ ] New endpoints state their auth expectation (public for now is a documented choice).

## Documentation
- [ ] `README.md` updated if setup or commands changed.
- [ ] `docs/architecture.md` updated if structure or boundaries changed.
- [ ] An ADR added for any significant or hard-to-reverse decision.
- [ ] API and schema changes documented; backward compatibility preserved or the break
      called out explicitly.

## Environment
- [ ] `docker compose up` still brings up a working stack from a clean checkout.
- [ ] Migrations apply cleanly to an empty database and to the previous version.

## Process
- [ ] Changes arrived as focused commits with meaningful messages (Conventional Commits).
- [ ] The change is small enough to review; unrelated work was not bundled in.
- [ ] Backlog status updated.
