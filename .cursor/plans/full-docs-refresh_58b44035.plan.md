---
name: full-docs-refresh
overview: Perform a repo-wide documentation refresh for MethylPipeline, aligning root docs, Quarto books, and package docs with current pipeline behavior and CLI defaults. Deliver direct in-place updates with consistent cross-links, reduced duplication, and an explicit canonical-source structure.
todos:
  - id: root-docs-refresh
    content: Refresh/create monorepo landing docs (`README.md`, `docs/index.md`, top-level orientation docs) and align with current package/workflow reality.
    status: completed
  - id: quarto-sync
    content: Synchronize overlapping content between theory chapters and user-manual runbooks with consistent defaults, commands, and caveats.
    status: completed
  - id: package-docs-normalize
    content: Normalize package docs; add missing `docs/USAGE.md`, `docs/IMPLEMENTATION.md`, `docs/THEORY.md` for `methyldiseaseprogression`.
    status: completed
  - id: high-churn-doc-reconcile
    content: Reconcile high-churn docs (`methylvalidation`, `methyldetector`, `methylutils`) to avoid contradictions and stale command examples.
    status: completed
  - id: final-doc-validation
    content: Perform final consistency sweep (links, paths, CLI names, config keys, cross-reference integrity) and apply cleanup fixes.
    status: completed
isProject: false
---

# Full Monorepo Documentation Refresh Plan

## Goals
- Update all user-facing docs across the monorepo to match current workflow behavior and CLI defaults.
- Establish a clear canonical hierarchy to reduce drift between root docs, Quarto manuals, and package docs.
- Fill structural gaps (notably `methyldiseaseprogression` package docs) and normalize cross-references.

## Canonical Structure To Enforce
- Root entrypoint and orientation:
  - [`/home/ubuntu/MethylPipeline/docs/index.md`](/home/ubuntu/MethylPipeline/docs/index.md)
  - [`/home/ubuntu/MethylPipeline/docs/DEPLOYMENT.md`](/home/ubuntu/MethylPipeline/docs/DEPLOYMENT.md)
  - [`/home/ubuntu/MethylPipeline/README.md`](/home/ubuntu/MethylPipeline/README.md) (create/update to match `pyproject.toml` metadata)
- Theory/reference source:
  - [`/home/ubuntu/MethylPipeline/docs/theory/index.qmd`](/home/ubuntu/MethylPipeline/docs/theory/index.qmd)
  - [`/home/ubuntu/MethylPipeline/docs/theory/chapters/`](/home/ubuntu/MethylPipeline/docs/theory/chapters/)
- Operational runbook source:
  - [`/home/ubuntu/MethylPipeline/docs/user-manual/index.qmd`](/home/ubuntu/MethylPipeline/docs/user-manual/index.qmd)
  - [`/home/ubuntu/MethylPipeline/docs/user-manual/`](/home/ubuntu/MethylPipeline/docs/user-manual/)
- Package-local specifics:
  - `packages/*/README.md` + `packages/*/docs/{USAGE,IMPLEMENTATION,THEORY}.md`

## Execution Phases

### Phase 1: Monorepo entrypoint + top-level coherence
- Create/refresh [`/home/ubuntu/MethylPipeline/README.md`](/home/ubuntu/MethylPipeline/README.md) as the canonical landing page.
- Update [`/home/ubuntu/MethylPipeline/docs/index.md`](/home/ubuntu/MethylPipeline/docs/index.md) to reflect current workflow stages and package roles.
- Reconcile high-risk top-level files with current docs (overview, workflow diagram docs, configuration matrix) and add explicit “source of truth” notes where overlap exists.

