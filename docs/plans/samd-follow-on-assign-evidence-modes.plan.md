---
name: SaMD Follow-on Epic
overview: "Phased follow-on (D + Fold): hybrid typed-assign adoption for SamplePrep only (MC stays FOREACH+planner), fill real prostate evidence packages and 510(k)/De Novo scaffolding from existing runs, then fold the five mc_* research axes into samd_research as modeling-mode overlays—without any new SQL NodeTypes."
> **Status: COMPLETED** — 2026-07-10.

azure_devops:
  type: Feature
  title: "SaMD follow-on (assign → evidence → fold mc_*)"
  work_item_id: 539
  epic_id: 413
todos:
  - id: phase-a-sampleprep-assign
    content: Hybrid SamplePrep typed variables/out/optional SWITCH; leave MC FOREACH+planner; compiler tests + v2 doc
    status: completed
    work_item_id: 540
  - id: phase-b-evidence-packages
    content: Fill validation-evidence-index for Plasma, H_PCa_good, Buffy; add 510(k)/De Novo scaffold doc; link regulatory README
    status: completed
    work_item_id: 541
  - id: phase-c-fold-mc-modes
    content: Add samd_research mode overlays; alias mc_* → samd_research+mode; preserve gene-only/PPI behavior; update tests/docs
    status: completed
    work_item_id: 542
  - id: promote-follow-on-plan
    content: Promote to docs/plans/samd-follow-on-assign-evidence-modes.plan.md and README mapping
    status: completed
    work_item_id: 543
---

# SaMD follow-on epic (assign → evidence → fold mc_*)

> **Locked choices:** phased **A → B → C**; fold `mc_*` into **`samd_research` as modeling-mode overlays** (not a single undifferentiated profile); **no new SQL `NodeType`s** — engine stays process-agnostic (assign remains ACTION + `variable_output_binding`).

```mermaid
flowchart LR
  phaseA["A SamplePrep hybrid assign"] --> phaseB["B Prostate evidence + 510k scaffold"]
  phaseB --> phaseC["C Fold mc_* into samd_research modes"]
```

---

## Phase A — SamplePrep hybrid typed assign (MC left alone)

### Goal
Adopt typed assign / SWITCH / typed `variables` where they improve **QC state-machine clarity** in SamplePrep—not to reimplement methylation science in-graph.

### Delivered
1. Hybrid rewrite of `workflow_engine/domain/fixtures/sample_prep.program.json` (+ remediate fixture): typed `variables` with `schemaRef` to `schemas/vars/bool.schema.json`; keep `FOREACH samples` + `parallel: true`.
2. Compiler tests in `workflow_engine/tests/test_domain_compiler.py`.
3. Docs: `docs/reference/domain-program-language-v2.md` hybrid SamplePrep note.

### Explicitly left as-is
MC / lifecycle programs remain FOREACH + planner + profile IF flags.

---

## Phase B — Prostate evidence packages + 510(k)/De Novo scaffolding

### Delivered
1. Filled `docs/regulatory/validation-evidence-index.md` for Plasma, H_PCa_good, Buffy.
2. Added `docs/regulatory/samd-submission-scaffold.md`; linked from regulatory README + usage ch.18.
3. Gap list documented (partitions / pivotal promotion) as follow-up ops.

---

## Phase C — Fold five `mc_*` axes into `samd_research` modes

### Mode matrix (preserve behavior)

| Mode preset id | `dmp_modeling_mode` | `gene_modeling_mode` | Critical overlays |
|----------------|---------------------|----------------------|-------------------|
| `dual_fc` (default `samd_research`) | `featurecuts` | `featurecuts` | current samd_research BA/early-stop/regulatory |
| `dmp_raw` (was `mc_dmp`) | `raw_pool` | `none` | `stability_dmp_freq` > 0; no gene FC |
| `dmp_fc` (was `mc_dmp_fc`) | `featurecuts` | `none` | DMP FC only; selected CSV |
| `gene_enricher` (was `mc_gene`) | `raw_pool` | `none` | **`stability_dmp_freq: 0`** + enricher PPI/STRING defaults |
| `gene_fc` (was `mc_gene_fc`) | `raw_pool` | `featurecuts` | gene FC targets |

### Delivered
1. Mode overlays under `workflow_engine/domain/profiles/modes/*.mode.json`.
2. `pipeline_profiles.load_profile` / `apply_pipeline_profile` fold `mc_*` → `samd_research` + mode; seed `researchMode` into context; support `samd_research` + context `researchMode`.
3. Physical `mc_*.profile.json` kept as deprecated shims (`deprecatedAliasOf` / `researchMode` tags).
4. Docs: DPL, config-parameter-matrix, usage ch.05/16/18.
5. Tests: `test_pipeline_profiles.py`, `test_dmp_gene_modeling_modes.py`.
6. Holdout/pivotal profiles **not** folded into research modes.

---

## Cross-cutting constraints

- **No new SQL NodeTypes**; no engine specialization for SamplePrep/SaMD.
- Study manifests still own cohorts/partitions/regulatory; profiles/modes own science knobs.
