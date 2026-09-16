---
name: DS20M Dual-Graph Finish
overview: Finish a scientifically complete dual-graph pangenome_wgbs extraction on the existing DS20M GAF (not the C2T-BAM shortcut), restore the missing MethylCall GFA asset from QNAP, project graph CpGs to GRCh38, and re-compare against linear DS20M before any full-depth / multi-worker work.

> **Status: Complete (conditional).** MethylCall+projection done; go/no-go = NO-GO for full-depth until cov/meth concordance fixed. Report: `/work/samples/_comparisons/20260728T163518Z/dual_graph_gono.md`.

azure_devops:
  type: Feature
  title: "DS20M dual-graph MethylCall finish"
  work_item_id: null
  epic_id: 413
todos:
  - id: restore-wl-gfa
    content: Restore hprc-d9-bs.wl.gfa from QNAP seed; verify segment IDs
    status: completed
  - id: clean-quarantine
    content: Clean empty mcall*.tmp; quarantine BAM-extract H5s
    status: completed
  - id: run-methylcall
    content: Stage GAF locally; MethylCall -t<=16 + MergeCpG; preflight in runner
    status: completed
  - id: project-linear
    content: Implement graph.cpg.tsv → GRCh38 chrom/pos projector + H5 emission
    status: completed
  - id: compare-gono
    content: Re-run DS20M compare report; record go/no-go
    status: completed
---

# Finish dual-graph MethylCall on DS20M

See implementation notes in chat / runner changes. Key correction vs initial draft: **do not rebuild `wl.gfa` from stock d9.gbz** — use the PrepareGenome artifact seeded on QNAP (`s3://goliath/genomes/pangenome/GRCh38/d9-bs/1.70/hprc-d9-bs.wl.gfa`).
