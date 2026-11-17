# Sprint 3 readiness

Prepared only — **not** implemented as full Sprint 3 scope.

## Already implemented (usable as foundations)

| Topic | Foundation in repo |
|-------|--------------------|
| Human approval | Node `awaiting_approval`, approve/reject APIs + UI |
| Pause/resume | Workflow cancel + resume endpoints |
| Multi-provider routing | Provider registry, routing policy, model overrides |
| Cost / tokens | Execution summaries store tokens, cost, latency |
| Artifacts | Artifact APIs + desk UI |
| Ownership | Workflow `owner_id`, auth isolation tests |
| Explainability | Selection reasons, node satisfies, decisions store |

## Prepared / extension points (interfaces only)

| Sprint 3 theme | Prepared as | Not done |
|----------------|-------------|----------|
| Workflow versioning / replay | Immutable workflow records + thread parent ids | Version table, replay API |
| Templates | Agent enrollment + builder roster | Template CRUD |
| RBAC roles | Operator identity + Google subject | Role enum, permission matrix |
| Render deploy | Course has blueprint | Not ported to personal repo |

## Requires further architectural decisions

1. Password auth vs Google-only for class demos.
2. Whether templates are operator-scoped or team-shared.
3. Cost budgets: hard stop vs soft warning at workflow level.

## Explicitly not Sprint 3-complete

Do not present versioning, replay, full RBAC, or marketplace templates as shipped.
