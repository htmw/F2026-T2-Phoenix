# Sprint 3 implementation roadmap

Ordered for the personal repository after Sprint 2 acceptance.

1. **Workflow versioning** — snapshot plan JSON + version number on each save; list/diff versions.
2. **Replay** — re-run a prior plan with frozen agent ids and recorded inputs.
3. **Approval policies** — per-capability approval rules (beyond per-node flag).
4. **RBAC** — roles (`operator`, `viewer`, `admin`) on workflow ownership.
5. **Template gallery** — save Build-tab rosters as named templates.
6. **Cost controls** — hard budget halt + dashboard burn chart.
7. **Deploy** — port Render blueprint from course repo; document env vars (no secrets in git).
8. **Observability** — wire unused `getMetrics` + ActivityFeed into Work dashboard.

Each item needs its own acceptance tests before claiming done.
