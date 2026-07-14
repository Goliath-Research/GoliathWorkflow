# MethylPipeline Documentation Audit

**Date:** 2026-07-09 (comprehensive audit refresh)  
**Prior IA revision:** 2026-06-26  
**Scope:** Theory, Usage, Implementation, Architecture, Reference, deployment, DomainProgram language.

This document is the canonical register of documentation coverage, canonical sources, stale items, and maintenance rules.

## Coverage matrix

| Area | Canonical source | Status | Notes |
|------|------------------|--------|-------|
| **Theory** | [`docs/theory/`](theory/) | Slimmed | Parts I–II only; no CLI runbook chapters |
| **Usage** | [`docs/usage/`](usage/index.qmd) | Complete | Renamed from `user-manual/`; DomainProgram-first front matter |
| **Implementation** | [`docs/implementation/`](implementation/index.md), [`workflow_engine/docs/IMPLEMENTATION.md`](../workflow_engine/docs/IMPLEMENTATION.md) | Consolidated | Package index at `implementation/packages/` |
| **Architecture** | [`docs/architecture/`](architecture/index.md) | Consolidated | Absorbs architecture_review + pipeline overview |
| **Reference** | [`docs/reference/`](reference/documentation-toolchain.md) | New pillar | Config matrix, DomainProgram language, toolchain decision |
| **Workflow JSON** | [`reference/domain-program-language.md`](reference/domain-program-language.md) | Moved | Schemas in `schemas/domain/` |
| **SamplePrep + QC** | Usage ch.03, [`workflow_engine/sql_mssql/SamplePrepFlow.md`](../workflow_engine/sql_mssql/SamplePrepFlow.md) | Documented | |
| **Deployment** | Usage ch.14, [`deployment/production_runbook.md`](deployment/production_runbook.md) | Dual-backend | Worker-only gateway; env templates in `deploy/env/` |
| **Admin CLI** | [`reference/admin-cli-methyl-study-start.md`](reference/admin-cli-methyl-study-start.md) | Documented | Direct DB; not on gateway |
| **Workflow engine** | [`implementation/workflow-engine.md`](implementation/workflow-engine.md) | Expanded | Dual-dialect state machine |
| **Traceability / ops** | [`reference/traceability-provenance.md`](reference/traceability-provenance.md), [`architecture/workflow-idempotency-retry-lease.md`](architecture/workflow-idempotency-retry-lease.md) | New | Honest lease/retry gaps |
| **July 2026 audit** | [`architecture/documentation-audit-2026-07-09.md`](architecture/documentation-audit-2026-07-09.md) | Active | Supersedes partial 2026-07 config audit items |
| **Schemas / contracts** | [`reference/schema-index.md`](reference/schema-index.md), [`contracts/openapi.yaml`](../contracts/openapi.yaml) | Machine-readable | |
| **Regulatory / product controls** | [`regulatory/`](regulatory/README.md) | New synthesis pillar | Product controls, validation evidence index, change management, deployment supervision, traceability |
| **Platform overview** | [`overview/methylpipeline-platform-overview.md`](overview/methylpipeline-platform-overview.md) | Canonical quick synthesis | Few-dozen-page Markdown + [companion canvas](canvas/methylpipeline-platform-overview.canvas.tsx); not a fourth Quarto book |
| **Storage credentials (DB SoT)** | [`architecture/config-registry.md`](architecture/config-registry.md), [`deployment/portal_resource_profile.md`](deployment/portal_resource_profile.md), plan [`plans/storage-db-sot.plan.md`](plans/storage-db-sot.plan.md) | Active | Portal `sp_*` authoring; expand + `contentHash` + node-local cache; Key Vault optional |
| **Diagrams** | [`docs/diagrams/src/*.mmd`](diagrams/src/), [`docs/diagrams/out/*.svg`](diagrams/out/), [`docs/diagrams/out/*.png`](diagrams/out/) | Pre-render pipeline | `scripts/render_diagrams.sh` (`htmlLabels: false`, PNG for Quarto PDF) |

