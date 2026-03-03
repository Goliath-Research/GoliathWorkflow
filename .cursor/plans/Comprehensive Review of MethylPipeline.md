# Comprehensive Review of MethylPipeline Mono-Repo

## Executive Summary
MethylPipeline is a well-structured Python monorepo for analyzing bisulfite sequencing data (WGBS/RRBS), focusing on group-level methylation representations via **centroids** and **biologically-informed DMP detection**. It implements a production pipeline (AlignmentQC → Centroid → Detector → Classifier → Predictor) and research extensions (Validation via Monte Carlo CV, Mapper, Enricher). 

**Theoretical Strengths**: 
- **Centroids** aggregate sufficient statistics (e.g., sums for means/vars, log-sums for Beta fits) across samples in a group, enabling robust group representations that mitigate individual variability—novel for bulk DMP workflows (standard methods like dmrseq/methylSig model individuals via beta-binomial).
- **DMP Selection**: Combines FDR q-values with biological priors (effect size ≥0.2, |Δmean| ≥0.2, overlap ≤0.8) and **discrimination capacity** (greedy/binary search for 99% balanced accuracy threshold)—prioritizes actionable biomarkers over pure stats.
- Aligns with 2024–2026 trends (e.g., Amethyst/scEpi2 for sc-methyl centroids, DiffMethylTools for effect-size-aware DMRs).

**Implementation Strengths**: Modular (10 Poetry packages), GPU-accelerated (CuPy/cuDF), unified Pydantic-validated JSON configs, extensive docs. Production-ready for HPC/Docker with manual CLI orchestration.

**Potential Gaps**: No automated orchestrator (manual sequencing/scripts), dev-stage versions (0.1–1.0), mixed Poetry/setuptools. Metrics distributions robust but assume binary classification.

## Theoretical Background and Novelty
### Standard Methylation Pipelines (WGBS/RRBS)
- **Data**: Per-CpG/site counts (mC methylated reads, uC unmethylated, cov=mC+uC).
- **QC**: Alignment metrics (duplication, dedup).
- **DMP/DMR Detection**: Beta-binomial GLM (methylSig), GLS (dmrseq), sliding windows (swDMR). Focus: p/q-values; effect size (Δmean, Cohen's d) secondary. Multi-sample variability modeled directly.
- **Classification**: Logistic/probit on top DMPs; often limma-voom.
- **Validation**: CV (k-fold/Monte Carlo); metrics: accuracy, bal_acc, sens/spec.
- **Annotation**: Bedtools to genes; ORA (Enrichr/gseapy).

From recent lit (2024–2026): Emphasis on sc-resolution (Amethyst clusters via methylation windows), multi-omic (scEpi2-seq), ancestry-DMPs in prostate Ca (hyper-methylation separates groups via PCA).

### MethylPipeline Innovations
- **a) Centroids for Group Representation**: Instead of per-sample modeling, compute **group centroids** (MethylExtendedCentroid/BetaBinomialCentroid) via streaming GPU accumulation:
  - Sufficient stats: N (samples), Sx=∑x, Sx2=∑x², log∑log(x), log∑log(1-x); optional BB (sum_mC, sum_cov², etc.).
  - Distributions: Normal/ECDF (small N<30), Beta (MLE/MoM), BetaBinomial (discrete).
  - **Advantage**: Noise reduction, scalable to 100s samples/chr/ctx; enables centroid-pair Δmean/effect_size directly.
  
  Novelty: Bulk equivalent to sc-population averages; contrasts individual-level GLMs.

- **b) DMPs by Effect Size + Discrimination**:
  - Filters: q≤α (Storey FDR), |Δmean|≥min_delta, effect_size≥min (var-normalized?), overlap≤max.
  - **Discrimination**: Binary search/featurecuts optimizes DMP subset for target bal_acc (e.g., 0.99) on held-out positions—**probabilistic classifier preview**.
  - Model: ProbabilisticBetaClassifier (Beta log-likelihood ratio per DMP; chr/ctx weighted avg, optional Platt/temp scaling).
  
  Novelty: Integrates biology (effect_size) + utility (discrimination AUC-like); beyond p-value only.

- **Multi-Chr/Context Classifier**: Per-chr models → trimmed-mean weights (or fitted Lasso); hyperslice loads only DMP positions.
- **Research**: MC-CV distributions (mean/std/p95 bal_acc etc.); min-DMP max-gene (Stouffer gene p-values); Enrichr ORA on filtered genes.

Robust for prostate Ca (Healthy vs PCa1-4 configs); extensible multiclass.

## Mono-Repo Structure and Orchestration
**Layout** (inferred tree; ~10 Poetry packages, docs/MkDocs):

```
MethylPipeline/
├── configs/          # 170+ JSONs/CSVs (e.g., project_Healthy_vs_PCa1-4.json)
├── docs/             # ARCHITECTURE.md, THEORY_AND_PACKAGES.md, OPERATIONS_MANUAL.md
├── packages/         # methylalignmentqc, methylcentroid, methyldetector, etc.
│   └── methylutils/  # Shared: GPU I/O, config, MethylSample/CentroidFrame
├── scripts/          # install_all.sh
├── pyproject.toml    # Root tooling (pytest/black)
└── README.md, PROJECT_OVERVIEW.md
```

**Packages/Scripts** (Poetry CLIs):

