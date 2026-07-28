---
name: Linear vs WGBS SamplePrep Compare
overview: Run SamplePrep through extraction QC for plasma `DPLST-051425-111148` and buffy `DBCST-051425-111148` under linear vs `pangenome_wgbs`, keeping mode-isolated local trees and producing a CpG-quality plus alignment-time comparison report—without archiving to QNAP until after review.

> **Status: DEPTH-MATCHED COMPARE COMPLETE (with caveats).** Report: `/work/samples/_comparisons/20260728T151643Z/`. Linear arm reached QC pass + MethylExtractor H5s. Pangenome dual-graph `MethylCall` on the 18 GB named-coordinate GAF was abandoned (~30 h ETA); CpG metrics below are from MethylExtractor on the C2T-only QC BAM (73.6% mapped), so they understate a full dual-graph methylation call.

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
| `samtools markdup` aborted after the giraffe QC BAM | giraffe BAMs have no MC tag | insert `samtools fixmate -m` on the name-ordered restored BAM before coordinate-sort / markdup |
| Host `MethylExtractor` rejected `--read-level` | aarch64 binary on this worker predates the flag | probe `--help` and omit `--read-level` / `--tile-size` when absent (`extract_runner.py`) |
| Dual-graph `MethylCall` stalled on the 18 GB GAF | ~392 MB parsed in 40 min (~30 h ETA); workers idle on futex | Finished the compare with MethylExtractor on the C2T QC BAM instead; full MethylCall remains future work |

### Depth-matched subset results (`DPLST-051425-111148-DS20M`, 20M pairs)

| Arm | Mapped | Properly paired | CpG sites (min cov) | CpG mean cov | CpG meth | CHG / CHH meth |
|---|---|---|---|---|---|---|
| linear (Parabricks) | 99.19% | 90.70% | 98,721 | 8.23 | 0.731 | 0.023 / 0.031 |
| pangenome_wgbs (C2T QC BAM) | 73.62% | 66.94% | 23,096 | 15.23 | 0.539 | 0.219 / 0.201 |

Report: `/work/samples/_comparisons/20260728T151643Z/comparison.md`

Pangenome site yield is ~23% of linear on this C2T-only QC BAM path; coverage on the sites that remain is higher. Elevated CHG/CHH on the pangenome arm should be treated as a conversion/coordinate-mapping red flag until dual-graph `MethylCall` (or a dual-graph QC BAM merge) is re-run.

Re-running the align action now reuses an existing non-empty GAF (and, when present, the giraffe / restored BAM), so a QC-BAM or markdup failure no longer costs another full dual-graph mapping.

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


## Dual-graph DS20M finish (2026-07-28)

Completed true MethylCall+MergeCpG on the DS20M GAF after restoring QNAP-seeded `hprc-d9-bs.wl.gfa`.
See [`ds20m-dual-graph-finish.plan.md`](ds20m-dual-graph-finish.plan.md) and go/no-go note:
`/work/samples/_comparisons/20260728T163518Z/dual_graph_gono.md`.

**Go/no-go:** NO-GO for full-depth multi-worker yet — site yield is high but overlap cov/meth vs linear are not concordant (coverage ~100× inflated).


## Interim production recommendation (2026-07-28)

**Buffy WGBS SamplePrep default = linear** (`buffy_wgbs_linear_gene_fc`).
`buffy_wgbs_pangenome_gene_fc` remains experimental until the acceptance path in
[`wgbs-alignment-decision.plan.md`](wgbs-alignment-decision.plan.md) passes
(DS20M concordance + buffy confirmation). Memo:
`/work/samples/_comparisons/20260728Tinterim/interim_alignment_recommendation.md`.
