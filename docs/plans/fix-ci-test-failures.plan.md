---
name: Fix CI test failures
overview: Repair the 19 failing tests on main — refresh stale worker test doubles, restore native-json MSSQL bindings (plus DDL re-apply), update tabular/model-MC tests to the fail-closed test-partition contract, and install samtools/bedtools in the PR pipeline.

> **Status: IMPLEMENTED.** Dev Azure SQL procs re-typed to native `json`; `mssql.py` CAST bindings restored; worker/validation/CI fixtures updated. Verified via targeted suite + `scripts/run_tests_ci.sh`.

azure_devops:
  type: Feature
  title: "Fix CI test failures (native JSON + stale doubles)"
  work_item_id: null
  epic_id: 413
todos:
  - id: mssql-ddl
    content: Re-apply wf_repository_api.sql and wf_worker_api_contract.sql to the dev Azure SQL DB, then verify all JSON proc params report type 'json'
    status: completed
    work_item_id: null
  - id: mssql-code
    content: Restore _declare_json/CAST bindings for create_workflow_instance and worker_submit_result in mssql.py
    status: completed
    work_item_id: null
  - id: worker-doubles
    content: "Refresh worker test doubles: TaskPollResult returns, handle= kwarg on fake actions, run_cancellable patch targets"
    status: completed
    work_item_id: null
  - id: env-fragile
    content: Fix MAX_ARG_STRLEN-sensitive large-stdout test and the MethylExtractor --read-level probe fixture
    status: completed
    work_item_id: null
  - id: validation-tests
    content: Update 5 tabular tests to save_test_dataset=False and make the model-MC resume fake emit test_metrics.json
    status: completed
    work_item_id: null
  - id: ci-host-tools
    content: Install samtools and bedtools in ci/azure-pipelines-pr.yml before the regression suite
    status: completed
    work_item_id: null
  - id: verify
    content: Run the nine touched test files, then the full suite via scripts/run_tests_ci.sh
    status: completed
    work_item_id: null
---

# Fix CI test failures

## Diagnosis

Four clusters caused 19 CI failures on `main`:

1. **Stale worker test doubles** — `TaskPollResult`, `handle=` on `action.execute`, `run_cancellable` instead of `subprocess.run`.
2. **MSSQL JSON binding drift** — `mssql.py` bound `@context_json` / `@output_json` as bare `?` while DDL and policy tests require native `json`. Live DB confirmed both procs were still `nvarchar` until re-applied.
3. **Model-MC / tabular partition contract** — tests predated fail-closed `test_groups.json` rules.
4. **Hosted-agent environment** — missing `samtools`/`bedtools`; large-stdout argv exceeded `MAX_ARG_STRLEN` on 4 KiB-page agents.

## Delivered

- Re-applied `wf_repo_create_workflow_instance` and `sp_worker_submit_result` with native `json` params on the dev Azure SQL DB.
- Restored `_declare_json` / `CAST(? AS json)` bindings in [`workflow_engine/rest/db/mssql.py`](../../workflow_engine/rest/db/mssql.py).
- Updated worker and methylvalidation tests; installed host CLIs in [`ci/azure-pipelines-pr.yml`](../../ci/azure-pipelines-pr.yml).
