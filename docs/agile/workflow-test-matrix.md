# Workflow test matrix (J-1)

The twelve required scenarios and where they are covered. All LLM calls are faked or
HTTP-mocked. No test spends money.

| Scenario | Primary tests |
|----------|----------------|
| Single agent | `test_single_agent_runs.py`, `POST /tasks` with a narrow security request |
| Sequential | `test_workflow_engine.py` (security → coding → documentation) |
| Parallel | `test_parallel_execution.py` |
| Conditional branch | `test_conditional_workflows.py` (empty findings skip coding) |
| Agent failure | `test_retry_and_recovery.py`, `test_workflow_engine.py` failed branch |
| Agent retry | `test_retry_and_recovery.py` (`seed_fast_retries`) |
| Provider failure | `test_agent_executor.py` fallback; `test_providers.py` HTTP mapping |
| Invalid agent output | `test_output_validation.py`, executor invalid-output path |
| Cancellation | `test_retry_and_recovery.py` |
| Resume | `test_retry_and_recovery.py` restore from persisted state |
| Agent skipped | `test_conditional_workflows.py` |
| Human approval | `test_approval.py` |

Supporting collaboration coverage (not a substitute for the twelve):

| Behaviour | Tests |
|-----------|--------|
| Direct agent message + inbox | `test_message_bus.py` |
| Workflow hand-off as a bus message | `test_workflow_handoff_is_a_direct_agent_message` |
| Private vs shared memory | `test_private_memory_is_not_visible_to_another_agent` |
| Artifact reference | `test_artifact_is_a_reference_not_a_blob` |
| Cost / retries / failing provider | `test_metrics.py` |
| Provider conformance | `test_providers.py` (`all_adapters`) |
