# Documentation Audit — July 2026

> **Status:** COMPLETE (docs refresh + CI guardrails plan, 2026-07).

This audit records drift between MethylPipeline code and documentation after the **four-layer config**, **config-not-code**, **DMP/gene modeling modes**, and **DMP export simplification** changes.

## Quarto vs plain Markdown — validated decision

**Decision record:** [`docs/reference/documentation-toolchain.md`](../reference/documentation-toolchain.md) (Option A, adopted 2026-06-26).

| Pillar | Format | Rationale |
|--------|--------|-----------|
| **Theory** | Quarto (`.qmd`) | LaTeX math, `references.bib`, `@eq-` / `@sec-` cross-refs, publication PDF via `lualatex` |
| **Usage** | Quarto (`.qmd`) | Multi-part book assembly, PDF runbooks; reviewed 2026-07 — **stays Quarto** |
| **Implementation / Architecture / Reference** | Plain Markdown | GitHub-native; Mermaid + pre-rendered SVG |

**Validated 2026-07:** Theory cannot move to plain Markdown without losing equation numbering and bibliography. Usage has no math but benefits from book/PDF export; migration to Markdown would not reduce contributor burden proportionally.

**Gaps addressed in this refresh:**

- CI now runs `quarto render docs/theory docs/usage --to html` when Quarto is available.
- `scripts/check_doc_freshness.sh` blocks reintroduction of stale config/export tokens.
- Usage TikZ workflow figures migrated to Mermaid source + pre-rendered SVG.

## Root causes of drift

1. Code moved tool parameters out of study manifests (`step_config` rejected by `ProjectConfig`).
2. Operational defaults moved to site/profile `actionConfig` (no Python science fallbacks).
3. Modeling modes and generic profiles (`mc_dmp_*`, `mc_gene_*`) replaced disease-named presets.
4. FeatureCuts exports consolidated to `dmps-*-selected.csv`.
5. No CI gate for doc freshness or Quarto book smoke.

## Findings by severity

### Critical — teaches removed behavior as primary

| File | Issue | Fix |
|------|-------|-----|
| `docs/theory/chapters/11-project-configuration.qmd` | Entire chapter built around `step_config` dictionary | Rewritten: four-layer model, study manifest only |
| `docs/reference/configuration-reference.qmd` | Organized as `step_config.*` keys | Reframed as `actionConfig.*` resolver targets |
| `packages/methylvalidation/docs/USAGE.md` | "Project Config: step_config.validation"; package defaults | Profile + `resolvedConfig` + `mc_config.json` |
| `workflow_engine/docs/pipeline_architecture.md` | `step_config` as authoritative project content | Four-layer + enriched `context_json` |

### High — stale specifics

| File | Issue | Fix |
|------|-------|-----|
| `docs/usage/02-project-config-and-layout.qmd` | Precedence ends in "package defaults" | "no Python fallback for tunable science knobs" |
| `docs/reference/domain-program-language.md` | Same precedence; deprecated profile examples | Canonical profiles; updated precedence |
| `docs/reference/config-parameter-matrix.md` | Same precedence line | Aligned with layer model |
| `docs/usage/05-stage-stability.qmd` | Deprecated profiles; no modeling modes | `mc_*` profiles; modeling mode section |
| DMP export docs | Lead with `classifier` / `classifier-extended` | Primary: `dmps-*-selected.csv` |
| `docs/ANALYTE_PROFILES.md` | `step_config.validation.regulatory` | Top-level `regulatory` + profile/site |

### Medium — package and theory sweep

| Area | Issue | Fix |
|------|-------|-----|
| Theory ch.03, 04, 05, 12, 15 | Residual `step_config.*` references | Point to `actionConfig` |
| Package USAGE/IMPLEMENTATION | `step_config` paths | Resolver / profile keys |
| Check READMEs | Deprecated profile names | `mc_gene_fc`, `mc_dmp_*` |

## Remediation checklist

- [x] Audit report (this file)
- [x] Precedence alignment (usage ch.02, domain-program-language, config-parameter-matrix)
- [x] Theory ch.11 rewrite
- [x] configuration-reference reframe
- [x] ANALYTE_PROFILES rewrite
- [x] Modeling modes in usage ch.05 + theory ch.12
- [x] Canonical profile names in runbooks
- [x] DMP export narrative (`dmps-*-selected.csv`)
- [x] Workflow-engine docs
- [x] methylvalidation USAGE config section
- [x] Package doc sweep
- [x] documentation-toolchain validated note
- [x] Usage TikZ → Mermaid/SVG
- [x] `check_doc_freshness.sh` + CI
- [x] Quarto render CI step
- [x] Plan promoted to `docs/plans/`

## Related

- [DOCUMENTATION_AUDIT.md](../DOCUMENTATION_AUDIT.md) — coverage registry
- [layer-model.md](layer-model.md) — canonical precedence
- [AGENTS.md](../../AGENTS.md) — config-not-code principles
