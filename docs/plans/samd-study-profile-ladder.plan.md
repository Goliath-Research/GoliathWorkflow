---
name: SaMD Study Profile Ladder
overview: Define a small, FDA-aligned study creation path: three disease-agnostic pipeline profiles (research → holdout enrichment → pivotal), a study scaffold that always provisions real holdout partitions, and an operator SOP for growing cohorts without leaking holdouts into training—while unknown hyperparameters are discovered via early-stop and hyperparam search only in the research tier.
> **Status: COMPLETED** — 2026-07-10.

azure_devops:
  type: Feature
  title: "SaMD study profile ladder"
  work_item_id: 532
  epic_id: 413
todos:
  - id: sop-doc
    content: Write docs/usage/18-samd-study-lifecycle.qmd; link from tutorial 16, index, regulatory README
    status: completed
    work_item_id: 533
  - id: samd-profiles
    content: Add samd_research, samd_holdout_enrichment, samd_pivotal profiles; register aliases; update DPL + config-parameter-matrix
    status: completed
    work_item_id: 534
  - id: study-scaffold
    content: Implement methyl-study-init scaffold + partition/claim validation helper
    status: completed
    work_item_id: 535
  - id: presets-cli-docs
    content: Add workflow_presets + Admin CLI start recipes for the three tiers
    status: completed
    work_item_id: 536
  - id: examples-evidence
    content: Add generic example manifests with non-empty partition stubs; document evidence-index package steps
    status: completed
    work_item_id: 537
  - id: promote-plan
    content: Promote to docs/plans/samd-study-profile-ladder.plan.md and update docs/plans/README.md
    status: completed
    work_item_id: 538
---

# SaMD-aligned study creation (profile ladder)

> **Delivery:** 3 profiles + study scaffold + SOP/docs + example manifests. Existing `mc_*` research axes remain for deep exploration.

## Profiles

| Profile | Role |
|---------|------|
| `samd_research` | Feasibility / expanded development; early-stop; exploratory BA |
| `samd_holdout_enrichment` | Requires `locked_test`; lock HPs from research |
| `samd_pivotal` | Requires `pivotal_validation`; hard gates; claim-ready stage |

## Artifacts

- SOP: [`docs/usage/18-samd-study-lifecycle.qmd`](../usage/18-samd-study-lifecycle.qmd)
- Profiles: `workflow_engine/domain/profiles/samd_*.profile.json`
- CLIs: `methyl-study-init`, `methyl-study-validate-manifest`
- Examples: [`docs/examples/samd/`](../examples/samd/)
- Presets: `scripts/workflow_presets.sh` (`samd_*`)
