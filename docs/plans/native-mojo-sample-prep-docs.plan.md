---
name: Native-Mojo Sample Prep docs
overview: Resolve the documentation schism by making native-Mojo (one portable DeviceContext implementation on NVIDIA CUDA + AMD HIP) the canonical pangenome_wgbs Sample Preparation align path; Parabricks is an explicit config choice for linear/stock pangenome modes, never an automatic Mojo failure path; CPU align only when the GPU vendor is unknown. Also document mode-aware alignment QC — shared guardrails plus tool-specific metrics/parameters per aligner family.

> **Status: COMPLETED.** Documentation update across theory, implementation, usage, overview, architecture, presentations, reference, deployment, workflow_engine, and worker docs. Mode-aware QC contract cross-links [`pangenome-wgbs-methyl-qc.plan.md`](pangenome-wgbs-methyl-qc.plan.md).

azure_devops:
  type: Feature
  title: "Native-Mojo Sample Preparation Flow documentation"
  work_item_id: null
  epic_id: 413
todos:
  - id: canonical
    content: Rewrite canonical WGBS + metrics-import/guardrails sections in sample-preparation-flow.md and architecture docs
    status: completed
  - id: mode-aware-qc-docs
    content: Document mode-aware alignment QC in theory/09, sample-preparation-flow, USAGE.md
    status: completed
  - id: usage-theory-overview
    content: Update usage, theory 09a, overview, index/nav
    status: completed
  - id: presentations-reference-deploy
    content: Update presentations, reference, deployment docs
    status: completed
  - id: workflow-worker-docs
    content: Rewrite CPU-only claims in workflow_engine and worker/docker docs
    status: completed
  - id: plans
    content: Update docs/plans statuses and CPU-only assumptions
    status: completed
  - id: verify
    content: Grep for residual stale phrases and re-read for consistency
    status: completed
---

# Native-Mojo Sample Preparation Flow: documentation update

See the full plan body in the Cursor plan that promoted this file. Canonical model:

- **`pangenome_wgbs`** → native-Mojo on NVIDIA CUDA or AMD HIP (one DeviceContext implementation).
- **`linear` / `pangenome`** → NVIDIA Clara Parabricks via **explicit** config (never an automatic Mojo failure path).
- **CPU align** → only when the GPU vendor is unknown (e.g. Google Cloud GPUs that are neither NVIDIA nor AMD).
- **Mode-aware QC** → shared guardrails + Parabricks-family vs methylGrapher-family tool-specific checks.
