# MethylPipeline Integrity and Design Review

> **Remediation status (2026-07-01):** All prioritized follow-ups executed. Full suite now
> **1002 passed, 3 skipped, 0 failed**; pytest collection clean (no `test_runner` collision);
> schema-drift (4 exporters), guard scripts, and package imports all green. See
> [Remediation log](#remediation-log) at the end for per-finding resolutions.

> **Date:** 2026-07-01  
> **Scope:** Whole repository (17 packages, workers, workflow_engine, schemas, docs)  
> **Context:** ~31 commits in the prior 3 days (MC centroid seed/deltas, unified `action_run_log`, `project_resolver` run-dir fixes, `--group all` CLI disambiguation, config-not-code refactors)  
> **Method:** Automated verification + read-only design review (no source changes)

## Executive summary

**Overall:** The repository is **architecturally sound** and **operationally functional** for the Buffy MC stability path that was debugged in this cycle. Schema drift checks, guard scripts, and release script syntax all pass. The critical production bug (`--group all` running every cohort) is fixed and covered by tests.

**Test health is degraded:** 45 failing tests (951 passing) plus a **collection blocker** (`test_runner.py` name collision). Most failures are **stale test fixtures** (legacy `step_config`, outdated golden outputs, missing `/work` sample CSVs) rather than regressions in the MC centroid path.

**Design gaps to close:** idempotency/collector false-success for centroids (empty `artifacts` still skips), `copy_centroid_seed_baseline` does not validate seed HDF5 presence, and docs still mention "package defaults" in the precedence chain.

---

## Track A — Automated verification results

| Check | Result | Notes |
|-------|--------|-------|
| `pytest -m "not gpu and not slow"` | **FAIL** (45 failed, 951 passed, 3 skipped) | Full collection: 999 tests + **1 collection error** |
| `pytest --collect-only` | **FAIL** | Module name collision on `test_runner` |
| Package import sweep (18 modules) | **MOSTLY PASS** | `methyl_cluster` fails: `No module named 'methyl_utils.beta_analytics'` |
| `methyl-export-config-schemas --check` | **PASS** | 18 artifacts |
| `methyl-export-domain-schemas --check` | **PASS** | 13 artifacts |
| `methyl-export-task-schemas --check` | **PASS** | 66 artifacts |
| `methyl-export-action-catalog --check` | **PASS** | 37 actions (was 33 at review time) |
| `scripts/check_no_step_config.py` | **PASS** | |
| `scripts/check_task_input_config_boundary.py` | **PASS** | |
| `scripts/check_windows_paths.py` | **PASS** | 5735 tracked paths |
| `scripts/check_doc_links.sh` | **PASS** | |
| `bash -n` release scripts | **PASS** | `build_release.sh`, `assemble_release.sh`, `promote_release.sh` |
| Recent-change targeted tests | **PASS** | 26 tests: `test_workflow_planner`, `test_cli_group_all_disambiguation`, `test_action_run_log`, `test_action_skip` |

### Pytest collection blocker

```
ERROR collecting workers/tests/test_runner.py
imported module 'test_runner' has this __file__ attribute:
  packages/methyldmpselect/tests/test_runner.py   # collected first
  workers/tests/test_runner.py                   # conflicts
```

**Impact:** `pytest` from repo root cannot collect the full suite in one pass. Running `workers/tests/test_runner.py` in isolation works. Workaround used for this review: `--ignore=workers/tests/test_runner.py` (951 tests executed).

**Recommendation:** Rename one file (e.g. `workers/tests/test_worker_runner.py`).

### Failure breakdown by package (45 failures)

| Package / area | Failures | Dominant theme |
|----------------|----------|----------------|
| `methylpredictor` | 10 | `test_group_paths` API / resolver contract changes |
| `methylvalidation` | 16 | `sample_prep_planner` fixtures still use `step_config`; queue workflow golden drift |
| `workflow_engine` | 6 (12 when run as `workflow_engine/`) | Missing `/work/projects/prostate-cancer/data/PCaH.csv`; profile/compiler drift |
| `methylenricher` | 5 | `step_config` / queue planner expectations |
| `methylalignmentqc` | 2 | `step_config` in resolver tests |
| `workers` | 2 | Golden `validation.plan_iterations` fixture stale; methyl_extract idempotency |
| `methylclassifier` | 1 | Native multiclass smoke |
| `methyldomain` | 1 | `StratifiedCohortDraw` test missing required `taskConfig` fields |

**Example failure (representative):** `test_use_project_samples` fails because test project JSON still contains `step_config`, which `ProjectConfig` now rejects:

```
ValidationError: step_config was removed from study manifests.
Use pipeline profile actionConfig + site manifest.
```

### Per-area pytest (approximate)

| Area | Outcome |
|------|---------|
| `tools/` | 11 passed |
| `workers/` | 200 passed, 1 failed (+ collection conflict at root) |
| `workflow_engine/` | 95 passed, 12 failed, 2 skipped |
| `packages/` | Collection error at area root; ~33 failures when run via full suite ignore |

GPU and slow smokes were **not** run (live MC workflow on GPU during review).

---

## Track B — Design and architecture assessment

### 1. Four-layer configuration model

**Status: Mostly consistent**

The implementation in [project_gen.py](../../packages/methylvalidation/methyl_validation/project_gen.py), [workflow_planner.py](../../packages/methylvalidation/methyl_validation/workflow_planner.py), and [action_config_resolver.py](../../packages/methylutils/methyl_utils/action_config_resolver.py) correctly separates:

- Study manifest (`project.json` / `run_XXXX/project.json`)
- Profile (`*.profile.json`)
- Site (`/work/site/methyl_site.json`)
- DomainProgram / compiled workflow

MC iteration centroids use `build_cohort_relative_centroid_scope()` with `centroidSeedDir`, `centroidDir`, and cohort-relative `removeSamples` — matching [parallel-mc-centroid-seed.plan.md](../plans/parallel-mc-centroid-seed.plan.md).

**Doc drift:** [layer-model.md](layer-model.md) line 19 still lists **"package defaults"** as the lowest precedence layer. [AGENTS.md](../../AGENTS.md) and [.cursor/rules/config-not-code.mdc](../../.cursor/rules/config-not-code.mdc) state there should be **no Python fallback** for tunable science knobs. Update layer-model precedence to match.

### 2. Config-not-code compliance

**Status: Partial — improving but not complete**

| Pattern | Finding |
|---------|---------|
| `apply_*_defaults()` | **None found** (good) |
| Gene FC caps ([caps.py](../../packages/methylgeneselect/methyl_gene_select/caps.py)) | **Compliant** — returns `(None, None)` when unset |
| `MonteCarloConfig` caps | `stability_gene_featurecuts_max_dmps/max_genes` use `Optional[int] = Field(default=None)` (good); `observed_feature_max_genes: int = Field(default=32)` remains a code default |
| `DEFAULT_*` constants | Present in deployment/infra paths (`DEFAULT_SITE_PATH`, `DEFAULT_EPIMETHYL_ROOT`) — acceptable. **Science/ops knobs** remain in [gene_disease_enricher.py](../../packages/methylmapper/methyl_mapper/gene_disease_enricher.py) (`DEFAULT_GROK_BATCH_SIZE`, cache TTLs, worker counts) and [methyl_enricher](../../packages/methylenricher/methyl_enricher/) — should migrate to site/profile |
| Study `step_config` | **Rejected at runtime** by `ProjectConfig`; guard script passes on tracked manifests but **tests still use legacy fixtures** |

### 3. Recent-change coherence (~31 commits)

**Status: Coherent for MC centroid path; production-validated**

```mermaid
flowchart LR
  plan["validation.plan_iterations"] --> seed["centroid_seed FOREACH"]
  seed --> iter["iterations FOREACH"]
  iter --> copy["copy_centroid_seed_baseline"]
  copy --> centroid["methyl-centroid per chr"]
  centroid --> detector["methyl-detector"]
```

| Change | Assessment |
|--------|------------|
| `group_token_requests_all_groups()` + CLI fix ([97ddbd45](https://github.com/)) | **Critical fix.** `--group all` now targets cohort label `all` when present. Covered by [test_cli_group_all_disambiguation.py](../../packages/methylcentroid/methyl_centroid/tests/test_cli_group_all_disambiguation.py). **Production confirmed:** `run_0001` wrote 24+24 HDF5, detector stage reached. |
| `output_dir` / `--chromosome` / `--context` in project mode | **Working** — single-combination runs (`Processing 1/1`) |
| `build_cohort_relative_centroid_scope` + seed copy in [centroid.py](../../workers/methyl_worker/actions/centroid.py) | **Correct design** — seed HDF5 copied before incremental methyl-centroid |
| Unified [action_run_log.py](../../workers/methyl_worker/action_run_log.py) | **Implemented** — all ACTION categories log when log root resolves; docs updated in [domain-program-language.md](../reference/domain-program-language.md) and [WORKER_PROTOCOL.md](../../workers/WORKER_PROTOCOL.md) |
| Typed models (`CentroidGroupScope`, `CentroidSeedGroup` in [types.py](../../packages/methyldomain/methyl_domain/types.py)) | **Present** with `extra="forbid"` on wire models |

**Remaining loose end:** `copy_centroid_seed_baseline()` ([project_gen.py:539](../../packages/methylvalidation/methyl_validation/project_gen.py)) copies the tree unconditionally and returns `True` if `src.is_dir()` — **does not verify any `*.h5` exist**. This allowed the original MC failure (empty seed dir, `start=0`).

### 4. Idempotency and collectors

**Status: Design weakness — caused production incident**

| Component | Behavior | Risk |
|-----------|----------|------|
| [CentroidLegacyCollector](../../workers/methyl_worker/collectors.py) | Sets `"status": "ok"` unconditionally; `centroid_h5_path` only set if `*.h5` found in `outputDir` | Manifest can show success with no HDF5 |
| [verify_artifacts()](../../workers/methyl_worker/action_skip.py) | Returns `True` for **empty** `artifacts` list | Skip replay accepts false-success manifests |
| [maybe_skip_action()](../../workers/methyl_worker/action_skip.py) | Requires `result_code == 0` + signature match + `verify_artifacts` | Empty artifacts pass verification |

**Observed in production:** Control seed manifests at `_centroid_seed/.../healthy/all/.action_results/` had `result_code: 0`, `artifacts: []`, `centroid_h5_path: null` while HDF5 were written to the wrong study-root path.

**Recommendations:**
1. For `pipeline.centroid`, collector should set non-zero / failed status when `outputDir` has no `{chrom}-{ctx}.h5` after run.
2. `verify_artifacts([])` should return `False` for actions that declare required output kinds, or centroid manifests must always record the HDF5 in `artifacts`.
3. `copy_centroid_seed_baseline` should raise if zero `*.h5` in seed dir.

### 5. Schema / catalog / DB parity

| Source | Count | Match? |
|--------|-------|--------|
| Git `schemas/actions/catalog.json` | 37 actions (was 33 at review time) | Baseline |
| `methyl-export-action-catalog --check` | 37 actions | **PASS** |
| PostgreSQL `wf.workflow_action_schema` | 33 input + 33 output = 66 rows | **PASS** (2 rows per action) |
| Azure SQL `wf.workflow_action_schema` | Query succeeded; direction/group count returned | **Likely PASS** (row data not fully captured in MCP response) |
| Compiled workflow vs program | `buffy_mc_stability` compiled JSON includes `centroid_seed`, `centroidSeedDir` bindings | **Consistent** with [mc_stability.program.json](../../workflow_engine/domain/fixtures/mc_stability.program.json) |

Task schema export: 66 artifacts — aligns with typed task input/output models.

### 6. Documentation vs code

| Document | Status |
|----------|--------|
| [domain-program-language.md](../reference/domain-program-language.md) | **Aligned** on `action_run_log.jsonl`, signature skip, idempotency fields |
| [WORKER_PROTOCOL.md](../../workers/WORKER_PROTOCOL.md) | **Aligned** on unified timeline log |
| [layer-model.md](layer-model.md) | **Drift** — mentions "package defaults" in precedence |
| [AGENTS.md](../../AGENTS.md) | **Aligned** with four-layer model and config-not-code |
| Plan [parallel-mc-centroid-seed.plan.md](../plans/parallel-mc-centroid-seed.plan.md) | Implementation matches intended seed → iteration delta flow |

---

## Findings by severity

### Blocker

None for the currently running Buffy MC path after `--group all` fix.

### High

| ID | Finding | Location | Recommendation |
|----|---------|----------|----------------|
| H1 | `test_runner.py` module name collision blocks full pytest collection | `packages/methyldmpselect/tests/test_runner.py` vs `workers/tests/test_runner.py` | Rename `workers/tests/test_runner.py` → `test_worker_runner.py` |
| H2 | Centroid idempotency accepts empty artifacts | [action_skip.py:294-305](../../workers/methyl_worker/action_skip.py), [collectors.py:336-370](../../workers/methyl_worker/collectors.py) | Require HDF5 artifact for `pipeline.centroid`; fail skip when `artifacts` empty |
| H3 | Seed copy does not validate HDF5 presence | [project_gen.py:539-554](../../packages/methylvalidation/methyl_validation/project_gen.py) | Raise clear error if seed dir has zero `*.h5` before iteration deltas |

### Medium

| ID | Finding | Location | Recommendation |
|----|---------|----------|----------------|
| M1 | 45 tests fail — mostly stale `step_config` fixtures | `methylvalidation/tests/test_sample_prep_planner.py`, enricher/predictor tests | Batch-migrate test project JSON; run `migrate_project_config.py` on fixtures |
| M2 | Golden output fixture stale for `validation.plan_iterations` | [workers/tests/test_golden_task_outputs.py](../../workers/tests/test_golden_task_outputs.py) | Regenerate golden after `centroidSeedGroups` schema change |
| M3 | Workflow profile tests require missing `/work` CSVs | [test_pipeline_profiles.py](../../workflow_engine/tests/test_pipeline_profiles.py) | Use tmp_path fixtures instead of production paths |
| M4 | `methyl_cluster` import broken | `methyl_cluster` → `methyl_utils.beta_analytics` | Add missing module or make import optional |
| M5 | Doc precedence lists "package defaults" | [layer-model.md:19](layer-model.md) | Align with config-not-code: site/profile only, no package science defaults |
| M6 | Grok/mapper operational defaults in code | [gene_disease_enricher.py](../../packages/methylmapper/methyl_mapper/gene_disease_enricher.py) | Move to site `actionConfig` or profile |

### Low

| ID | Finding | Location | Recommendation |
|----|---------|----------|----------------|
| L1 | Pydantic v2 `class Config` deprecation warnings | methylclassifier, methylpredictor, sqlmodel | Migrate to `ConfigDict` |
| L2 | `methyldomain` test missing required `taskConfig` fields | [test_domain_types.py](../../packages/methyldomain/tests/test_domain_types.py) | Update fixture to match `StratifiedCohortDraw` schema |
| L3 | CI PR pipeline does not run full pytest | [azure-pipelines-pr.yml](../../ci/azure-pipelines-pr.yml) | Add pytest job (or document intentional omission) |

---

## Prioritized follow-up list

1. **H2 + H3** — Harden centroid seed copy and idempotency (prevents recurrence of MC `start=0` silent failure).
2. **H1** — Fix `test_runner` name collision so CI can run the full suite.
3. **M1 + M2** — Refresh test fixtures and golden outputs after `step_config` removal and MC planner schema changes.
4. **M5** — Update layer-model precedence documentation.
5. **M3** — Decouple workflow_engine tests from `/work` production paths.
6. **M4** — Fix or document `methyl_cluster` / `beta_analytics` dependency.
7. **M6** — Continue config-not-code migration for mapper/enricher knobs.

---

## Conclusion

MethylPipeline's **core architecture remains sound**: disease-agnostic, four-layer config, typed task schemas, signature-based idempotency, and unified observability are all implemented and largely documented. The **recent MC centroid work is coherent and production-validated** after the `--group all` CLI fix.

The main integrity gaps are **test-suite hygiene** (stale fixtures, collection collision) and **operational hardening** (centroid collector/skip and seed validation). Neither blocks the current `run_0001` execution path, but both should be addressed before treating CI green as a release gate.

**Review artifacts:** `.review-scratch/` (pytest output, schema drift, guards) — local only, not committed.

---

## Remediation log

All findings from the prioritized list were addressed on 2026-07-01.

| ID | Resolution |
|----|-----------|
| H1 | Renamed `workers/tests/test_runner.py` → `test_worker_runner.py`; collection now yields 1005 tests, no module-name collision. |
| H2 | `pipeline.centroid` now fails when a "successful" run writes no HDF5 at `outputDir` ([centroid.py](../../workers/methyl_worker/actions/centroid.py) `_require_centroid_hdf5`); `maybe_skip_action` refuses to replay a centroid manifest with zero artifacts (`_requires_output_artifacts` in [action_skip.py](../../workers/methyl_worker/action_skip.py)). New tests in [test_action_skip.py](../../workers/tests/test_action_skip.py). |
| H3 | [`copy_centroid_seed_baseline`](../../packages/methylvalidation/methyl_validation/project_gen.py) raises `FileNotFoundError` on a present-but-empty seed dir; worker fails loudly when a declared seed produces no baseline. Test in [test_centroid_seed_copy.py](../../workers/tests/test_centroid_seed_copy.py). |
| M1 | Migrated stale `step_config` fixtures (predictor, enricher, alignmentqc, sample_prep, queue_workflow) to site/profile `actionConfig` via `METHYL_SITE_CONFIG`, or to top-level `regulatory`. |
| M2 | Regenerated golden `validation.plan_iterations` output to match `ValidationPlannedIteration`; completed `StratifiedCohortDraw` taskConfig fixture. Also fixed real bugs: `predictor.py` `class_names` used before assignment; sklearn ≥1.7 `LogisticRegression(multi_class=...)` removal; `production_enricher_root` returning `enricher/<control>` instead of `enricher/`. |
| M3 | Added [workflow_engine/tests/conftest.py](../../workflow_engine/tests/conftest.py) `local_project` factory that rewrites committed projects onto temp sample CSVs + H5 evidence; profile/compile tests no longer need `/work` data. |
| M4 | Restored [beta_analytics.py](../../packages/methylutils/methyl_utils/beta_analytics.py) (`beta_log_pdf`) and wired it into `methyl_utils`; fixes `import methyl_cluster`. Verified bit-exact against `scipy.stats.beta.logpdf`. |
| M5 | [layer-model.md](layer-model.md) precedence now states no Python fallback for tunable science knobs. |
| M6 | Verified mapper/enricher/model_bundle operational knobs already resolve from site/profile `actionConfig` via `resolve_for_project`; remaining module-level `DEFAULT_*` are permitted library-API fallbacks for non-science infra/behavior knobs (no change needed). |
| Extra | Fixed cross-test pollution: `test_local_engine.py` set `WORKER_STUB_EXTERNAL` via `os.environ` (now `monkeypatch`), which had leaked into `test_methyl_extract_idempotent_when_outputs_exist`. |