## Canonical doc map (“read this for X”)

| Question | Start here |
|----------|------------|
| What is the end-to-end platform + SaMD fitness story? | [`overview/methylpipeline-platform-overview.md`](overview/methylpipeline-platform-overview.md) |
| How do I set up the dev environment? | [`DEPLOYMENT.md`](DEPLOYMENT.md), Usage ch.01 |
| Where do project configs vs programs live? | Usage ch.02, [work-config-paths](../.cursor/rules/work-config-paths.mdc), [layer model](architecture/layer-model.md) |
| How does SamplePrep QC work? | Usage ch.03, theory ch.09 |
| How do I run a study end-to-end? | `methyl-workflow-run` + Usage Part II |
| How do I author a workflow in JSON? | [domain-program-language.md](reference/domain-program-language.md) |
| How do I deploy DB + gateway + workers? | Usage ch.14, [production_runbook.md](deployment/production_runbook.md), [deploy/env/](../deploy/env/README.md) |
| How do I compile/start instances without gateway admin? | [admin-cli-methyl-study-start.md](reference/admin-cli-methyl-study-start.md) |
| What is the REST/worker protocol? | [WORKER_PROTOCOL.md](../workers/WORKER_PROTOCOL.md), [contracts/openapi.yaml](../contracts/openapi.yaml) |
| What is stale vs current? | This file + [documentation-audit-2026-07-09.md](architecture/documentation-audit-2026-07-09.md) |

## Repository vs `/work` ownership

| **Repository (versioned)** | **`/work/<study>/` (runtime)** |
|----------------------------|--------------------------------|
| `workflow_engine/domain/profiles/*.profile.json` | `configs/project_*.json` |
| `workflow_engine/domain/checks/*/configs/*.program.json` | Sample CSVs, outputs |
| `workflow_engine/domain/fixtures/*.program.json` | `monte_carlo_runs/`, `alignment_qc/` |
| `schemas/`, docs, theory | Per-study artifacts |

## Maintenance rules (IA revision)

1. **One canonical home per fact** — if duplicated, lower-pillar doc links upward.
2. **Theory changes** require equation label + bib entry when adding principled methods.
3. **Usage changes** require Usage chapter update when CLI defaults change.
4. **Implementation changes** require `workflow_engine/docs/IMPLEMENTATION.md` or package IMPLEMENTATION update when action catalog or compiler changes.
5. **No new top-level standalone Quarto docs** — use the three pillars + architecture/reference.
6. **Presentations** remain derivative exports from pillars.
7. **Diagrams** — edit `docs/diagrams/src/*.mmd`; run `render_diagrams.sh`; never edit TikZ workflow figures by hand.
8. **PDF builds** must not rely on live Mermaid JS — only pre-rendered assets from `docs/diagrams/out/`.
9. **Package THEORY.md** — max ~40 lines; link to theory book chapter only.
10. **Committed `_book/`** — regenerate after substantive `.qmd` edits or publish from CI.

## CI hooks

- `bash scripts/check_doc_links.sh` — legacy path guard + required files
- `python scripts/check_windows_paths.py` — reject tracked paths invalid on Windows
- `bash scripts/render_diagrams.sh --check` — SVG freshness vs `.mmd` sources
- `bash scripts/check_doc_freshness.sh` — stale config/export token guard
- `quarto render docs/theory docs/usage --to html` — book smoke (when Quarto available)

## Related documents

- Hub: [`index.md`](index.md)
- Toolchain decision: [`reference/documentation-toolchain.md`](reference/documentation-toolchain.md)
- Canvas hub: [`methylpipeline-docs.canvas.tsx`](canvas/methylpipeline-docs.canvas.tsx) (git: `docs/canvas/`; sync with `scripts/sync_cursor_canvases.sh`)
- Plans: [`plans/README.md`](plans/README.md)
