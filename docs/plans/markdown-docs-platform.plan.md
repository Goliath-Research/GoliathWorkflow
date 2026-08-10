---
name: Markdown Docs Platform
overview: Migrate MethylPipeline documentation from Quarto books to a Markdown-first MkDocs Material site with native Mermaid, MathJax equations, audience-based navigation, and portable static HTML (plus Playwright PDF that preserves diagrams and math).

> **Status: COMPLETE.** MkDocs Material site live; Theory/Usage converted to Markdown; customer + PDF configs; CI uses `mkdocs build --strict`.

azure_devops:
  type: Feature
  title: "Markdown-first documentation platform"
  work_item_id: null
  epic_id: 413
todos:
  - id: scaffold-mkdocs
    content: Add mkdocs.yml (Material + Mermaid + MathJax), docs deps, make docs/docs-serve/docs-pdf targets, build site/ from existing Markdown pillars
    status: completed
  - id: convert-theory-usage
    content: Convert Theory/Usage .qmd → .md (LaTeX kept; Quarto crossrefs → anchors/links); include usage ch.18–24 in nav; fix SaMD broken link
    status: completed
  - id: mermaid-unify
    content: Standardize on inline Mermaid for site HTML; demote diagrams/out PNG pipeline to optional (Marp/offline); update CI diagram checks
    status: completed
  - id: pdf-packaging
    content: Configure mkdocs-exporter aggregators (Theory/Usage/Regulatory/full); stop committing stale _book/ PDFs; document site/ hosting
    status: completed
  - id: audience-nav-customer
    content: Role-based mkdocs nav + optional mkdocs.customer.yml excluding plans/research/internals; claim-boundary banners on regulatory pages
    status: completed
  - id: content-refresh
    content: Alignment engines page + mojo cross-links; close audit leftovers; cleanup user-manual/strays; add docs/CONTRIBUTING.md; rewrite toolchain ADR
    status: completed
  - id: ci-guardrails
    content: Replace Quarto CI smoke with mkdocs build --strict; retarget freshness/link scripts for .md; release PDF job
    status: completed
---

# Markdown-first documentation platform

Implemented per the approved Cursor plan. Canonical toolchain ADR:
[`docs/reference/documentation-toolchain.md`](../reference/documentation-toolchain.md).

Contributor entry: [`docs/CONTRIBUTING.md`](../CONTRIBUTING.md).

Commands: `make docs`, `make docs-serve`, `make docs-customer`, `make docs-pdf`, `make check-docs`.
