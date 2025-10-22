# MethylCluster: Automated Clustering Strategy

## Two-Stage Approach for Unknown Cluster Structure

### Stage 1: HDBSCAN for Heterogeneity Detection

**Purpose**: Detect if the population has any density-based structure or outliers

**Configuration**:
```json
{
  "min_cluster_size": 5,  // ~10% of samples (adjust based on sample count)
  "min_samples": 3,
  "cluster_selection_epsilon": 0.0,
  "cluster_selection_method": "eom",
  "allow_single_cluster": true
}
```

**Interpretation**:
- **0 clusters, all noise** → Homogeneous population, no further clustering needed
- **1 cluster, < 20% noise** → Mostly homogeneous, noise samples are potential outliers
- **1 cluster, > 20% noise** → Ambiguous, proceed to Stage 2
- **2+ clusters** → Clear heterogeneity, use HDBSCAN results

### Stage 2: Hierarchical Clustering with Automatic K Selection

**When to use**: HDBSCAN suggests heterogeneity but results are ambiguous

**Methods for automatic K selection**:

#### Option A: Silhouette Analysis (Recommended)
- Compute silhouette scores for k=2 to k=sqrt(n)
- Choose k with highest silhouette score
- **Threshold**: If best silhouette < 0.2, declare homogeneous
- **Advantage**: Works well with distance matrices

#### Option B: Gap Statistic
- Compare within-cluster dispersion to null reference
- Choose k where gap is maximized
- **Advantage**: More rigorous statistical test

#### Option C: Elbow Method
- Plot within-cluster sum of distances vs k
- Choose k at the "elbow" point
- **Advantage**: Simple and intuitive

### Implementation Recommendations

#### For Your Current Data (49 samples)

**Stage 1 Results**:
- HDBSCAN: 1 cluster (5 samples) + 44 noise
- This suggests checking for heterogeneity

**Stage 2 Results**:
- Best silhouette score: 0.13 for k=5
- **Conclusion**: Score < 0.2 → **Population is homogeneous**
- The "heterogeneity" detected by HDBSCAN is due to tiny distance variations (CV=0.018)

#### Recommended Workflow

```python
def auto_cluster(distance_matrix, sample_paths):
    """
    Automated clustering with heterogeneity detection.
    """
    n_samples = len(distance_matrix)
    
    # Stage 1: HDBSCAN
    min_cluster_size = max(5, n_samples // 10)
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=max(3, min_cluster_size // 2),
        allow_single_cluster=True,
        metric='precomputed'
    )
    labels = clusterer.fit_predict(distance_matrix)
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = np.sum(labels == -1)
    noise_pct = n_noise / n_samples
    
    # Decision logic
    if n_clusters == 0:
        return {'status': 'homogeneous', 'method': 'hdbscan', 'clusters': 0}
    
    if n_clusters >= 2:
        return {'status': 'heterogeneous', 'method': 'hdbscan', 
                'clusters': n_clusters, 'labels': labels}
    
    if n_clusters == 1 and noise_pct < 0.2:
        return {'status': 'mostly_homogeneous', 'method': 'hdbscan',
                'clusters': 1, 'outliers': n_noise, 'labels': labels}
    
    # Stage 2: Hierarchical clustering with silhouette analysis
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform
    
    condensed_dist = squareform(distance_matrix, checks=False)
    linkage_matrix = linkage(condensed_dist, method='average')
    
    best_k = 1
    best_score = -1
    max_k = min(10, int(np.sqrt(n_samples)))
    
    for k in range(2, max_k + 1):
        clusters = fcluster(linkage_matrix, k, criterion='maxclust')
        score = compute_silhouette(distance_matrix, clusters)
        
        if score > best_score:
            best_score = score
            best_k = k
    
    # Threshold for meaningful clustering
    if best_score < 0.2:
        return {'status': 'homogeneous', 'method': 'hierarchical',
                'best_silhouette': best_score, 'clusters': 0}
    else:
        clusters = fcluster(linkage_matrix, best_k, criterion='maxclust')
        return {'status': 'heterogeneous', 'method': 'hierarchical',
                'clusters': best_k, 'silhouette': best_score, 'labels': clusters}
```

### Configuration Guidelines

**For exploratory analysis** (don't know if clusters exist):
```json
{
  "min_cluster_size": 5,
  "allow_single_cluster": true,
  "enable_hierarchical_fallback": true,
  "silhouette_threshold": 0.2
}
```

**For known heterogeneous populations**:
```json
{
  "min_cluster_size": 5,
  "allow_single_cluster": false,
  "cluster_selection_epsilon": 0.0
}
```

**For outlier detection only**:
```json
{
  "min_cluster_size": 10,  // Larger = stricter outlier detection
  "allow_single_cluster": true,
  "min_samples": 5
}
```

### Key Metrics

**Distance Matrix Quality**:
- Coefficient of variation > 0.05: Good cluster potential
- CV 0.02-0.05: Weak structure, may need hierarchical
- CV < 0.02: Likely homogeneous (like your current data)

**Silhouette Score Interpretation**:
- > 0.7: Strong, well-separated clusters
- 0.5-0.7: Reasonable structure
- 0.2-0.5: Weak structure, clusters overlap
- < 0.2: No meaningful clusters (homogeneous)

**HDBSCAN Noise Interpretation**:
- < 10% noise: Tight clusters
- 10-20% noise: Normal, some outliers
- 20-50% noise: Weak structure or wrong parameters
- > 50% noise: Likely homogeneous or wrong method

### For Your Current Dataset

**Conclusion**: With CV=0.018 and silhouette=0.13, these 49 samples form a **homogeneous population** with no meaningful subgroups. The pairwise alignment improvement revealed this biological reality more accurately.

**Recommendation**: Report as "no clusters detected" rather than forcing a clustering structure.

