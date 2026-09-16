---
name: Docs refresh and guardrails
overview: Produce a documentation audit, remediate stale docs (config-not-code, four-layer config, modeling modes, dmps-*-selected exports, canonical profile names), finalize the Quarto decision record and TikZ->SVG migration, and add CI guardrails so drift can't recur. Quarto is kept as-is; the decision record is updated and validated.

> **Status: COMPLETE.** Audit published; active docs aligned to four-layer `actionConfig`; CI gates `check_doc_freshness.sh` and guarded Quarto book smoke.

azure_devops:
  type: Feature
  title: "Documentation refresh and CI guardrails"
  work_item_id: 501
  epic_id: 413
todos:
  - id: audit-report
    content: Write docs/architecture/documentation-audit-2026-07.md (findings by severity + Quarto keep-analysis + fix checklist); link from DOCUMENTATION_AUDIT.md and architecture/index.md
    status: completed
    work_item_id: 502
  - id: fix-precedence
    content: Align precedence wording (drop 'package defaults', no Python fallback) in 02-project-config-and-layout.qmd, domain-program-language.md, config-parameter-matrix.md
    status: completed
    work_item_id: 503
  - id: fix-config-theory
    content: Rewrite theory ch.11-project-configuration.qmd and reframe configuration-reference.qmd around four-layer/actionConfig; fix output tree to dmps-*-selected.csv
    status: completed
    work_item_id: 504
  - id: fix-analyte
    content: Rewrite ANALYTE_PROFILES.md around regulatory.primary_analyte + profile/site actionConfig
    status: completed
    work_item_id: 505
  - id: modeling-modes
    content: Document modeling modes, split BA targets, recurrence source, and generic profiles in usage ch.05 + theory ch.12
    status: completed
    work_item_id: 506
  - id: profile-names
    content: Replace deprecated profile names with canonical (mc_dmp_*, mc_gene_*, mc_gene_fc) in usage ch.05, check READMEs, and domain-program-language.md examples/tables
    status: completed
    work_item_id: 507
  - id: dmp-exports
    content: Make dmps-*-selected.csv the primary export narrative in detector theory/usage, configuration-reference, methyldmpselect README; mark classifier-extended transitional
    status: completed
    work_item_id: 508
  - id: workflow-engine-docs
    content: Update pipeline_architecture.md, portal_study_lifecycle.md, and contract capability docs to drop step_config as authoritative
    status: completed
    work_item_id: 509
  - id: validation-usage
    content: Rewrite methylvalidation USAGE.md config section to profile/resolvedConfig/mc_config.json flow; remove max_dmps:500 and package-defaults claims
    status: completed
    work_item_id: 510
  - id: package-sweep
    content: Sweep remaining step_config/defaults references across methylenricher/methylpredictor/methyldetector/methylmapper/methyldiseaseprogression docs and theory ch.04/05/15
    status: completed
    work_item_id: 511
  - id: quarto-record
    content: "Update documentation-toolchain.md: keep Option A, add Validated-2026-07 note, record Usage stays Quarto"
    status: completed
    work_item_id: 512
  - id: tikz-svg
    content: Migrate remaining usage-chapter inline TikZ workflow figures to Mermaid src + pre-rendered SVG
    status: completed
    work_item_id: 513
  - id: ci-freshness
    content: Add scripts/check_doc_freshness.sh + test for stale tokens; wire into .github/workflows/pr.yml
    status: completed
    work_item_id: 514
  - id: ci-quarto
    content: Add guarded 'quarto render docs/theory docs/usage --to html' step to CI
    status: completed
    work_item_id: 515
  - id: regen-verify
    content: Regenerate _book/ and SVGs; run all doc checks; promote plan to docs/plans/
    status: completed
    work_item_id: 516
---

# Documentation Full Refresh + Guardrails

Quarto stays (Theory needs LaTeX math, `references.bib`, `@eq-`/`@sec-` cross-refs; MkDocs/MyST already rejected). This plan updates/validates that decision, fixes the drift, and gates CI so it cannot recur.

## Root causes of drift
- Code moved to a **four-layer config** model and **rejects `step_config`** in study manifests ([pipeline_config.py](../../packages/methylutils/methyl_utils/pipeline_config.py)), removed Python science defaults ([caps.py](../../packages/methylgeneselect/methyl_gene_select/caps.py)), added **modeling modes** ([modeling_modes.py](../../packages/methylvalidation/methyl_validation/modeling_modes.py)) and switched exports to `dmps-*-selected.csv`.
- Docs still teach `step_config`, "package defaults", `classifier`/`classifier-extended` exports, and deprecated profile names.
- CI never gated docs against code (no `quarto render`, no stale-token grep).

## Phase 1 - Audit deliverable
- Add `docs/architecture/documentation-audit-2026-07.md`: findings by severity, the Quarto-vs-Markdown analysis (keep-Quarto rationale + gaps), and a checklist mapping each stale file to its fix. Link it from [docs/DOCUMENTATION_AUDIT.md](../DOCUMENTATION_AUDIT.md) and [docs/architecture/index.md](../architecture/index.md).

