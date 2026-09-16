# Universal Office — Sprint 6: Artifact browser & office polish

**Status:** Done  
**Goal:** Surface artifact references in Floor and Activity without adding blob storage
or auth.

## Shipped

| ID | Item | Status |
|----|------|--------|
| U6-1 | `GET /artifacts/{id}` | Done |
| U6-2 | Emit `artifact_created` network events on register | Done |
| U6-3 | Frontend `ArtifactView` + list/get clients | Done |
| U6-4 | Floor desk Artifacts list + inspector | Done |
| U6-5 | Message inspector resolves artifact ids to titles | Done |
| U6-6 | Activity Artifacts panel | Done |
| U6-7 | Tests + sprint notes | Done |

## Rules kept

- Artifacts remain **references** (URI + metadata), never blobs
- No auth (Sprint 9)

## Next

Sprint 7 — decision log & light retention — **DONE**
(`docs/sprints/universal-office-sprint-7.md`).

Next: Sprint 8 — auth foundations, or deeper selection/routing decision capture.
