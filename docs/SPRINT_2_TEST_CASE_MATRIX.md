# Sprint 2 test case matrix

Maps SCRUM-63..69 themes to automated tests in this repository.

| ID | Theme | Automated coverage | Notes |
|----|-------|--------------------|-------|
| S2-DAG-01 | Cycle detection | `backend/tests/test_schemas.py` | WorkflowPlan rejects cycles |
| S2-DAG-02 | Sequential execution | `test_workflow_engine.py` | Linear dependency chain |
| S2-DAG-03 | Parallel execution | `test_parallel_execution.py` | Independent nodes concurrent |
| S2-DAG-04 | Conditional edges | `test_conditional_workflows.py` | Security→code on findings |
| S2-HO-01 | Structured handoff | `test_message_bus.py`, engine upstream payload | Invalid output not stored |
| S2-RT-01 | Retry / recovery | `test_retry_and_recovery.py` | Retryable vs fail-fast |
| S2-ST-01 | Status / cancel / resume | `test_retry_and_recovery.py`, runs API | Workflow + node statuses |
| S2-AG-01 | Specialist agents | seed + orchestration tests | Auditor/fixer/tester aliases |
| S2-AG-02 | Data pipeline | planner capabilities + new analyst agent | Clean → analyse → report |
| S2-API-01 | Task / workflow APIs | pytest API / orchestration | `/tasks`, `/workflows` |
| S2-AUTH-01 | Auth | `test_jwt_auth.py`, `test_google_and_isolation.py` | Google + session |
| S2-FE-01 | Office / builder UI | Playwright `e2e/sprint2.spec.ts` | Build tab, DAG, `/login` |
| S2-E2E-01 | Regression | CI Backend + Playwright jobs | PR CI is source of truth |

## Execution log (2026-11-03 / 2026-11-04, Docker)

| Suite | Command | Result |
|-------|---------|--------|
| Sprint 2 data pipeline | `pytest tests/test_sprint2_data_pipeline.py` | **2 passed** |
| Parallel / conditional / retry / schemas | `pytest tests/test_{parallel,conditional,retry,schemas,sprint2}*` | **62 passed, 45 skipped** without test DB; with `agentorch_test` full suite green after agent-count update |
| Frontend lint + types | `npm run lint && npm run typecheck` | **Pass** |
| Backend ruff + mypy | `ruff check/format` + `mypy` | **Pass** |
| Playwright Sprint 2 UI | `frontend/e2e/sprint2.spec.ts` | Covered in CI e2e job |

Never mark Pass without an executed run.