## Phase 2 - Critical config-not-code / four-layer rewrites
- Rewrite [docs/theory/chapters/11-project-configuration.qmd](../theory/chapters/11-project-configuration.md): remove the "`step_config` dictionary" model; reframe around study manifest (cohorts/paths/`regulatory`) + profile/site `actionConfig` + program overrides; fix output tree to `dmps-*-selected.csv`.
- Reframe [docs/reference/configuration-reference.qmd](../reference/configuration-reference.md): present step schemas as **resolver targets** under `actionConfig.<action>`, not study-manifest keys.
- Fix the precedence line (drop "-> package defaults", use "no Python fallback for tunable science knobs") in [docs/usage/02-project-config-and-layout.qmd](../usage/02-project-config-and-layout.md), [docs/reference/domain-program-language.md](../reference/domain-program-language.md), [docs/reference/config-parameter-matrix.md](../reference/config-parameter-matrix.md) to match [layer-model.md](../architecture/layer-model.md).
- Rewrite [docs/ANALYTE_PROFILES.md](../ANALYTE_PROFILES.md) around top-level `regulatory.primary_analyte` + profile/site `actionConfig`.

## Phase 3 - Modeling modes, profiles, exports
- Add modeling-mode coverage (enums `dmp_modeling_mode`/`gene_modeling_mode`, split BA targets `dmp_featurecuts_target_ba`/`gene_featurecuts_target_ba`, `stability_gene_recurrence_source`, generic profiles `mc_dmp_discovery`/`mc_dmp_featurecuts`/`mc_gene_mapper`/`mc_gene_featurecuts`/`phase_a_dmp_stability`/`phase_b_gene_from_stable_dmps`) to [docs/usage/05-stage-stability.qmd](../usage/05-stage-stability.md) and a theory note in [12-two-workflows.qmd](../theory/chapters/12-two-workflows.md).
- Replace deprecated profile names with canonical ones in usage ch.05, [buffy_healthy_vs_pca/README.md](../../workflow_engine/domain/checks/buffy_healthy_vs_pca/README.md), [h_pca_good/README.md](../../workflow_engine/domain/checks/h_pca_good/README.md), and the legacy example/table rows in [domain-program-language.md](../reference/domain-program-language.md).
- Make `dmps-*-selected.csv` the primary export narrative in [03-methyldetector.qmd](../theory/chapters/03-methyldetector.md), [configuration-reference.qmd](../reference/configuration-reference.md), [methyldetector USAGE](../../packages/methyldetector/docs/USAGE.md), [methyldmpselect README](../../packages/methyldmpselect/README.md); mark classifier/classifier-extended as transitional.

## Phase 4 - Workflow-engine + package doc sweep
- Update [workflow_engine/docs/pipeline_architecture.md](../../workflow_engine/docs/pipeline_architecture.md) (source of the generated `.qmd`), [portal_study_lifecycle.md](../../workflow_engine/docs/portal_study_lifecycle.md), [sample_prep_capabilities.md](../../workflow_engine/contract/sample_prep_capabilities.md), [validation_planner_capabilities.md](../../workflow_engine/contract/validation_planner_capabilities.md) to drop `step_config` as authoritative.
- Rewrite [packages/methylvalidation/docs/USAGE.md](../../packages/methylvalidation/docs/USAGE.md) "Project Config: step_config.validation" into profile + `METHYL_PROFILE` + `resolvedConfig` + `mc_config.json` snapshot flow; remove `max_dmps: 500` and "package defaults" claims.
- Sweep remaining `step_config.*` / defaults references in methylenricher, methylpredictor, methyldetector, methylmapper, methyldiseaseprogression docs and theory ch.04/05/15 (point tool params to `actionConfig`).

## Phase 5 - Quarto decision record + TikZ->SVG
- Update [documentation-toolchain.md](../reference/documentation-toolchain.md): keep Option A, add a "Validated 2026-07" note, and record that Usage was reviewed and stays Quarto.
- Finish TikZ retirement in the ~11 usage chapters that still embed `{=latex}` TikZ: move workflow figures to Mermaid source under [docs/diagrams/src/](../diagrams/src/), pre-render SVG via [scripts/render_diagrams.sh](../../scripts/render_diagrams.sh), and reference SVG in PDF (per audit rule 8).

## Phase 6 - CI guardrails
- Add `scripts/check_doc_freshness.sh` (mirrors the `check_absent` pattern in [check_doc_links.sh](../../scripts/check_doc_links.sh)) to fail on stale tokens in active docs: `step_config`, "package defaults", `classifier-extended`, `dmps-*-classifier.csv`, `stability_gene_featurecuts_max_dmps.*500`, deprecated profile names. Scope to `docs/**` + `packages/**/docs/**` + `workflow_engine/docs/**`, excluding `_book/`, `.pdf`, `.html`, redirect stubs, and `docs/plans/**`.
- Add a `quarto render docs/theory docs/usage --to html` step to [.github/workflows/pr.yml](../../.github/workflows/pr.yml) (guarded by `command -v quarto`, like the terraform step) so book breakage is caught.
- Add `scripts/tests/test_check_doc_freshness.py` for the new guard.

## Phase 7 - Regenerate artifacts + verify
- Regenerate committed `docs/theory/_book/` and `docs/usage/_book/` (audit rule 10) and any changed SVGs; run `check_doc_links.sh`, `check_doc_freshness.sh`, and diagram `--check`.
- Promote this plan to `docs/plans/` per the repo plan-mode rule.

## Out of scope
- No revert of Quarto; no migration of Usage to Markdown (decision: keep and document).
- No content changes to code; docs only (plus CI scripts/tests).
