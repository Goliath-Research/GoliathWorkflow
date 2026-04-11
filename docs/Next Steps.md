(Original TOC preserved, with additions:  
- 5. MethylClassifier (expanded)  
- 6. MethylPredictor and MethylValidation (expanded)  
- 7. Legacy Components (deprecated notes)  
- 14. Case Study: Prostate Cancer Staging Progression (new)  

### 1. Scope, Traceability, and Notation
(Original content...)  
**Update**: Pipeline is hybrid: ECDFs for core aggregation/detection; parametric models (e.g., Beta-Binomial) in deprecated modules for specialized tasks.

### Part I: Mathematical and Statistical Foundations

#### 2. MethylUtils
(Original: ECDF reconstruction, KS/Mann-Whitney...)  
**Update**: Added note on GPU acceleration (e.g., CuPy for parallel Mann-Whitney on histograms) for large cohorts.

#### 3. MethylCentroid
(Original: Histograms, binomial thinning...)  
ECDFs central here for sufficient statistics.

#### 4. MethylDetector
(Original: DMP screening...)  
ECDFs key for two-sample comparisons.

#### 5. MethylClassifier (Expanded)
**5.1 Role**: Builds classifiers from detected DMPs for binary/multiclass staging (e.g., healthy vs. 4 prostate cancer levels).  

**5.2 Binary Classification**: Uses ECDF distances (e.g., KS statistic) to score samples against centroids. Score = max KS over DMPs.  

**5.3 Multi-Chromosome Binary Classification**: Aggregate per-chromosome scores via weighted sum, with weights from effect sizes (2.8).  

**5.4 One-vs-Rest (OvR) Multiclass Fusion (New Completion)**: For 5 classes (healthy + PCa1-4), train binary classifiers per class vs. rest. Fuse via softmax on scores: P(class i) = exp(score_i) / sum(exp(score_j)). Handles ordinal staging by optional monotonic constraints.  

**5.5 Pairwise Control Aggregation**: ... (original)  

**5.6 Bipartite Multi-Control × Multi-Disease Aggregation**: ... (original)  

**5.7 Calibration (New Completion)**: Apply isotonic regression on holdout set to map raw scores to probabilities. E.g., fit non-decreasing function f such that f(score) ≈ true positive rate.  

**5.8 Multiclass Learned Head: Class Weighting**: ... (original)  

**5.9 Missing Data Semantics (New Completion)**: Impute missing betas with cohort median or ECDF midpoint. If >20% missing per sample, flag as low-confidence.  

**5.10 Publication Guidance**: ... (original)  

#### 6. MethylPredictor and MethylValidation (Expanded)
**6.1 Role**: ... (original)  

**6.2 MethylPredictor: Labeled Evaluation (New Completion)**: Compute metrics like AUC, confusion matrices for multiclass. For staging, add ordinal metrics (e.g., mean absolute error on stage predictions).  

**6.3 Blind Prediction Summaries (New Completion)**: Generate CSV reports with predicted stages, confidence scores, and flagged low-visibility cases (see 6.10).  

**6.4 MethylValidation: Split Strategy**: ... (original)  

**6.5 Monte Carlo Evaluation**: ... (original)  

**6.6 What The Validation Layer Does Not Do**: ... (original)  

**6.7 Stability Analysis**: ... (original)  

**6.8 Production Freeze**: ... (original)  

**6.9 Two Workflows Summary**: ... (original)  

**6.10 Publication Guidance and Progression Visibility Checks (New Addition)**: For disease staging, assess evolution visibility post-validation. Compute ordinal trends (e.g., Spearman correlation between stage and pathway scores). If no significant trends (p > 0.05) or flat matrices, flag model as "useless" (insufficient discriminatory power). Example: In prostate cancer, check if EMT scores increase monotonically.  

#### 7. Legacy Components (Deprecated)
**Note (New)**: Deprecated components are retained only for historical compatibility notes and are excluded from the active canonical production workflow.

(Other chapters original, with minor deprecation notes where relevant.)

### Part II: Workflows and Production
(Original content preserved.)

#### 14. Case Study: Prostate Cancer Staging Progression (New)
