# Sprint 1 application test cases

Each test case from the Sprint 1 user stories (US_01 to US_05) is automated. Backend cases
run in the `Backend` CI job; UI cases run in the `Browser e2e smoke (Playwright)` job
against the Docker stack in Demo Mode.

| TC | Story | Scenario | Automated test |
|---|---|---|---|
| TC_01 | US_01 | Enroll an agent with valid details | `backend/tests/test_sprint1_acceptance.py::test_tc01_enroll_agent_with_valid_details` |
| TC_02 | US_01 | Enroll with a missing required field | `test_tc02_enroll_with_missing_required_field`, `test_tc02_empty_capability_list_is_rejected` |
| TC_03 | US_01 | Enroll a duplicate agent name | `test_tc03_enroll_duplicate_agent_name`, `test_tc03_builtin_names_are_also_protected` |
| TC_04 | US_01 | Enrollment speed and single request | `test_tc04_enrollment_is_a_single_fast_request` |
| TC_05 | US_01 | Disable an enrolled agent | `test_tc05_disabled_agent_is_never_spawned` (plus re-enable and update tests) |
| TC_06 | US_02 | Brief needing several capabilities | `test_tc06_brief_needing_several_capabilities` |
| TC_07 | US_02 | Brief needing one capability | `test_tc07_brief_needing_one_capability` |
| TC_08 | US_02 | Brief with no matching agent | `test_tc08_brief_with_no_matching_agent` |
| TC_09 | US_02 | Empty or vague brief | `test_tc09_empty_brief_is_blocked`, `test_tc09_vague_brief_gets_a_clarifying_question` |
| TC_10 | US_02 | Same brief submitted twice | `test_tc10_same_brief_twice_creates_separate_instances` |
| TC_11 | US_02 | Selection reason is shown | `test_tc11_selection_reason_is_shown` |
| TC_12 | US_03 | Table created on enrollment | `test_tc12_table_created_on_enrollment` |
| TC_13 | US_03 | Unsafe table name | `test_tc13_unsafe_table_name_is_sanitised`, `test_tc13_unsafe_property_names_are_rejected` |
| TC_14 | US_03 | Repeat table creation | `test_tc14_repeat_table_creation_keeps_data`, `test_tc14_new_schema_fields_add_columns` |
| TC_15 | US_03 | Table creation failure rolls back enrollment | `test_tc15_table_creation_failure_rolls_back_enrollment` |
| TC_16 | US_04 | Reject a malformed schema | `test_tc16_invalid_json_is_rejected`, `test_tc16_unknown_schema_type_is_rejected_naming_the_field`, `test_tc16_non_object_output_schema_is_rejected` |
| TC_17 | US_04 | Store valid agent output | `test_tc17_valid_output_is_written_to_the_agent_table` |
| TC_18 | US_04 | Output with a missing required field | `test_tc18_output_missing_a_required_field` |
| TC_19 | US_04 | Output with the wrong data type | `test_tc19_output_with_the_wrong_data_type` |
| TC_20 | US_05 | Submit a brief from the UI | `frontend/e2e/sprint1.spec.ts` "TC_20 ..." |
| TC_21 | US_05 | Empty brief blocked in the UI | `frontend/e2e/sprint1.spec.ts` "TC_21 ..." |
| TC_22 | US_05 | Agents page matches the API | `frontend/e2e/sprint1.spec.ts` "TC_22 ..." |
| TC_23 | US_05 | Backend error shown to the user | `frontend/e2e/sprint1.spec.ts` "TC_23 ..." |

## How the stories are implemented

- **Enrollment (US_01):** `POST /api/v1/agents` takes name, description, capabilities,
  supported models, input/output schema and cost profile, and returns the agent with a
  generated id and `status: active`. `PATCH /api/v1/agents/{id}` updates an agent;
  `{"enabled": false}` disables it so it is never offered to the orchestrator. Names are
  unique regardless of case.
- **Spawning (US_02):** each spawned agent is a workflow node with its own instance `id`
  and status. Skipped agents and their reasons are in `selection.excluded`. A brief with
  no meaningful words gets a clarifying question (422) instead of spawning agents.
- **Dynamic tables (US_03):** every agent gets a table `agent_data.out_<agent id>` with one
  column per top-level output property (`string` → text, `integer` → bigint, `number` →
  double precision, `boolean` → boolean, anything else → jsonb). The agent row and its
  table are created in one transaction. `GET /api/v1/agents/{id}/records` reads it back.
- **Validation (US_04):** schemas are checked as JSON Schema at enrollment, naming the bad
  field. Output is validated before it is stored; invalid output fails the step after its
  retries, is never written to the agent's table, and is logged with the agent id and the
  failing fields.
- **Frontend (US_05):** the Agents tab lists the registry (capabilities and status) and
  has an enrollment form. The Work tab shows each spawned agent's status and why it was
  selected, plus the agents that were not spawned and why.
