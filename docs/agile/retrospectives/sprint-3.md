# Sprint 3 — Review and Retrospective

## Sprint goal

A plain-English request activates the right agents, in the right order, and only those.

**Outcome: goal met.** 21 of 21 committed points delivered, plus G-1 (task submission
API) pulled forward from Sprint 6 because the endpoint was needed to demonstrate the
sprint goal at all.

## Review

| Story | Points | Status | Evidence |
|-------|--------|--------|----------|
| F-1 Capability analysis and agent selection | 13 | Done | Heuristic and LLM-backed analysers behind one protocol; greedy set-cover selection; every excluded agent carries a reason, persisted with the workflow |
| F-2 Sequential workflow execution | 8 | Done | Dependency-driven engine; each node receives only its direct upstream payloads; every transition persisted |
| G-1 Task submission | 3 | Done (API) | `POST /api/v1/tasks` and `POST /api/v1/tasks/plan`; the UI half stays in Sprint 6 |

242 tests pass, lint and `mypy --strict` clean.

### Demonstrated live

A narrow request — *"Find security vulnerabilities in the payments service"* — produced
one capability, one agent, and six exclusions, each with a stated reason.

A broad request — *"Analyze this GitHub repository for security vulnerabilities, fix the
issues you find, write tests for the fixes, and document all changes"* — produced five
capabilities and this workflow:

```
planning -> security -> coding -> testing -> documentation
```

`research-agent` and `review-agent` were excluded as irrelevant. All five nodes
completed, total cost $0.001832, with per-node token and cost records. The
documentation agent was routed to the cheap model and the reasoning agents to the
expensive one, which is the routing rule doing its job without anyone naming a model.

## Design decisions worth recording

**Analysis returns capabilities, never agent names.** Both analysers are forbidden from
naming agents, and the LLM analyser may only choose from the declared vocabulary —
anything it invents is dropped with a warning rather than propagated to selection, where
it would masquerade as a coverage gap.

**The LLM analyser always has a heuristic fallback.** A planning outage, a malformed
response, or an unrecognised answer all fall back rather than fail. The platform
degrades to keyword analysis instead of becoming unusable, and the fallback is visible
in the recorded `analysis_source` (`llm->fallback`).

**Ordering is expressed as stage ranks over capabilities, not a pipeline.** Research
informs analysis, analysis informs code, code precedes tests, tests precede review, and
documentation reports last. Because the ranks are keyed by capability, a newly
registered agent takes its correct place without the planner learning its name. A test
asserts every capability is ranked, since an unranked one would silently land mid-graph.

**Selection prefers one agent covering several capabilities.** Fewer agents means fewer
calls and less hand-off for the same coverage. Optimal set cover is NP-hard, so the
greedy choice is deterministic and tie-broken by cost then id — the same request always
produces the same graph.

**An uncovered capability refuses the request.** Answering a different question than the
one asked is worse than saying no. The task row is still written, because a refused
request is evidence of a coverage gap worth seeing.

**Node objectives restate the user's words verbatim.** A paraphrase drifts from what was
asked and every downstream agent inherits the drift, so each node gets the original
request plus a statement of its own remit.

**The engine is dependency-driven, not list-driven.** It repeatedly asks which nodes have
satisfied dependencies. Sequential execution is the degenerate case, so Sprint 4's
parallelism changes how a ready batch is dispatched and Sprint 5's conditions change how
"satisfied" is judged — neither requires rewriting the loop.

## What went wrong

**Two endpoint tests failed for the same hidden reason: the analyser ate the script.**
API tests script responses on the fake provider for the *agents*, but the default
configuration also runs an LLM analysis call, which consumed the first queued response.
The security agent then received a generic stub and the assertions failed with a
confusing diff. Fixed by configuring test settings to use heuristic analysis — the LLM
analyser keeps its own unit tests, including the fallback paths — which also makes
endpoint tests deterministic.

*Lesson: a shared scripted dependency needs to be obvious about who consumes it. The
symptom (wrong payload) was nowhere near the cause (an extra caller).*

**One assertion made the wrong claim about the plan preview.** It asserted the preview
spends nothing, then failed because analysis is itself a model call. The claim that
actually matters is that no *agent* runs and no workflow is created, which the test now
asserts. Running real analysis in the preview is correct: a preview produced by a
different code path than the real thing is not a preview.

**A service returned `tuple[object, object]` and poisoned three files.** `plan_only`
started out untyped, and the route and its tests filled up with `type: ignore` comments
to compensate. Replaced with a `PlanPreviewResult` dataclass, which deleted every
ignore and let the preview also report the cost ceiling.

*Lesson: a loose return type does not stay local — it spreads as suppressions.*

## Carry-over

None.

## Next sprint

Sprint 4: parallel execution with a join. The engine's ready-set already identifies
independent nodes; the work is dispatching them concurrently with bounded fan-out, and
teaching the planner to emit a diamond instead of a chain where dependencies allow.
