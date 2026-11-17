# Sprint 2 implementation report

Repository: personal (`Soumen2581/Capstone-Project`)  
Branch: `sprint-2-implementation`  
Date: 2026-11-03

## Skills used

| Skill | Available | Used for |
|-------|-----------|----------|
| Impeccable | Yes (v4.5.1; newer v4.8.0 available) | Operate-mode UX for DAG dashboard, builder, login |
| Code review / security / API / DB | Cursor plugins present | Targeted review of auth and contracts |
| TDD / architecture dedicated skill files | Not found as project skills | Followed existing pytest / Playwright patterns |

## What was already complete

Backend already implemented DAG validation, cycle detection, sequential/parallel/conditional execution, structured handoff, retries, Postgres persistence, Review-Fix-Test planner edges, Google auth APIs, and a large automated suite.

## Changes in this Sprint 2 pass

### Backend

- Default `RetryPolicy.max_attempts` raised to **3** (SCRUM-49 alignment).
- Added `Capability.DATA_ANALYSIS` and **Data Analyst Agent**.
- Planner wires **Data Cleaner → Data Analyst**; documentation/report still synthesises the run.
- Heuristic keywords for data analysis.
- Course-facing aliases in agent descriptions (Code Auditor / Code Fixer / Automated Test Writer).

### Frontend (Impeccable Operate)

- Work tab DAG layout: parallel ranks as columns with dependency labels (`data-testid="workflow-dag"`).
- New **Build** tab: drag-reorder workflow builder with plan preview + run (`WorkflowBuilder`).
- New `/login` page: Google button when configured; local operator identity otherwise. No fake success path.
- CSS for DAG columns and builder; no new UI framework.

### Not claimed

- Full pixel-perfect Figma drag canvas / React Flow.
- Email/password auth (Google + local operator remain the real paths).
- Course repo updates or pushes.
- Jira ceremony evidence (SCRUM-70/71).

## Jira story status (evidence-based)

| Band | Status |
|------|--------|
| SCRUM-42..47 DAG / persistence | Done (pre-existing + verified) |
| SCRUM-48 handoff | Done (pre-existing) |
| SCRUM-49 retries | Done (default 3 this pass) |
| SCRUM-50 status tracking | Done (pre-existing) |
| SCRUM-51..54 builder / DAG viz | Implemented this pass (HTML5 DnD + ranked DAG) |
| SCRUM-55 live dashboard | Done (polling Work tab + DAG columns) |
| SCRUM-56 API integration | Done (real `/tasks`, `/tasks/plan`, workflows) |
| SCRUM-57..60 code pipeline | Done (security/coding/testing/review agents) |
| SCRUM-61..62 data + report | Done this pass (cleaner + analyst + documentation) |
| SCRUM-63..69 tests | Existing suite + matrix doc; run results in test matrix |
| SCRUM-101 login | `/login` page + Google when configured |

## Git

- Branch `sprint-2-implementation` pushed to personal `origin`; CI via pull request.
