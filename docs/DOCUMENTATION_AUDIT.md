# MethylPipeline Documentation Audit

**Date:** 2026-08-25 (SamplePrep docs audit — arm layout, V2.1, CPU extract, native manifest)  
**Prior:** 2026-08-10 Markdown-first MkDocs migration; 2026-07-09 comprehensive audit; 2026-06-26 IA revision  
**Scope:** Theory, Usage, Implementation, Architecture, Reference, deployment, DomainProgram language, regulatory.

This document is the canonical register of documentation coverage, canonical sources, stale items, and maintenance rules.

## Coverage matrix

| Area | Canonical source | Status | Notes |
|------|------------------|--------|-------|
| **Site toolchain** | [`mkdocs.yml`](../mkdocs.yml), [`reference/documentation-toolchain.md`](reference/documentation-toolchain.md) | Adopted | Markdown + Mermaid + MathJax; portable `site/` |
| **Theory** | [`docs/theory/`](theory/index.md) | Markdown | MathJax equations; Parts I–II |
| **Usage** | [`docs/usage/`](usage/index.md) | Markdown | Includes ch.18–24 (SaMD, packs) + [alignment engines](usage/alignment-engines.md) |
| **Implementation** | [`docs/implementation/`](implementation/index.md) | Consolidated | Package index at `implementation/packages/` |
| **Architecture** | [`docs/architecture/`](architecture/index.md) | Consolidated | Inline Mermaid |
| **Reference** | [`docs/reference/`](reference/documentation-toolchain.md) | Active | Config matrix, DomainProgram language, toolchain ADR |
| **SamplePrep + QC** | Usage [ch.03](usage/03-sample-prep-and-qc.md), [alignment engines](usage/alignment-engines.md), [`sample-preparation-flow.md`](implementation/sample-preparation-flow.md) | Documented (2026-08-25) | `sampleRoot` vs `sampleDir` arm leaf; QC export V2.1; CPU MethylExtractor vs GPU alignment; native extract manifest preserve-or-synthesize |
| **Deployment** | [`deployment/operator-journey.md`](deployment/operator-journey.md) | Dual-backend | Worker-only gateway |
| **Regulatory** | [`regulatory/`](regulatory/README.md) | Synthesis | Claim-boundary admonitions; customer nav via `mkdocs.customer.yml` |
| **Platform overview** | [`overview/methylpipeline-platform-overview.md`](overview/methylpipeline-platform-overview.md) | Canonical | Quick synthesis + canvas |
| **Diagrams** | Inline Mermaid; optional [`diagrams/src/*.mmd`](diagrams/src/) | Dynamic first | `render_diagrams.sh` optional for Marp |
| **July 2026 ops audit** | [`architecture/documentation-audit-2026-07-09.md`](architecture/documentation-audit-2026-07-09.md) | Historical | Many P0 items gated by freshness scripts; treat open header as backlog pointer |

## Canonical doc map (“read this for X”)

| Question | Start here |
|----------|------------|
| How do I preview the docs site? | [`CONTRIBUTING.md`](CONTRIBUTING.md), `make docs-serve` |
| What is the end-to-end platform + SaMD fitness story? | [`overview/methylpipeline-platform-overview.md`](overview/methylpipeline-platform-overview.md) |
| How do I set up the dev environment? | [`DEPLOYMENT.md`](DEPLOYMENT.md), Usage ch.01 |
| Where do project configs vs programs live? | Usage ch.02, [layer model](architecture/layer-model.md) |
| Which aligner / engine should I use? | [alignment-engines.md](usage/alignment-engines.md) |
| How does SamplePrep QC work? | Usage [ch.03](usage/03-sample-prep-and-qc.md), [`sample-preparation-flow.md`](implementation/sample-preparation-flow.md) |
| How do I run a study end-to-end? | `methyl-workflow-run` + Usage staged chapters |
| How do I author a workflow in JSON? | [domain-program-language.md](reference/domain-program-language.md) |
| How do I deploy DB + gateway + workers? | [operator-journey.md](deployment/operator-journey.md), [production_runbook.md](deployment/production_runbook.md) |
| What is stale vs current? | This file + freshness CI |

## Maintenance rules

1. **One canonical home per fact** — if duplicated, lower-pillar doc links upward.
2. **Theory changes** — keep MathJax delimiters; add equation anchors for cross-links.
3. **Usage changes** — update Usage chapters when CLI / artifact contracts change; keep `mkdocs.yml` nav in sync.
4. **Implementation changes** — update `implementation/` or package IMPLEMENTATION when action catalog or compiler changes.
5. **No `.qmd` files** — Markdown + MkDocs only. `scripts/check_doc_freshness.sh` fails if any remain.
6. **Presentations** remain derivative exports from pillars.
7. **Diagrams** — prefer inline Mermaid; shared sources under `docs/diagrams/src/` for Marp.
8. **PDF** — Playwright print of rendered HTML (`make docs-pdf`), not TeX/Mermaid pre-render for the site.
9. **Package THEORY.md** — max ~40 lines; link to theory chapters.
10. **Do not commit `site/`** — build in CI or locally; host the artifact anywhere.

## CI hooks

- `mkdocs build --strict`
- `bash scripts/check_doc_links.sh`
- `bash scripts/check_doc_freshness.sh`
- `python scripts/check_windows_paths.py`
- Optional: `bash scripts/render_diagrams.sh --check` (Marp assets)
- Release: `mkdocs build -f mkdocs.customer.yml` and `bash scripts/build_docs_pdf.sh`

## Related documents

- Hub: [`index.md`](index.md)
- Contributing: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Toolchain decision: [`reference/documentation-toolchain.md`](reference/documentation-toolchain.md)
- Plans: [`plans/README.md`](plans/README.md)
