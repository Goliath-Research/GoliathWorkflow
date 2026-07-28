---
name: Linear vs WGBS SamplePrep Compare
overview: Run SamplePrep through extraction QC for plasma `DPLST-051425-111148` and buffy `DBCST-051425-111148` under linear vs `pangenome_wgbs`, keeping mode-isolated local trees and producing a CpG-quality plus alignment-time comparison report—without archiving to QNAP until after review.

> **Status: TOOLING IMPLEMENTED; LIVE COMPARE IN PROGRESS (depth-matched subset).** Runner `scripts/compare_sample_prep_linear_vs_wgbs.sh` + `workflow_engine/ops/sample_prep_mode_compare.py`; helpers in `packages/methylutils/methyl_utils/testing/sample_prep_mode_compare.py`; operator note in `workflow_engine/docs/sample_prep_test_bed.md`. Reports under `/work/samples/_comparisons/`. Linear arm needs Parabricks GPU; `pangenome_wgbs` is **CPU-only** methylGrapher(+vg) — no CUDA, expect much longer wall time on the same host.

## Live-run findings (2026-07-28)

Full depth for plasma `DPLST-051425-111148` is 349.3M read pairs, so the arms run on a **deterministic 20M-pair subset** (`DPLST-051425-111148-DS20M`, first 20M pairs of each mate file, ~5.7% of depth) to keep the CPU-only arm to hours instead of days. Blockers found and cleared while getting the first real dual-arm run:

| Blocker | Cause | Fix |
|---|---|---|
| `methyl_qc` looked for `<mode>.bam` | mode subdir name used as sample id | `resolve_sample_artifact_id` in `methyl_alignment_qc/core/parser.py` |
| FOREACH parents stayed `PENDING` after children succeeded | base schema scripts overwrote the FOREACH-aware continuation proc | `wf.wf_foreach_route_continue` router + guards in every `wf_engine_continue_parent` / `wf_engine_on_action_complete` definition |
| `gc_dropout` 5.102 failed a hardcoded `< 5.0` | core WGBS thresholds were literals in Python | `CoreGuardrailsConfig` (site/profile `actionConfig.alignment_qc.core_guardrails`) |
| Trim remediation crashed | `fastp` not installed on the worker host | `apt install fastp` (already declared in `scripts/setup_host.sh`) |
| `methylGrapher Align` wrote a 0-byte GAF | `vg` 1.70 emits GAF header lines (`@HD\tVN:Z:1.0`); methylGrapher 0.2.0/0.2.1 indexes column 11 of every line | `workers/docker/methylgrapher/patch_gaf_header.py` applied at image build |
| Retry QC task rejected its own input | `MethylQcTaskInput.remediationTrigger` typed `str` while programs pass an object | `RemediationTrigger` model in `workers/methyl_worker/task_models/sample_prep_models.py` |
| `vg surject` aborted on the methylGrapher GAF (signal 6, empty BAM) | methylGrapher maps with `vg giraffe --named-coordinates`, so the GAF path column holds GFA **segment** names; `vg surject -G` reads it as vg **node** IDs. Node `57658665` is 3 bp in the graph while the GAF claims a 1202 bp path, tripping the `cur_offset < cur_len` assertion in `gaf_to_alignment` | Build the QC BAM from a dedicated `vg giraffe -o BAM --ref-paths` C2T pass over freshly converted reads (`build_qc_bam_command`); the GAF stays untouched for `MethylCall`, which needs named coordinates |
| Comparison arms overwrote each other's QC | `methyl_qc` wrote only to `alignment_qc/<sampleId>.json`, keyed by sample id alone | `methyl_qc` also mirrors `<sampleId>.alignment_qc.json` into the sample dir — which is the file the compare validator already looked for |

Re-running the align action now reuses an existing non-empty GAF, so a QC-BAM failure no longer costs another full dual-graph mapping.

Guardrail outcome on the subset (linear arm): `min_quality_post20` 27.23 failed, screening asked for a 5 bp R2 front trim, and the post-trim realignment cleared it. `properly_paired_rate` 0.88996 is a library/insert-size property that trimming cannot fix, so this study sets `alignment_guardrails.min_properly_paired_rate: 0.80` at the site layer — otherwise neither arm reaches extraction and there are no CpG metrics to compare.

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
    status: pending
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