### Phase 2: Quarto docs synchronization (theory + user manual)
- Align workflow narrative between:
  - [`/home/ubuntu/MethylPipeline/docs/theory/chapters/11-workflow-runbook.qmd`](/home/ubuntu/MethylPipeline/docs/theory/chapters/11-workflow-runbook.qmd)
  - [`/home/ubuntu/MethylPipeline/docs/theory/chapters/12-distributed-workflows.qmd`](/home/ubuntu/MethylPipeline/docs/theory/chapters/12-distributed-workflows.qmd)
  - [`/home/ubuntu/MethylPipeline/docs/theory/chapters/14-user-guide.qmd`](/home/ubuntu/MethylPipeline/docs/theory/chapters/14-user-guide.qmd)
  - [`/home/ubuntu/MethylPipeline/docs/user-manual/04-stability-runbook.qmd`](/home/ubuntu/MethylPipeline/docs/user-manual/04-stability-runbook.qmd)
  - [`/home/ubuntu/MethylPipeline/docs/user-manual/05-freeze-runbook.qmd`](/home/ubuntu/MethylPipeline/docs/user-manual/05-freeze-runbook.qmd)
  - [`/home/ubuntu/MethylPipeline/docs/user-manual/06-model-training-runbook.qmd`](/home/ubuntu/MethylPipeline/docs/user-manual/06-model-training-runbook.qmd)
- Ensure defaults and caveats are consistent (e.g., biological readiness behavior, Grok advisory defaults, enricher completeness semantics, stability/freeze expectations).

### Phase 3: Package docs normalization
- Bring all package docs to consistent structure and quality level.
- Add missing `docs/` set for:
  - [`/home/ubuntu/MethylPipeline/packages/methyldiseaseprogression/`](/home/ubuntu/MethylPipeline/packages/methyldiseaseprogression/)
    - `docs/USAGE.md`
    - `docs/IMPLEMENTATION.md`
    - `docs/THEORY.md`
- For high-churn packages, reconcile extended docs with package README/USAGE:
  - [`/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/`](/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/)
  - [`/home/ubuntu/MethylPipeline/packages/methyldetector/`](/home/ubuntu/MethylPipeline/packages/methyldetector/)
  - [`/home/ubuntu/MethylPipeline/packages/methylutils/docs/`](/home/ubuntu/MethylPipeline/packages/methylutils/docs/)

### Phase 4: Link integrity, duplication reduction, and migration notes
- Update stale references and remove/retitle ambiguous planning-style docs from user-facing flows.
- Add short migration/changelog notes in affected major docs summarizing changed commands/defaults.
- Ensure each overlapping document points to a single canonical owner section instead of duplicating long explanations.

### Phase 5: Validation pass
- Run a repo-wide documentation consistency sweep:
  - broken links/paths
  - command examples consistency
  - package name/CLI entrypoint consistency
  - configuration key naming consistency with code
- Final proofreading pass for terminology and workflow ordering.

## Key High-Risk Files To Prioritize Early
- [`/home/ubuntu/MethylPipeline/docs/index.md`](/home/ubuntu/MethylPipeline/docs/index.md)
- [`/home/ubuntu/MethylPipeline/docs/config_parameter_matrix.md`](/home/ubuntu/MethylPipeline/docs/config_parameter_matrix.md)
- [`/home/ubuntu/MethylPipeline/docs/MethylPipeline-overview.qmd`](/home/ubuntu/MethylPipeline/docs/MethylPipeline-overview.qmd)
- [`/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/STABILITY_FREEZE_READINESS.md`](/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/STABILITY_FREEZE_READINESS.md)
- [`/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/USAGE.md`](/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/USAGE.md)
- [`/home/ubuntu/MethylPipeline/packages/methylenricher/docs/USAGE.md`](/home/ubuntu/MethylPipeline/packages/methylenricher/docs/USAGE.md)

## Deliverables
- Updated root landing docs and deployment guidance.
- Synchronized theory/user-manual workflow docs.
- Standardized package docs across all packages, including newly added docs for `methyldiseaseprogression`.
- Cleaned cross-links and reduced duplication with explicit canonical-source pointers.
- Final docs consistency pass completed.