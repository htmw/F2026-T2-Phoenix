# Universal Office — Sprint 8: Auto-capture selection & routing

**Status:** Done  
**Goal:** Persist agent-selection and model-routing choices into the decision log
automatically. Auth remains Sprint 9.

## Shipped

| ID | Item | Status |
|----|------|--------|
| U8-1 | `AgentOutput.routing_reason` + `routing_alternatives` | Done |
| U8-2 | Executor annotates every attempt with routing metadata | Done |
| U8-3 | `SELECTION` decision on workflow prepare | Done |
| U8-4 | Pin `ROUTING` decision for One/Mixed (and baked pins) | Done |
| U8-5 | Per-attempt `ROUTING` decision in engine / single-agent | Done |
| U8-6 | Floor + Activity kind badges + payload inspector | Done |
| U8-7 | Tests + sprint notes | Done |

## Semantics

- **Selection** — recorded once at plan time (`actor_id=orchestrator`) with chosen /
  excluded agents and required capabilities.
- **Pin routing** — recorded at plan time when strategy is One/Mixed or nodes carry
  baked model pins.
- **Execution routing** — recorded per attempt (`actor_id=executor`) with provider,
  model, reason, and fallback alternatives.
- Executor stays DB-free; orchestration and the engine own persistence.

## Next

Sprint 9 — auth foundations (owners / JWT prep).
