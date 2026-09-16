# Universal Office — Sprint 3: Agent communication

**Status:** Done  
**Goal:** Productize the durable message bus into a usable agent mailbox with typed
context/delegation traffic and a Floor inspector.

## Shipped

| ID | Item | Status |
|----|------|--------|
| U3-1 | Message types: `context_request` / `context_response`, `delegation`, `artifact_share` | Done |
| U3-2 | Bus reply mapping + hive closes context/delegation requests | Done |
| U3-3 | `ContextManager.packet` + fulfill-context API | Done |
| U3-4 | `GET /agents/{id}/mailbox` → inbox / sent / archive | Done |
| U3-5 | `GET /messages/{id}` message inspector payload | Done |
| U3-6 | Floor desk: Inbox / Sent / Archive tabs + inspector | Done |
| U3-7 | Handoff emits `artifact_share` alongside task handoff | Done |
| U3-8 | Tests for mailbox folders + context fulfill | Done |

## API surface

- `GET /api/v1/agents/{agent_id}/mailbox` — active inbox, sent, completed/failed archive
- `GET /api/v1/messages/{message_id}` — single envelope for the inspector
- `POST /api/v1/messages/{message_id}/fulfill-context?agent_id=` — reply with a context packet

## Rules kept

- Relevant context packets only — never full conversation dumps
- Agent ≠ Model ≠ Provider unchanged from Sprint 1–2

## Next

Sprint 4 — routing strategies as product surface (Fixed / Auto / One / Mixed), or
continue office UX polish.

### Sprint 4 — DONE

See `docs/sprints/universal-office-sprint-4.md`. Next: provider priority / blocked
models, or further office polish.
