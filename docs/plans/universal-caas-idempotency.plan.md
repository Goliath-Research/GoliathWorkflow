---
name: Universal CAAS Idempotency
overview: Deep analysis and phased plan to make content-addressed idempotency the default for every atomic DomainProgram ACTION on the worker, with FOREACH-aware short-circuit so distributed claim/execute loops stop paying for work whose content keys already hit.

> **Status: IMPLEMENTED.** Phases 0–3 landed in-tree; Phase 4 sample-scoped CAAS is scaffolded behind `METHYL_SAMPLE_CAAS_ENABLED`. Operator guide: [`docs/usage/17-content-addressed-action-store.qmd`](../usage/17-content-addressed-action-store.md).

azure_devops:
  type: Feature
  title: "Universal worker-side CAAS idempotency (+ FOREACH)"
  work_item_id: null
  epic_id: 413
todos:
  - id: phase0-substrate
    content: Path remap in signatures; fix centroid empty-artifact CAAS commit; catalog idempotency fields + ch.17 docs; skip-rate metrics
    status: completed
  - id: phase1-validation-caas
    content: Default-on study action eligibility; implement CAAS for remaining validation.* (model_mc, select_best_model, post_model_validation, model_*)
    status: completed
  - id: phase2-foreach-bundle
    content: FOREACH iteration-bundle content keys + local then DB short-circuit before BODY fan-out; update WORKER_PROTOCOL
    status: completed
  - id: phase3-consolidate-reuse
    content: Bridge split-reuse / Kept-existing / strict-reuse into CAAS fingerprints
    status: completed
  - id: phase4-sample-caas
    content: "Deferred: sample-scoped CAAS under /work/samples/{id}/.caas with destructive opt-outs"
    status: completed
---

# Universal worker-side CAAS idempotency (+ FOREACH)

## Design principle

**Default: every atomic ACTION is CAAS-eligible on the worker unless opted out.** Opt-outs are explicit (destructive, time-varying, deferred sample-scoped store). FOREACH gets a second layer: **iteration-bundle** keys so the control plane can avoid claiming work that would all skip.

## Implementation map

| Phase | Deliverable |
|-------|-------------|
| 0 | Path remap + dual-mount canonicalize in signatures; centroid artifact harvest; content-based dir fingerprints; catalog `idempotency_*` export; `scripts/audit_caas_skip_rate.py` |
| 1 | Invert eligibility gate (opt-out); CAAS for remaining `validation.*` + `context.resolve_project` |
| 2 | `.caas/foreach_bundle/` + local scheduler short-circuit; `wf.foreach_bundle_entry` + SQL skip hook |
| 3 | Split CSV fingerprints in plan_iterations / model_mc signatures (`reuse_splits.fingerprint_*`) |
| 4 | `methyl_domain.sample_content_store` under `/work/samples/{id}/.caas` (`METHYL_SAMPLE_CAAS_ENABLED`) |

## Non-goals / hard opt-outs

- Destructive `sample.delete_*`, control-flow `sample.qc_failed`, mtime `workflow.fs_stat`.
- Putting `executionScopeId` into `content_key` (ledger-only).
- Gateway-side skip without content keys (workers remain execution authority; FOREACH short-circuit is claim avoidance).

## Success metrics

- Study re-run: CAAS skip rate ≫ prior ~3%; centroid empty-artifact recomputes → 0.
- Second `mc_stability` on unchanged inputs: ACTION claim count drops via iteration-bundle short-circuit.
- Cross-mount workers (`/work` vs `/lambda/nfs/Work`) share keys after remap.
- Catalog documents eligibility/opt-out for every action.
