---
name: Hyperparameter Result Versioning
overview: Introduce content-addressed action storage (CAAS) keyed by a cumulative signature so results of every idempotent action are physically versioned by their hyperparameters, canonical paths become symlinks into the store, and identical intermediate results are shared across workflow instances to preserve idempotency.
todos:
  - id: record-schema
    content: Bump ActionExecutionRecord to schema 1.2 with content_key + hyperparam_set_id fields; add CAAS path helpers (caas_root, caas_entry_dir, instance_ledger_path) in packages/methyldomain/methyl_domain/action_result.py.
    status: completed
  - id: content-store
    content: Create packages/methyldomain/methyl_domain/content_store.py implementing atomic, concurrency-safe commit_artifacts_to_store, link_entry_into_place, entry validation, and instance-ledger append.
    status: completed
  - id: content-key
    content: Add compute_content_key in workers/methyl_worker/action_skip.py (sha256 of action_revision + input_signature); verify _normalize_path_strings resolves symlinks so keys stay cumulative.
    status: completed
  - id: skip-reuse
    content: Make maybe_skip_action consult the CAAS entry for the content_key (cross-instance reuse), relink canonical paths, and replay; make record_action_execution commit product artifacts into CAAS and stamp content_key.
    status: completed
  - id: execute-orchestrate
    content: Wire commit/relink + ledger append into execute_task in workers/methyl_worker/handlers.py around the existing skip/run/record calls; gate on METHYL_CAAS_ENABLED.
    status: completed
  - id: hpset-id
    content: Compute + bake hyperparamSetId in finalize_instance_context (hash of resolvedConfig__* slices + optional name); add hyperparamSetId to RUNTIME_INPUT_KEYS; inject it into ACTION templates in compiler._action_template.
    status: completed
  - id: tests
    content: Add unit tests (content-key stability, cross-instance reuse, config-change fork, symlink cumulative signatures, ledger) and an MC smoke end-to-end check; run under .venv.
    status: completed
  - id: docs
    content: Promote plan to docs/plans/hyperparameter-result-versioning.plan.md, update docs/plans/README.md, and document CAAS layout + hyperparamSetId in domain-program-language.md and 10-artifacts-and-qa-checks.qmd.
    status: completed
---

# Hyperparameter Result Versioning — First Step

> **Status: IMPLEMENTED** (first step — CAAS storage, hyperparamSetId, idempotent action integration)

## Goal

Make the results of every idempotent action **versioned by their hyperparameters** on shared storage, while still **reusing** any intermediate result whose inputs and config are unchanged across workflow instances (hyperparameter sets).

Today, idempotency is *path-scoped*: an action writes into a fixed canonical path (e.g. `run_0001/detections/<c>/<d>/`) and a manifest at `{outputDir}/.action_results/{action}.{run_key}.json` records `input_signature` / `output_signature`. If a new hyperparameter set changes an upstream config, the recomputed action **overwrites** the previous result at the same canonical path — so two hyperparameter sets cannot coexist, and results cannot be compared later.

## Approach: Content-Addressed Action Store (CAAS)

Store each action's product artifacts in a content-addressed location keyed by a **cumulative content key**, and turn the canonical per-run paths into **symlinks** into that store.

- Two instances that reach an action with the **same** cumulative key → one physical copy, instant reuse (skip).
- Any config change (own or upstream) → different cumulative key → a **new** store entry; the previous result is preserved.

### Content key

```
content_key = sha256(action_revision + "|" + input_signature)
```

`input_signature` is cumulative by construction: `_normalize_path_strings` resolves symlinks, so upstream CAAS outputs transitively affect downstream keys.

### Storage layout

```
{project_root}/.caas/
    {action_safe}/{content_key}/
        <product artifacts...>
        manifest.json
    instances/{hyperparamSetId}.json
```

`{project_root}` = `{output_base}/{project_name}`.

### Hyperparameter set identity

`finalize_instance_context` bakes `hyperparamSetId` (hash of all `resolvedConfig__*` slices plus optional `hyperparamSetName`). Every ACTION template receives `hyperparamSetId`; workers append `{action}:{run_key} → content_key` to the instance ledger.

### Rollout

- Gated by `METHYL_CAAS_ENABLED=1` or per-task `caasEnabled: true`.
- `forceRerun` / `METHYL_FORCE_RERUN` bypass skip and produce a fresh entry.

### Database (wf schema)

Deploy [`workflow_engine/sql_pg/wf_hyperparameter_set.sql`](../../workflow_engine/sql_pg/wf_hyperparameter_set.sql) (PostgreSQL parity in `sql_mssql/`).

| Table | Purpose |
|-------|---------|
| `wf.hyperparameter_set` | Registry of unique config combinations (`set_key`, optional `display_name`, `config_json`) |
| `wf.workflow_instance.hyperparameter_set_id` | FK linking each run to its hyperparameter set |
| `wf.hyperparameter_set_action_entry` | Queryable ledger: `(set, action, run_key) → content_key` |

Procedures:

- `wf_apply_hyperparameter_set` — called at instance creation from `study_lifecycle` when `hyperparamSetId` is present
- `wf_repo_upsert_hyperparameter_action_entry` — called from gateway after successful task submit when CAAS is enabled

On-disk CAAS (`.caas/`) remains the execution store; the database mirrors identity and ledger for portal queries and cross-instance comparison.

## Key files

- `packages/methyldomain/methyl_domain/action_result.py` — schema 1.2, CAAS path helpers
- `packages/methyldomain/methyl_domain/content_store.py` — commit, relink, ledger
- `workers/methyl_worker/action_skip.py` — `compute_content_key`, CAAS skip/record
- `workers/methyl_worker/handlers.py` — `execute_task` documents CAAS seam
- `workflow_engine/domain/workflow_context.py` — `compute_hyperparam_set_id`
- `workflow_engine/domain/compiler.py` — `hyperparamSetId` in ACTION templates
