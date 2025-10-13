# Output Columns Explained for Biologists

## Overview

The output CSV files now include both technical (Bhattacharyya Distance) and biologist-friendly (Bhattacharyya Coefficient) measures to help interpret DMP quality.

## Key Output Columns

### Core Measurements

| Column | Range | What It Means | How to Interpret |
|--------|-------|---------------|------------------|
| `position` | Genomic position | CpG site location | Chromosome coordinate |
| `chromosome` | 1-22, X, Y | Which chromosome | From input file |
| `context` | CG, CHG, CHH | Methylation context | Sequence context |

### Statistical Significance

| Column | Range | What It Means | How to Interpret |
|--------|-------|---------------|------------------|
| `p_value` | 0-1 | Raw p-value | Lower = more significant |
| `q_value` | 0-1 | FDR-corrected p-value | Lower = more significant (controls false discoveries) |

### Methylation Levels

| Column | Range | What It Means | How to Interpret |
|--------|-------|---------------|------------------|
| `mean1` | 0-1 | Average methylation in group 1 (e.g., cancer) | 0 = unmethylated, 1 = fully methylated |
| `mean2` | 0-1 | Average methylation in group 2 (e.g., healthy) | 0 = unmethylated, 1 = fully methylated |
| `delta_mean` | -1 to 1 | Difference in methylation (mean1 - mean2) | Larger absolute value = bigger effect |

### Distribution Separation (KEY FOR BIOLOGISTS! 👀)

| Column | Range | What It Means | **For Biologists** |
|--------|-------|---------------|-------------------|
| `bhattacharyya_distance` | 0-20 | Technical separation measure | Higher = better separation (technical) |
| `bhattacharyya_coefficient` | 0-1 | **Overlap between distributions** | **Lower = better DMP!** ✅ |

#### Understanding Bhattacharyya Coefficient (BC)

**BC measures how much the two methylation distributions overlap:**

- **BC ≈ 0 (e.g., 0.001)**: Excellent DMP! 
  - Distributions barely overlap
  - Clear separation between groups
  - Strong biomarker candidate
  
- **BC ≈ 0.1-0.3**: Good DMP
  - Low overlap
  - Distributions well-separated
  - Useful for classification
  
- **BC ≈ 0.5-0.7**: Moderate DMP
  - Moderate overlap
  - Some separation
  - May be useful in combination

- **BC ≈ 0.9-1.0**: Poor DMP
  - High overlap
  - Distributions very similar
  - Not useful for discrimination

### Beta Distribution Parameters

These describe the shape of methylation distributions in each group:

| Column | Range | What It Means |
|--------|-------|---------------|
| `alpha1`, `beta1` | >0 | Shape parameters for group 1 distribution |
| `alpha2`, `beta2` | >0 | Shape parameters for group 2 distribution |

Higher alpha = more methylation, higher beta = less methylation

### Biological Importance Ranking

| Column | Range | What It Means | How to Interpret |
|--------|-------|---------------|------------------|
| `biological_importance` | >0 | Combined score for DMP quality | Higher = better DMP for classification |

**Formula:** `biological_importance = |delta_mean| / (BC + ε)`

This combines:
- **Effect size** (delta_mean): How different the groups are
- **Separation** (BC): How well the distributions separate
- Higher importance = large effect + good separation

## Example: Interpreting Your DMPs

### Excellent DMP
```
position: 12345678
chromosome: 2
q_value: 0.0001          ← Highly significant
delta_mean: 0.45         ← Large effect (45% difference)
bhattacharyya_coefficient: 0.002  ← Excellent separation! (0.2% overlap)
bhattacharyya_distance: 6.2       ← Technical: high separation
biological_importance: 225.0      ← Top-ranked DMP
mean1: 0.75 (cancer)     ← Highly methylated in cancer
mean2: 0.30 (healthy)    ← Lowly methylated in healthy
```
**Interpretation:** This is an excellent biomarker! Cancer samples are highly methylated (75%) while healthy samples are lowly methylated (30%), with almost no overlap between groups.

### Poor DMP
```
position: 87654321
q_value: 0.04            ← Borderline significant
delta_mean: 0.15         ← Small effect (15% difference)
bhattacharyya_coefficient: 0.75   ← Poor separation (75% overlap)
bhattacharyya_distance: 0.3       ← Technical: low separation
biological_importance: 0.2        ← Low-ranked DMP
mean1: 0.55 (cancer)     ← Moderately methylated
mean2: 0.40 (healthy)    ← Moderately methylated
```
**Interpretation:** This DMP shows statistical significance but poor biological utility. The groups have substantial overlap (75%), making it unreliable for classification.

## What to Look For

### Best DMPs Have:
1. ✅ **Low q-value** (< 0.01): Statistically robust
2. ✅ **Large |delta_mean|** (> 0.2): Big effect size
3. ✅ **Low BC** (< 0.3): Well-separated distributions ← **Most important!**
4. ✅ **High biological_importance**: Top-ranked for classification

### Red Flags:
1. ❌ High BC (> 0.7): Too much overlap
2. ❌ Small |delta_mean| (< 0.1): Weak effect
3. ❌ High q-value (> 0.05): Not statistically robust

## Quick Reference Table

| BC Value | Interpretation | Use in Classification |
|----------|----------------|----------------------|
| 0.00-0.10 | Excellent separation | Strong biomarker |
| 0.10-0.30 | Good separation | Useful biomarker |
| 0.30-0.50 | Moderate separation | Supporting biomarker |
| 0.50-0.70 | Poor separation | Weak biomarker |
| 0.70-1.00 | Very poor separation | Not recommended |

## Summary

**For quick DMP quality assessment, focus on `bhattacharyya_coefficient`:**
- Values close to 0 = excellent DMPs with clear group separation
- Values close to 1 = poor DMPs with overlapping distributions

Combined with large effect size (`delta_mean`) and low q-value, low BC values identify the best biomarker candidates for methylation-based classification.

