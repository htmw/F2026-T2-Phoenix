# Universal Office — Sprint 4: Routing strategies

**Status:** Done  
**Goal:** Productize Fixed / Auto / One / Mixed model routing.

## Shipped

| ID | Item | Status |
|----|------|--------|
| U4-1 | `RoutingStrategy` enum: auto / one / mixed | Done |
| U4-2 | TaskRequest: `routing_strategy`, `shared_model`, Mixed validation | Done |
| U4-3 | `apply_routing_to_plan` bakes One/Mixed onto nodes | Done |
| U4-4 | `PATCH /agents/{id}/model-binding` Fixed ↔ Auto | Done |
| U4-5 | Seed preserves operator Fixed bindings | Done |
| U4-6 | Command: Auto / One / Mixed controls | Done |
| U4-7 | Settings: per-agent Fixed bindings | Done |
| U4-8 | Tests + ADR note | Done |

## Semantics

| Mode | Scope | Behaviour |
|------|--------|-----------|
| **Auto** | Run default | Agent Fixed binding if set; else trait router |
| **Fixed** | Agent (Settings) | Durable `preferred_model` on the agent role |
| **One** | Run | Single `shared_model` on every node |
| **Mixed** | Run | `model_overrides` per agent; others stay Auto/Fixed |

Legacy: sending `model_overrides` without a strategy still upgrades to Mixed.

## Next

Sprint 5 — provider priority / blocked models — **DONE**
(`docs/sprints/universal-office-sprint-5.md`).

Next: Sprint 6 — office UX polish, artifact browser, or auth prep.
