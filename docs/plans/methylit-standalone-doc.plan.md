---
name: MethylIT Standalone Doc
overview: Create a standalone research note on MethylIT (R 0.3.2.8 + Python methylit 0.4.2) by extracting and rewriting MethylIT content from the existing comparison, with every MethylPipeline reference removed.

> **Status: completed** — `docs/research/methylit.md` + README index row.
azure_devops:
  type: Feature
  title: "MethylIT Standalone Doc"
  work_item_id: 668
  epic_id: 413
todos:
  - id: draft-methylit-md
    content: Write docs/research/methylit.md from comparison, MethylIT-only rewrite
    status: completed
    work_item_id: 669
  - id: update-research-readme
    content: Add methylit.md row to docs/research/README.md
    status: completed
    work_item_id: 670
  - id: grep-bleed
    content: Grep new doc for MethylPipeline / related product terms and fix any bleed
    status: completed
    work_item_id: 671
---

# Standalone MethylIT research note

## Default scope

**Full research note** (method + R/Python source cross-checks + independent critiques). Descriptive-only or Python-only can be trimmed later if you prefer a shorter note.

## Deliverable

New file: [`docs/research/methylit.md`](../research/methylit.md)

Update index row in [`docs/research/README.md`](../research/README.md).

Leave [`docs/research/methylpipeline_vs_methylit_comparison.md`](../research/methylpipeline_vs_methylit_comparison.md) unchanged (still the head-to-head).

## Content outline (no MethylPipeline mentions)

1. **Header / evidence boundary** — Informal research note; sources are MethylIT R `0.3.2.8` and Python `methylit` `0.4.2` (external checkouts `MethylIT2/`, `EDFi/`); version naming (`0.4.0` config vs `0.4.2` code).

2. **Executive summary** — Information thermodynamics + signal detection; DMP = per-sample divergence vs pooled reference; pipeline stages; R default Youden vs Python ML-only cutpoint.

3. **Pipeline** — Mermaid flowchart + stage map (`cap_coverage` → `divergence` → `gof` → `pDMP` → `cutpoint` → `dmp` / prediction; `orca` / `06→09` trail).

4. **Core theory** — Per-sample unit of signal; parametric noise model; Bayesian beta-binomial levels; TV gate; where ML enters (R vs Python).

5. **Estimator formulas** (from R + Python cross-checks) — Coverage-weighted Hellinger; J-divergence; beta-binomial posteriors; tail-α + TV; reference pooling (`poolFromGRlist` / `centroid.stat`).

6. **R source cross-check** — Confirmed pipeline; Youden default; ECDF as built-in `dist.name`; gene layer (`getDMGs` / count GLM).

7. **Python 0.4.2 cross-check** — Confirmed formulas; Youden `NotImplementedError`; `target_sum=500` (not ~10x); gene testing out of MVP; profiles/tests/DHF posture.

8. **Reference selection** — Manual `is_reference`; pooled centroid; why it governs all downstream numbers; practical recipe; reference-swap sensitivity as open measurement.

9. **Gene / interpretation layer** — Python: gene-window masking only; R: count-based DMG GLM (not weighted propagation).

10. **Sidecar experiments** — `exp_wand.py` holdouts; `g2dmp_m34.py` gene subset + receipts.

11. **Deeper analysis (MethylIT-internal)** — Rewrite sections A–C so they critique MethylIT on its own terms (ECDF quantile vs GGamma at α=0.05; Youden vs RF under collinear features) **without** saying another product already does X.

12. **Independent critiques** — First-party evidence base; coverage cap vs beta-binomial field practice; replicates-over-depth (Ziller); small train fraction / RF cost; nested selection leakage. Empirical agenda kept MethylIT-only (ECDF vs parametric pDMP Jaccard; Youden vs RF; reference-swap; beta-binomial baseline).

13. **References** — First-party Sanchez/Mackenzie + independent external lit; key source paths reviewed.

## Rewrite rules

- Strip every MethylPipeline name, path, workflow, and “vs” framing.
- Where the comparison used MethylPipeline as a foil (“converges with…”, “MethylPipeline’s hold-out…”), restate as a MethylIT-internal prediction or open experiment.
- Do not invent new claims beyond what the comparison already verified against R/Python source.
- Keep math, mermaid, and citations intact where they are MethylIT-specific.

## Verification

- Grep the new file for `MethylPipeline`, `methyl-`, `DomainProgram`, `Workflow` to ensure zero product bleed.
- Confirm README table lists the new note.