| Package | CLI | Role |
|---------|-----|------|
| methylalignmentqc | `methyl-qc` | Parse Parabricks QC → JSONs |
| methylcentroid | `methyl-centroid[-explorer]` | Samples → centroids H5 |
| methyldetector | `methyl-detector` | Centroids → DMPs/models |
| methylclassifier | `methyl-classifier` | Models → sample probs |
| methylpredictor | `methyl-predictor` | Probs → metrics CSV/JSON |
| methylvalidation | `methyl-validation` | MC-CV distributions |
| methylmapper | `methyl-mapper` | DMPs → genes (Stouffer) |
| methylenricher | `methyl-enricher` | Genes → ORA (gseapy/Enrichr) |

**Configs** (Pydantic `ProjectConfig`; unified):

```json
// configs/project_Healthy_vs_PCa1-4.json (excerpt)
{
  "project_name": "Healthy_vs_PCa1-4",
  "output_base": "/home/ubuntu/Work/prostate-cancer",
  "controls": {"label": "healthy", "groups": [{"label": "healthy", "sample_paths": ["configs/healthy.csv"]}]},
  "diseases": {"label": "cancer", "groups": [... "pca1.csv" ..], "comparisons": [{"control_group": "healthy", "disease_group": "pca1"}, ...]},
  "step_config": {"centroid": {"min_coverage": 4, "use_gpu": true}, "detection": {"alpha": 0.01, "min_effect_size": 0.2, ...}}
}
```

Derives paths (e.g., `centroids/healthy/1-CG.h5`); `--step-override` merges.

**Execution**:
- **Production**: Sequential CLIs: `methyl-qc --project cfg.json && methyl-centroid --group healthy --project cfg.json && methyl-detector --project cfg.json && ...`
- **Research**: `methyl-validation --config monte_carlo.json --project cfg.json` (automates splits/pipeline); then mapper/enricher.
- **Inspection**: `methyl-centroid-explorer centroids/healthy/` (type-detects, position tables).

## Detailed Implementation Review
### 1. MethylAlignmentQC
Parses alignment metrics (`*deduplicate_metrics.txt`) → validated JSONs.

Key: Streaming parser, summary stats. No ML/stats.

```python
# packages/methylalignmentqc/methyl_alignment_qc/core/writer.py:23
def process_samples_to_qc_jsons(sample_paths: List[str], output_dir: str, validate_schema: bool = True):
    parsed = core_parser.parse_metrics_from_sample_paths([Path(p) for p in sample_paths])
    # Write per-sample JSONs with summary_stats
```

**Quality**: Simple, robust; optional Pydantic schema.

### 2. MethylCentroid
**Core Innovation**: `MethylCentroidBuilder` streams samples (H5: pos/mC/uC/tnc), GPU searchsorted aligns positions, accumulates stats (min_cov=4).

Outputs: `MethylExtendedCentroid` (Normal/Beta/ECDF) or BB.

Explorer (`explorer.py`): Detects types, builds position tables (means/vars per distro).

```python
# packages/methylutils/methyl_utils/core/centroid_builder.py:27
class MethylCentroidBuilder:
    def __init__(self, min_coverage: int = 4, use_gpu: bool = True, ...):
        self.xp = cp if self.use_gpu else np
    def add_sample(self, sample_path):  # GPU merge/accumulate
        idx = self.xp.searchsorted(self.pos[:self.size], pos)
        # Grow, filter cov>0, Sx += mean*mC etc.
```

**Quality**: Memory-efficient (chunked), GPU scales to 100GB/chr. Handles CG/CHG/CHH.

### 3. MethylDetector
Pairs centroids (`MethylCentroidPair`), computes Δmean/effect_size, Beta fits, FDR, biological filters, optimizes DMP subset for bal_acc.

Outputs: DMP CSVs (biological-sorted), `.pkl` classifiers.

**Quality**: Hybrid MoM/MLE; greedy opt ensures utility.

### 4–5. MethylClassifier & MethylPredictor
Classifier: Loads per-chr models, DMP-hyperslicing, weighted probs (`trimmed_percentile` weights).

Predictor: Classifies test sets, sklearn metrics (bal_acc = (sens+spec)/2).

```python
# packages/methylclassifier/methyl_classifier/core/classifier.py:55
class MethylClassifier:
    def __init__(self, config): self.chromosome_weights = self._compute_chromosome_weights()  # Trimmed effect_size
```

**Quality**: Calibratable (Platt/temp); multiclass-ready.

### 6–8. Research Tools
- **Validation**: MC splits (train_frac=0.8), runs pipeline/ predictor per iter → `metrics_summary.json` (mean/p95 bal_acc etc.).
- **Mapper**: Bedtools → Stouffer gene p (signed Z, weights=-log10(p)); optimize min-k DMPs for stable genes.
- **Enricher**: Filter genes (disease-only, min_dmp=2), Enrichr ORA (KEGG/GO).

Docs exemplary (e.g., MethylValidation_Theoretical_Foundation.md).

## Production Readiness and Recommendations
**Pros**:
- Scalable (GPU, parallel chroms).
- Reproducible (configs/seeds, path_remap for Docker).
- Observable (timings, explorer, metrics distros).
- Extensible (multiclass comparisons).

**Cons/Improvements**:
- **Orchestration**: Add `methyl-pipeline` runner (Snakemake/Nextflow?).
- **Versions**: Pin deps (poetry lock), release to PyPI.
- **Tests/CI**: Root pytest good; add GitHub Actions.
- **Edge Cases**: Low-N groups (ECDF fallback), Y-chr, multiclass metrics.
- **Perf**: Profile GPU mem (docs/README_GPU_MEMORY_MANAGEMENT.md exists).

Overall: **Excellent for prod research/prod (e.g., prostate Ca cohorts)**; minor tooling for full automation. Matches key diffs perfectly.