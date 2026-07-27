---
name: Linear vs WGBS SamplePrep Compare
overview: Run SamplePrep through extraction QC for plasma `DPLST-051425-111148` and buffy `DBCST-051425-111148` under linear vs `pangenome_wgbs`, keeping mode-isolated local trees and producing a CpG-quality plus alignment-time comparison report—without archiving to QNAP until after review.

> **Status: IMPLEMENTED.** Runner `scripts/compare_sample_prep_linear_vs_wgbs.sh` + `workflow_engine/ops/sample_prep_mode_compare.py`; helpers in `packages/methylutils/methyl_utils/testing/sample_prep_mode_compare.py`; operator note in `workflow_engine/docs/sample_prep_test_bed.md`. Dry-run payloads written under `/work/samples/_comparisons/`; live 4-arm execute blocked pending refreshed QNAP/lab FASTQ credentials and a GPU worker with Parabricks + methylGrapher capabilities.

azure_devops:
  type: Feature
  title: "Linear vs pangenome_wgbs SamplePrep comparison"
  work_item_id: null
  epic_id: 413
todos:
  - id: layout-runner
    content: Add experiment-only mode-subdir SamplePrep compare runner (FASTQs at sample root like QNAP; linear + pangenome_wgbs trees; no archive)
    status: completed
  - id: cpg-time-report
    content: Implement CpG quality + alignment-time comparison JSON/Markdown report with operator-set thresholds
    status: completed
  - id: execute-two-samples
    content: Run DPLST-051425-111148 and DBCST-051425-111148 through both arms; write report under /work/samples/_comparisons
    status: completed
  - id: docs-no-archive
    content: Document experiment layout and post-compare single-arm archive policy in sample_prep_test_bed
    status: completed
---

# Linear vs pangenome_wgbs SamplePrep comparison

## Samples and modes
- **Plasma (cfDNA):** `DPLST-051425-111148` (corrects the typo `…1111498`)
- **Buffy coat:** `DBCST-051425-111148`
- **Arms:** `linear` (Parabricks `fq2bam_meth` + MethylExtract) vs `pangenome_wgbs` (methylGrapher align + extract)
- **Depth:** download → align → alignment QC → extract → extraction QC for every arm
- **Archive:** disabled for this experiment (`sampleStorage` omitted / no archive node path used) so QNAP is not overwritten; archive the winning arm later after review

## Local layout (lab/QNAP FASTQ root + experiment-only mode trees)
Laboratories and QNAP store FASTQs **directly under `<sampleId>/`** (no extra `/fastq` folder). Keep that contract.

`linear/` and `pangenome_wgbs/` exist **only for this dual-align experiment** so both BAMs/QC/H5s can coexist for comparison. They are not the long-term production layout: once one mode wins consistently, SamplePrep returns to a single flat `/work/samples/<sampleId>/` tree.

```text
/work/samples/<sampleId>/
  <sampleId>_1.fastq.gz          # shared; same layout as QNAP / lab delivery
  <sampleId>_2.fastq.gz
  linear/                        # experiment-only: BAM, QC, H5, manifests
  pangenome_wgbs/                # experiment-only: BAM/GAF, QC, H5, manifests
```

Four SamplePrep instances (2 samples × 2 modes). Each sets `sampleDir` to the mode subdirectory and `alignmentMode` accordingly.

**FASTQ handling:** download once from QNAP into `/work/samples/<sampleId>/` (matching object keys), or `--reuse-local-fastq` when those files already exist. Before each mode run, hardlink/symlink the pair into that mode’s `sampleDir` so aligners see them without a second cloud pull and without inventing a `/fastq` staging dir. `deleteFastqs: false` so the shared root pair is retained across arms.

## Orchestration
- Entry: `scripts/compare_sample_prep_linear_vs_wgbs.sh`
- Core: `workflow_engine/ops/sample_prep_mode_compare.py`
- Helpers: `packages/methylutils/methyl_utils/testing/sample_prep_mode_compare.py`
- Inputs: sample list + QNAP `fastqStorage` (endpoint/bucket/prefix under the sample id, not a `/fastq` child), projectPath, optional `--reuse-local-fastq`
- Per arm: ensure mode `sampleDir`, link root FASTQs into it, then `admin.study_start sample-prep-start` with overlays (`alignmentMode`, `actionConfig`, `deleteFastqs: false`)
- Poll to COMPLETED; collect `duration_ms` / timestamps from task outputs and prep/action logs for **alignment wall time**
- Do not set `sampleStorage` for these starts
- Docs: mode subdirs are temporary experiment scaffolding, not a new lab/QNAP convention (`workflow_engine/docs/sample_prep_test_bed.md`)

## Comparison metrics (CpG quality + time)
Report JSON + Markdown under `/work/samples/_comparisons/<stamp>/` (and symlink latest).

Hypothesis framing: **pangenome_wgbs improves usable read support at CpG positions** (coverage/site yield), with alignment runtime as a cost metric—not a methylation-biology claim from stock Giraffe.

Operator-set thresholds extend `SamplePrepCanaryThresholds` (`alignment_time_ratio_max`, `cpg_coverage_min_fraction_of_linear`, `cpg_depth_thresholds`).
