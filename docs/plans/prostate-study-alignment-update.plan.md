---
name: Prostate study alignment update
overview: >
  Reconcile the prostate-cancer study (the 15 healthy vs 15 PCa plasma+buffy pair
  plus the other 10 recent manifests) with the new WGBS workflow: wire buffy to the
  pangenome_wgbs procedure and plasma to linear, fix the missing runtime-bundle
  procedures, and emit (without executing) the re-alignment and downstream re-run
  commands.

> **Status: Config + commands complete.** Procedures materialized, SamplePrep
> contexts wired, catalog actions synced, operator commands emitted in
> `/work/projects/prostate-cancer/ALIGNMENT_UPDATE.md`. Heavy SamplePrep /
> MC re-runs intentionally not executed.

azure_devops:
  type: Feature
  title: "Prostate study alignment update (buffy pangenome_wgbs)"
  work_item_id: null
  epic_id: 413
todos:
  - id: materialize-procedures
    content: Materialize the 5 procedure packs into runtime-bundle/domain/profiles/procedures/; confirm load_procedure resolves buffy_wgbs_pangenome_gene_fc and cfdna_wgbs_plasma
    status: completed
  - id: verify-site-catalog
    content: Validate site pangenome_wgbs assets and verify/seed sample.methylgrapher_wgbs_align/_extract catalog actions
    status: completed
  - id: wire-buffy-context
    content: Create context_sampleprep_buffy.json with pipelineProcedure=buffy_wgbs_pangenome_gene_fc
    status: completed
  - id: wire-plasma-context
    content: Create plasma sample-prep context with pipelineProcedure=cfdna_wgbs_plasma
    status: completed
  - id: emit-realign-commands
    content: Emit (do not run) sample_prep re-align commands for full buffy pool + plasma linear
    status: completed
  - id: acceptance-gate
    content: Document linear-vs-wgbs acceptance gate as go/no-go before downstream refresh
    status: completed
  - id: emit-downstream-commands
    content: Enumerate per-manifest downstream re-run scripts for all 12 manifests
    status: completed
  - id: docs
    content: Promote plan to docs/plans and add study-level alignment note
    status: completed
---

# Prostate study alignment update

## Situation

- **One study** under `/work/projects`: `prostate-cancer` (12 `project_*.json` manifests, ~last month). The 15v15 target is the paired pair [`project_Plasma_healthy_vs_PCa.json`](/work/projects/prostate-cancer/configs/project_Plasma_healthy_vs_PCa.json) (cfdna, 15/15) and [`project_Buffy_healthy_vs_PCa.json`](/work/projects/prostate-cancer/configs/project_Buffy_healthy_vs_PCa.json) (buffy_coat, 15/15).
- **Upstream-only change** (SamplePrep/alignment): actions `sample.methylgrapher_wgbs_align` / `_extract`, procedure packs, accepted default **buffy = `pangenome_wgbs`** via [`buffy_wgbs_pangenome_gene_fc.procedure.json`](../../workflow_engine/domain/profiles/procedures/buffy_wgbs_pangenome_gene_fc.procedure.json); plasma stays **linear** via `cfdna_wgbs_plasma`.
- **Downstream science is decoupled**: `context_*.json` files drive detection/mapper/validation and consume per-sample H5s from `/work/samples/{id}/`.
- Manifests are analyte-only (no aligner knobs) — correct per config-not-code. **No science-manifest edits.**

## What was implemented

1. **Runtime-bundle procedures** copied to `/work/epimethyl/current/runtime-bundle/domain/profiles/procedures/` (all five packs). `resolve_procedure_path` / `apply_pipeline_procedure` resolve `buffy_wgbs_pangenome_gene_fc` → `pangenome_wgbs` and `cfdna_wgbs_plasma` → `linear`.
2. **Site assets validated** (`pangenome_wgbs_genome` C2T/G2A indexes, `wl.gfa`, `cpg.tsv`, `node.replacement.json`, linear FASTA).
3. **Catalog sync**: `methyl-cfg sync-actions --from-json` wrote `sample.methylgrapher_wgbs_align` / `_extract` into `/work/epimethyl/cfg-store/action_definition/`.
4. **SamplePrep contexts** (study, not git):
   - `context_sampleprep_buffy.json` → 15v15 buffy
   - `context_sampleprep_buffy_pool.json` + `project_Buffy_sampleprep_pool.json` → full 238-sample buffy union
   - `context_sampleprep_plasma.json` → 15v15 plasma
5. **Operator runbook** with emit-only re-align, acceptance-gate, and downstream refresh commands: [`/work/projects/prostate-cancer/ALIGNMENT_UPDATE.md`](/work/projects/prostate-cancer/ALIGNMENT_UPDATE.md).

## Flow

```mermaid
flowchart TD
  procs["procedures/*.procedure.json (repo)"] -->|materialize| bundle["runtime-bundle/domain/profiles/procedures/"]
  site["methyl_site.json pangenome_wgbs + wl.gfa"] --> prep
  bundle --> prep["sample_prep.program.json"]
  ctxB["context buffy: pipelineProcedure=buffy_wgbs_pangenome_gene_fc"] --> prep
  ctxP["context plasma: pipelineProcedure=cfdna_wgbs_plasma"] --> prep
  prep -->|regenerate H5| pool["/work/samples/{id}/ (shared buffy pool)"]
  pool --> gate{"acceptance gate\nlinear vs wgbs"}
  gate -->|pass| downstream["run_*.sh downstream refresh (all 12 manifests)"]
```

## Operator next steps (not executed by this plan)

1. Run full buffy pool SamplePrep (`context_sampleprep_buffy_pool.json`).
2. Gate with `scripts/compare_sample_prep_linear_vs_wgbs.sh` + `thresholds.acceptance.json`.
3. Re-run existing `configs/run_*.sh` scripts after PASS.
