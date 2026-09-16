---
name: Buffy Clara bakeoff readiness
overview: "Readiness check for the 15 healthy + 15 PCa buffy_coat SamplePrep bakeoff: SamplePrep download→/work→align→QNAP plumbing is in place, all 30 FASTQs are local, but the 15v15 study is pinned to Mojo pangenome—not Clara—and has no Clara context or QNAP archive destination yet."

> **Status: IMPLEMENTED (ops).** Clara 15v15 contexts + QNAP `goliath-archive` expand launcher under `/work/projects/prostate-cancer/configs/`; smoke running + full-after-smoke watcher armed. Mojo arms remain separate. Does not flip site/procedure defaults.

azure_devops:
  type: Feature
  title: "Buffy Clara bakeoff readiness"
  epic_id: 413
  work_item_id: null
todos:
  - id: add-clara-15v15-context
    content: Create context_sampleprep_buffy_15v15_linear_parabricks.json (/work paths, Clara engine, 30 samples; no embedded secrets)
    status: completed
  - id: optional-qnap-dest
    content: Wire sampleDestination via goliath-archive / resource profile if this wave must upload to QNAP
    status: completed
  - id: smoke-then-full
    content: Smoke 1–2 Clara linear SamplePrep samples, then full 15v15; keep Mojo arms as separate contexts
    status: completed
---

# Buffy 15v15 Clara bakeoff readiness

## Verdict (pre-implementation)

**Not ready to start as a Clara Parabricks 15v15 run** until Clara-pinned contexts exist. Platform SamplePrep plumbing is architecturally ready; cohort + local FASTQs exist.

## Delivered

| Artifact | Path |
|----------|------|
| Full 15v15 Clara context | `/work/projects/prostate-cancer/configs/context_sampleprep_buffy_15v15_linear_parabricks.json` |
| Smoke (2-sample) context | `/work/projects/prostate-cancer/configs/context_sampleprep_buffy_15v15_linear_parabricks_smoke.json` |
| Launch helper (expands QNAP dest) | `/work/projects/prostate-cancer/configs/run_Buffy_15v15_clara_linear_bakeoff.sh` |
| Full-after-smoke chain | `/work/projects/prostate-cancer/configs/run_Buffy_15v15_clara_linear_bakeoff_full_after_smoke.sh` |
| Operator notes | `/work/projects/prostate-cancer/ALIGNMENT_UPDATE.md` §B2 |

Procedure: `buffy_wgbs_linear_gene_fc` + `parabricks.engine=parabricks`. Outputs under `align.linear.parabricks/` so Mojo root H5s are preserved. Archive via `sampleStorageEndpoint: goliath-archive` (credential `goliath-archive-keys` in cfg-store).

## Launch status (ops)

- Smoke running: Clara `fq2bam_meth` on `HBCST-051425-74294` under `align.linear.parabricks/` (log: `Buffy_healthy_vs_PCa.clara_linear.smoke.log`).
- Full 15v15 auto-starts when smoke reports `COMPLETED` (watcher `…_full_after_smoke.sh`).
- Mojo contexts (`buffy_wgbs_pangenome_gene_fc`, etc.) unchanged.

```bash
/work/projects/prostate-cancer/configs/run_Buffy_15v15_clara_linear_bakeoff.sh smoke
# after smoke PASS:
/work/projects/prostate-cancer/configs/run_Buffy_15v15_clara_linear_bakeoff.sh full
```
