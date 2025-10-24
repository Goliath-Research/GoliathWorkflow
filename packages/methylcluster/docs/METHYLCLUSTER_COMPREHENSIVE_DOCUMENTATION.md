# MethylCluster: Comprehensive Documentation

## Table of Contents

1. [Overview](#overview)
2. [Mathematical Theory](#mathematical-theory)
3. [Core Concepts](#core-concepts)
4. [Clustering Algorithm](#clustering-algorithm)
5. [API Reference](#api-reference)
6. [Configuration](#configuration)
7. [Advanced Features](#advanced-features)
8. [Usage Examples](#usage-examples)
9. [Troubleshooting](#troubleshooting)
10. [Integration with MethylPipeline](#integration-with-methylpipeline)
11. [Performance](#performance)
12. [License](#license)

---

## Overview

**MethylCluster** is a high-performance clustering tool for methylation samples with three clustering methods: HDBSCAN (density-based), Hierarchical, and Centroid-based (EM-like iterative). It uses GPU-accelerated distance metrics and includes intelligent fallback mechanisms.

### What is MethylCluster?

MethylCluster enables exploratory analysis of methylation data by grouping similar samples:

- **Unsupervised Discovery**: Identify natural groupings without prior labels
- **Quality Control**: Detect batch effects and outliers
- **Subgroup Identification**: Find methylation-based subtypes within disease groups
- **Validation**: Verify expected groupings (e.g., healthy vs disease)
- **Supervised Clustering**: Force group assignments for confirmation analyses

### Key Features

- **Three Clustering Methods**: 
  - **HDBSCAN**: Density-based, handles noise, finds clusters of varying density
  - **Hierarchical**: Agglomerative clustering with linkage methods (average, ward, complete, single)
  - **Centroid-based**: EM-like iterative clustering with cluster-level centroids
- **K-means Fallback**: Automatic fallback when HDBSCAN produces ambiguous results
- **GPU-Accelerated Distances**: Leverages MethylUtils for 20-50x speedup
- **Multiple Distance Metrics**: Jensen-Shannon, Hellinger, Wasserstein, Jeffreys, Bhattacharyya
- **Distance Matrix Caching**: Save and reuse computed matrices
- **Centroid Management**: Creates actual cluster-level centroids (not just labels)
- **Soft Assignments**: Probabilistic cluster membership for centroid method
- **Forced Groups**: Supervised/confirmation clustering with predefined groups
- **Automatic K Selection**: Silhouette analysis for optimal cluster count
- **Rich Visualizations**: Heatmaps, dendrograms, MDS plots, cluster trees
- **Flexible Configuration**: JSON-based reproducible analyses

---

## Mathematical Theory

### Distance Metrics for Beta Distributions

MethylCluster computes pairwise distances between samples using information-theoretic metrics. Each sample's methylation at position $i$ is represented by Beta distribution $\text{Beta}(\alpha_i, \beta_i)$.

#### Jensen-Shannon Divergence

Bounded, symmetric measure of distribution similarity:

$$
D_{\text{JS}}(P, Q) = \frac{1}{2}D_{\text{KL}}(P \| M) + \frac{1}{2}D_{\text{KL}}(Q \| M)
$$

where $M = \frac{1}{2}(P + Q)$ is the mixture distribution.

**For samples**: Average over all common positions:

$$
D_{\text{JS}}(\text{Sample}_1, \text{Sample}_2) = \frac{1}{n}\sum_{i=1}^{n} D_{\text{JS}, i}(P_{1,i}, P_{2,i})
$$

**Properties**:
- Bounded: $0 \leq D_{\text{JS}} \leq \log 2$
- Symmetric
- **Use when**: Need interpretable, bounded distances

#### Hellinger Distance

Geometric distance between probability distributions:

$$
D_{\text{Hellinger}}(P, Q) = \sqrt{1 - BC(P, Q)}
$$

where Bhattacharyya Coefficient:

$$
BC(\alpha_1, \beta_1, \alpha_2, \beta_2) = \frac{B\left(\frac{\alpha_1 + \alpha_2}{2}, \frac{\beta_1 + \beta_2}{2}\right)}{\sqrt{B(\alpha_1, \beta_1) \cdot B(\alpha_2, \beta_2)}}
$$

**Properties**:
- Proper metric (satisfies triangle inequality)
- Bounded: $0 \leq D_{\text{Hellinger}} \leq 1$
- **Use when**: Need metric properties for MDS

#### Wasserstein Distance

Optimal transport distance:

$$
W_p(P, Q) = \left(\int_0^1 |F_P^{-1}(u) - F_Q^{-1}(u)|^p\,du\right)^{1/p}
$$

**Properties**:
- Accounts for distribution shape
- Computationally expensive
- **Use when**: Distribution topology matters

#### Weighted Jensen-Shannon

Entropy-weighted version emphasizing certain positions:

$$
D_{\text{WJS}}(P, Q) = \sum_i w_i \cdot D_{\text{JS}, i}(P_i, Q_i)
$$

where $w_i = \frac{1}{H(P_i) + \epsilon}$ down-weights high-entropy (uncertain) positions.

### HDBSCAN Algorithm

**Hierarchical Density-Based Spatial Clustering**:

#### Step 1: Core Distance

For point $p$ with $k$ nearest neighbors:

$$
\text{core}_k(p) = \text{distance to } k\text{-th nearest neighbor}
$$

#### Step 2: Mutual Reachability Distance

$$
d_{\text{mreach}}(p, q) = \max\{\text{core}_k(p), \text{core}_k(q), d(p, q)\}
$$

#### Step 3: Minimum Spanning Tree

Build MST on mutual reachability distances.

#### Step 4: Cluster Hierarchy

Extract hierarchy by sorting edges by distance and building dendrogram.

#### Step 5: Cluster Extraction

Extract flat clustering based on stability:

$$
\text{Stability}(C) = \sum_{p \in C} (\lambda_{\text{max}} - \lambda_{\text{birth}}(p))
$$

where $\lambda = \frac{1}{\text{distance}}$.

**Parameters**:
- `min_cluster_size`: Minimum cluster size
- `min_samples`: Minimum neighborhood size for core points
- `cluster_selection_epsilon`: Distance threshold for cluster merging

**Advantages**:
- Finds clusters of varying density
- Robust to noise (outliers labeled as -1)
- No need to specify number of clusters

---

## Core Concepts

### 1. Three Clustering Methods

MethylCluster provides three distinct clustering approaches:

#### Method 1: HDBSCAN (Density-Based)

**When to use**: Exploratory analysis when you don't know K, expect outliers, or have varying cluster densities.

**Characteristics**:
- Finds clusters of varying density
- Labels outliers as noise (label = -1)
- No need to specify number of clusters
- Requires distance matrix
- Can produce ambiguous results (triggers K-means fallback)

**Fallback Mechanism**: If HDBSCAN produces:
- All noise (no clusters)
- Single cluster with >20% noise
- >50% noise overall

Then automatically falls back to K-means with automatic K selection.

#### Method 2: Hierarchical (Agglomerative)

**When to use**: Need stable, interpretable hierarchical structure; want dendrogram visualization.

**Characteristics**:
- Creates hierarchical tree of merges
- Multiple linkage methods (average, ward, complete, single)
- Automatic K selection via silhouette
- Deterministic results
- Requires distance matrix

**Linkage Methods**:
- **Average**: Balanced, works well for most cases (default)
- **Ward**: Minimizes within-cluster variance (good for equal-sized clusters)
- **Complete**: Prefers compact clusters
- **Single**: Can produce long chains (rarely used)

#### Method 3: Centroid-Based (EM-like Iterative)

**When to use**: Need actual cluster centroids for downstream analysis, want soft assignments, or have known K.

**Characteristics**:
- Creates `ClusterCentroid` objects (not just labels)
- EM-like iterative assignment algorithm
- Multiple restarts to avoid local optima
- Soft assignments with membership probabilities
- Forced group initialization for supervised clustering
- Automatic K selection or fixed K
- Can work without pre-computed distance matrix (computes on-the-fly)

**Unique Features**:
- **Cluster Centroids**: Actual MethylSample centroids for each cluster
- **Forced Groups**: Pre-assign samples to groups (e.g., healthy/cancer confirmation)
- **Soft Assignments**: Probabilistic membership instead of hard labels
- **Cluster Balancing**: Post-processing to balance cluster sizes
- **Empty Cluster Rescue**: Automatically rescues empty clusters during iteration

### 2. Distance Matrix

**Precomputed Distance Matrix**:

For $n$ samples, compute $n \times n$ symmetric matrix:

$$
D = \begin{bmatrix}
0 & d_{12} & \cdots & d_{1n} \\
d_{21} & 0 & \cdots & d_{2n} \\
\vdots & \vdots & \ddots & \vdots \\
d_{n1} & d_{n2} & \cdots & 0
\end{bmatrix}
$$

**Why Precompute?**
- HDBSCAN requires only distances, not coordinates
- Can use any distance metric
- Cacheable for reuse with different HDBSCAN parameters

**Storage**: Saved as `.npz` (compressed NumPy) file.

### 3. Cluster Validation Metrics

#### Silhouette Score

Measures cluster cohesion and separation:

$$
s(i) = \frac{b(i) - a(i)}{\max\{a(i), b(i)\}}
$$

where:
- $a(i)$: Mean distance to samples in same cluster
- $b(i)$: Mean distance to samples in nearest cluster

**Interpretation**:
- $s \approx 1$: Well-clustered
- $s \approx 0$: On cluster boundary
- $s \approx -1$: Mis-clustered

#### DBCV (Density-Based Clustering Validation)

Specialized for HDBSCAN, considers density:

$$
\text{DBCV} = \frac{1}{n}\sum_{i=1}^{n} \text{validity}(cluster_i)
$$

**Range**: [-1, 1], higher is better.

### 4. Visualization Methods

#### Distance Matrix Heatmap

Visual representation of $D$ with hierarchical clustering dendrogram.

#### MDS (Multidimensional Scaling)

Projects distances to 2D:

$$
\min_{\mathbf{X}} \sum_{i < j} (d_{ij} - \|\mathbf{x}_i - \mathbf{x}_j\|)^2
$$

where $\mathbf{x}_i \in \mathbb{R}^2$ are 2D coordinates.

#### UMAP (Uniform Manifold Approximation and Projection)

Nonlinear dimensionality reduction preserving local and global structure.

#### Cluster Tree

HDBSCAN condensed tree showing cluster hierarchy and stability.

---

## Clustering Algorithm

### Complete Workflow

```
1. Load Samples
   ├─ Read HDF5 files for each sample
   ├─ Validate data
   └─ Store as MethylSample objects

2. Choose Clustering Method
   ├─ HDBSCAN: Distance-based, handles noise
   ├─ Hierarchical: Tree-based with linkage
   └─ Centroid: EM-like with cluster centroids

3. Compute Distance Matrix (HDBSCAN & Hierarchical)
   ├─ Find common positions across samples
   ├─ Extract Beta parameters at common positions
   ├─ Compute pairwise distances (GPU-accelerated)
   ├─ Construct symmetric matrix
   └─ Save to cache (optional)

4. Perform Clustering
   ├─ HDBSCAN → Build hierarchy → Extract clusters
   │   └─ Fallback to K-means if ambiguous
   ├─ Hierarchical → Build linkage tree → Cut at optimal K
   └─ Centroid → EM iterations → Create ClusterCentroids

5. Validate Clusters
   ├─ Compute silhouette score
   ├─ Compute DBCV (HDBSCAN only)
   └─ Analyze cluster sizes

6. Generate Visualizations
   ├─ Distance matrix heatmap
   ├─ MDS projection
   ├─ UMAP projection (optional)
   ├─ Cluster tree (HDBSCAN)
   └─ Save plots

7. Export Results
   ├─ Cluster assignments (JSON, CSV)
   ├─ Cluster centroids (HDF5, centroid method only)
   ├─ Distance matrix (.npz)
   ├─ Visualizations (HTML, PNG)
   └─ Summary statistics (JSON)
```

### Centroid-Based Clustering Algorithm

The centroid-based method is unique in creating actual `ClusterCentroid` objects (not just labels).

#### Algorithm Overview

```
For each restart (default: 3):
  1. Initialize K centroids (farthest-point heuristic or forced groups)
  2. Assign seed samples to their centroids
  3. Until convergence:
      For each sample in random order:
          a. Compute log-likelihood to all centroids
          b. If better cluster found, move sample:
              - Remove from current centroid
              - Add to best centroid
              - Update centroid statistics
          c. Rescue empty clusters if needed
      d. Enforce minimum cluster sizes
      e. Check convergence (<1% samples changed)
  4. Compute silhouette score for this run

Select best run by highest silhouette score
```

#### Key Steps Explained

**Step 1: Initialization**

Two modes:
1. **Farthest-Point Heuristic** (unsupervised):
   - Pick first sample randomly
   - For each subsequent centroid, pick sample farthest from existing centroids
   - Ensures well-separated initial centroids

2. **Forced Groups** (supervised):
   - Pre-assign samples to groups (e.g., first 35 samples = Healthy, next 12 = Cancer)
   - Create initial centroids from forced assignments
   - Useful for validating expected groupings

**Step 2: EM-like Iteration**

- **E-step** (implicit): Compute log-likelihood of each sample to each centroid
- **M-step** (implicit): Update centroid by adding/removing sample
- **Sequential**: Process one sample at a time (not batch)
- **Stochastic**: Shuffle sample order each iteration

**Step 3: Likelihood Computation**

For sample with methylation $\mathbf{x}$ and centroid with Beta parameters $(\alpha, \beta)$:

$$
\log L(\mathbf{x} | \text{centroid}) = \sum_{i=1}^{n} \log \text{Beta}(x_i; \alpha_i, \beta_i)
$$

Centroid with highest log-likelihood "wins" the sample.

**Step 4: Centroid Update**

`ClusterCentroid` uses `PositionAligner` internally:
- Adding sample: Updates $Sx$, $Sx^2$, $N$ accumulators → recalculates Beta parameters
- Removing sample: Reverse operation
- Automatic position alignment across all samples in cluster

**Step 5: Empty Cluster Rescue**

If cluster empties during iteration:
1. Find largest cluster
2. Remove farthest sample from largest cluster
3. Seed empty cluster with that sample

**Step 6: Minimum Size Enforcement**

After each full iteration:
- Check if any cluster < `min_cluster_size`
- Move farthest sample from largest cluster to small cluster
- Repeat until all clusters ≥ `min_cluster_size`

**Step 7: Multiple Restarts**

Run entire EM algorithm `num_restarts` times (default: 3):
- Different random sample orderings → different local optima
- Select run with highest silhouette score
- Mitigates local optima problem

#### Soft Assignments (Optional)

Instead of hard labels, compute membership probabilities:

$$
P(\text{cluster } k | \text{sample}) = \frac{\exp(L_k / T)}{\sum_{j=1}^{K} \exp(L_j / T)}
$$

where $L_k$ = log-likelihood, $T$ = temperature parameter.

Higher temperature → softer assignments (more uncertain)

### Step-by-Step Implementation

#### Step 1: Initialize

```python
from methyl_cluster import MethylCluster, MethylClusterConfig

config = MethylClusterConfig(
    samples=['/data/sample1', '/data/sample2', ...],
    chrom='1',
    ctx='CG',
    metric='jensen_shannon',
    min_cluster_size=5,
    output_dir='/output/clustering'
)

cluster = MethylCluster(config)
```

#### Step 2: Load Samples

```python
cluster.load_samples()

# Internally:
# - Reads {sample_dir}/{chrom}-{ctx}.h5 for each sample
# - Validates sample data
# - Stores MethylSample objects
```

#### Step 3: Compute Distances

```python
cluster.compute_distances()

# Process:
# 1. Find common positions
common_pos = find_common_positions(cluster.samples)

# 2. Extract Beta parameters
for i, sample1 in enumerate(cluster.samples):
    for j, sample2 in enumerate(cluster.samples[i+1:], i+1):
        # Align to common positions
        s1_aligned = sample1.align_to_positions(common_pos)
        s2_aligned = sample2.align_to_positions(common_pos)
        
        # Estimate Beta parameters
        alpha1, beta1 = estimate_beta_params(s1_aligned)
        alpha2, beta2 = estimate_beta_params(s2_aligned)
        
        # Compute distance (GPU-accelerated)
        distance = compute_distance(alpha1, beta1, alpha2, beta2, 
                                    metric=config.metric)
        
        distance_matrix[i, j] = distance
        distance_matrix[j, i] = distance

# Save cache
np.savez_compressed('distance_matrix.npz', matrix=distance_matrix)
```

#### Step 4: Cluster

```python
cluster.cluster()

# Internally uses HDBSCAN:
import hdbscan

clusterer = hdbscan.HDBSCAN(
    metric='precomputed',
    min_cluster_size=config.min_cluster_size,
    min_samples=config.min_samples,
    cluster_selection_epsilon=config.cluster_selection_epsilon
)

cluster.cluster_labels = clusterer.fit_predict(cluster.distance_matrix)
cluster.clusterer = clusterer
```

#### Step 5: Validate

```python
cluster.validate()

# Compute metrics
from sklearn.metrics import silhouette_score

if len(set(cluster.cluster_labels)) > 1:
    silhouette = silhouette_score(
        cluster.distance_matrix,
        cluster.cluster_labels,
        metric='precomputed'
    )
else:
    silhouette = -1.0

dbcv = cluster.clusterer.relative_validity_

print(f"Silhouette: {silhouette:.3f}")
print(f"DBCV: {dbcv:.3f}")
print(f"Clusters: {len(set(cluster.cluster_labels)) - (1 if -1 in cluster.cluster_labels else 0)}")
```

#### Step 6: Visualize

```python
cluster.visualize()

# Creates:
# - distance_matrix_heatmap.html (interactive Plotly)
# - mds_projection.html (2D scatter with cluster colors)
# - cluster_tree.html (HDBSCAN hierarchy)
# - summary_stats.json (cluster sizes, metrics)
```

#### Step 7: Save Results

```python
cluster.save_results()

# Exports:
results = {
    'cluster_assignments': {
        sample_name: int(label)
        for sample_name, label in zip(sample_names, cluster_labels)
    },
    'metrics': {
        'silhouette_score': silhouette,
        'dbcv': dbcv,
        'n_clusters': n_clusters,
        'n_noise': n_noise
    },
    'parameters': {
        'metric': config.metric,
        'min_cluster_size': config.min_cluster_size,
        'min_samples': config.min_samples
    }
}

with open('cluster_results.json', 'w') as f:
    json.dump(results, f, indent=2)
```

---

## API Reference

### MethylCluster Class

Main clustering class:

```python
class MethylCluster:
    def __init__(self, config: MethylClusterConfig):
        """Initialize with configuration."""
    
    def load_samples(self) -> None:
        """Load all samples from configured paths."""
    
    def compute_distances(self) -> None:
        """Compute pairwise distance matrix."""
    
    def cluster(self) -> None:
        """Perform HDBSCAN clustering."""
    
    def validate(self) -> Dict[str, float]:
        """Validate clustering and return metrics."""
    
    def visualize(self) -> None:
        """Generate all visualizations."""
    
    def save_results(self) -> None:
        """Save cluster results and metadata."""
    
    def run(self) -> Dict[str, Any]:
        """Execute complete workflow."""
```

### MethylClusterConfig Class

Configuration model:

```python
class MethylClusterConfig(BaseModel):
    # Sample specification
    samples: List[str] = Field(..., description="Sample directory paths")
    chrom: str = Field(..., description="Chromosome")
    ctx: str = Field(..., description="Context (CG, CHG, CHH)")
    
    # Distance metric
    metric: ClusterMetric = Field(
        default=ClusterMetric.JENSEN_SHANNON,
        description="Distance metric"
    )
    
    # HDBSCAN parameters
    min_cluster_size: int = Field(default=5, description="Min cluster size")
    min_samples: int = Field(default=1, description="Min samples for core")
    cluster_selection_epsilon: float = Field(
        default=0.0,
        description="Distance threshold for merging"
    )
    
    # Output
    output_dir: str = Field(..., description="Output directory")
    
    # Performance
    use_gpu: bool = Field(default=True, description="Enable GPU")
    cache_distance_matrix: bool = Field(
        default=True,
        description="Cache distance matrix"
    )
    
    # Visualization
    generate_visualizations: bool = Field(
        default=True,
        description="Generate plots"
    )
```

### DistanceMatrixComputer Class

Handles distance computation:

```python
class DistanceMatrixComputer:
    def __init__(
        self,
        samples: List[MethylSample],
        metric: ClusterMetric,
        use_gpu: bool = True
    ):
        """Initialize distance computer."""
    
    def compute_matrix(self) -> np.ndarray:
        """Compute full distance matrix."""
    
    def compute_pairwise(
        self,
        sample1: MethylSample,
        sample2: MethylSample
    ) -> float:
        """Compute distance between two samples."""
    
    def save_cache(self, file_path: str) -> None:
        """Save computed matrix to file."""
    
    @classmethod
    def load_cache(cls, file_path: str) -> np.ndarray:
        """Load cached distance matrix."""
```

---

## Configuration

### JSON Configuration Examples

####  Example 1: HDBSCAN with K-means Fallback

```json
{
  "samples": ["/data/healthy1", "/data/healthy2", "/data/cancer1", "/data/cancer2"],
  "chrom": "1",
  "ctx": "CG",
  
  "clustering_method": "hdbscan",
  "metric": "jensen_shannon",
  
  "min_cluster_size": 3,
  "min_samples": 1,
  "cluster_selection_epsilon": 0.0,
  "cluster_selection_method": "eom",
  "allow_single_cluster": false,
  
  "enable_kmeans_fallback": true,
  "max_k": 10,
  "silhouette_threshold": 0.2,
  
  "output_dir": "/output/clustering",
  "use_gpu": true,
  "cache_distance_matrix": true
}
```

#### Example 2: Hierarchical Clustering

```json
{
  "samples": ["/data/sample1", "/data/sample2", ...],
  "chrom": "1",
  "ctx": "CG",
  
  "clustering_method": "hierarchical",
  "metric": "hellinger",
  
  "linkage_method": "average",
  "max_k": 10,
  "silhouette_threshold": 0.3,
  "force_k": null,
  
  "output_dir": "/output/hierarchical",
  "use_gpu": true
}
```

#### Example 3: Centroid-Based (Unsupervised)

```json
{
  "samples": ["/data/sample1", "/data/sample2", ...],
  "chrom": "1",
  "ctx": "CG",
  
  "clustering_method": "centroid",
  "metric": "jensen_shannon",
  
  "force_k": 3,
  "min_cluster_size": 5,
  "max_em_iterations": 50,
  "convergence_threshold": 0.01,
  "num_restarts": 3,
  
  "enable_medoid_refinement": true,
  "balance_clusters": true,
  "soft_assignment": false,
  
  "output_dir": "/output/centroid",
  "use_gpu": true
}
```

#### Example 4: Centroid-Based with Forced Groups (Supervised)

```json
{
  "samples": [
    "/data/healthy1", "/data/healthy2", "/data/healthy3",
    "/data/cancer1", "/data/cancer2"
  ],
  "chrom": "1",
  "ctx": "CG",
  
  "clustering_method": "centroid",
  "metric": "jensen_shannon",
  
  "forced_groups": {
    "Healthy": 3,
    "Cancer": 2
  },
  
  "min_cluster_size": 2,
  "max_em_iterations": 50,
  "soft_assignment": true,
  "assignment_temperature": 1.0,
  
  "output_dir": "/output/forced_clustering",
  "use_gpu": true
}
```

### Key Parameters by Method

#### HDBSCAN Parameters
- `min_cluster_size`: Minimum samples per cluster (default: 5)
- `min_samples`: Core point neighborhood size (default: same as min_cluster_size)
- `cluster_selection_epsilon`: Distance threshold for merging (default: 0.0)
- `cluster_selection_method`: "eom" or "leaf" (default: "eom")
- `allow_single_cluster`: Allow single cluster result (default: false)
- `enable_kmeans_fallback`: Enable K-means fallback (default: false)

#### Hierarchical Parameters
- `linkage_method`: "average", "ward", "complete", or "single" (default: "average")
- `max_k`: Maximum K to test (default: sqrt(n_samples))
- `force_k`: Force specific K, skip silhouette analysis (optional)
- `silhouette_threshold`: Minimum score to accept clusters (default: 0.2)

#### Centroid-Based Parameters
- `force_k`: Number of clusters (required if no forced_groups)
- `forced_groups`: Dict of group labels and sizes for supervised clustering
- `max_em_iterations`: Maximum EM iterations (default: 50)
- `convergence_threshold`: Convergence fraction (default: 0.01)
- `num_restarts`: Multiple restarts to avoid local optima (default: 3)
- `soft_assignment`: Enable probabilistic membership (default: false)
- `assignment_temperature`: Softmax temperature for soft assignments (default: 1.0)
- `enable_medoid_refinement`: Refine using K-medoids (default: true)
- `balance_clusters`: Balance cluster sizes (default: true)
- `validate_init`: Validate forced initialization (default: false)

### Available Distance Metrics

- `"jensen_shannon"`: Bounded, symmetric (default, recommended)
- `"hellinger"`: Geometric distance, proper metric
- `"wasserstein"`: Optimal transport (slower)
- `"jeffreys"`: Symmetric KL divergence
- `"bhattacharyya"`: Distribution overlap
- `"weighted_jensen_shannon"`: Entropy-weighted
- `"kl"`: Kullback-Leibler divergence

---

## Advanced Features

### 1. Distance Matrix Caching

```python
# First run: compute and cache
config = MethylClusterConfig(
    ...,
    cache_distance_matrix=True,
    distance_matrix_cache='/cache/dist_matrix.npz'
)

cluster = MethylCluster(config)
cluster.compute_distances()  # Saves to cache

# Subsequent runs: load from cache
cluster2 = MethylCluster(config)
cluster2.distance_matrix = np.load('/cache/dist_matrix.npz')['matrix']
cluster2.cluster()  # Skip distance computation
```

### 2. GPU Acceleration

Automatic GPU detection and usage:

```python
from methyl_utils import is_gpu_available

if is_gpu_available():
    # GPU-accelerated distance computation
    # 20-50x faster than CPU
    pass
else:
    # Automatic CPU fallback
    pass
```

### 3. Parameter Optimization

Find optimal HDBSCAN parameters:

```python
from sklearn.model_selection import ParameterGrid

param_grid = {
    'min_cluster_size': [3, 5, 10],
    'min_samples': [1, 3, 5],
    'cluster_selection_epsilon': [0.0, 0.1, 0.2]
}

best_score = -1
best_params = None

for params in ParameterGrid(param_grid):
    config = MethylClusterConfig(..., **params)
    cluster = MethylCluster(config)
    cluster.run()
    
    metrics = cluster.validate()
    score = metrics['silhouette_score']
    
    if score > best_score:
        best_score = score
        best_params = params

print(f"Best parameters: {best_params}")
print(f"Best silhouette: {best_score:.3f}")
```

### 4. Batch Processing

Cluster multiple chromosome/context combinations:

```python
for chrom in ['1', '2', '3']:
    for ctx in ['CG', 'CHG']:
        config = MethylClusterConfig(
            samples=sample_paths,
            chrom=chrom,
            ctx=ctx,
            output_dir=f'/output/clustering/chr{chrom}_{ctx}',
            ...
        )
        
        cluster = MethylCluster(config)
        result = cluster.run()
        
        print(f"{chrom}-{ctx}: {result['metrics']['n_clusters']} clusters")
```

---

## Usage Examples

### Example 1: Hierarchical Clustering (Recommended)

```python
from methyl_cluster import MethylCluster, MethylClusterConfig, ClusteringMethod

config = MethylClusterConfig(
    samples=[
        '/data/healthy1', '/data/healthy2', '/data/healthy3',
        '/data/cancer1', '/data/cancer2', '/data/cancer3'
    ],
    chrom='1',
    ctx='CG',
    clustering_method=ClusteringMethod.HIERARCHICAL,
    linkage_method='average',
    output_dir='/output/clustering'
)

cluster = MethylCluster(config)
result = cluster.run()

print(f"Method: {result['clustering_method']}")
print(f"Found {result['metrics']['n_clusters']} clusters")
print(f"Silhouette score: {result['metrics']['silhouette_score']:.3f}")
print("Cluster assignments:")
for sample, label in result['cluster_assignments'].items():
    print(f"  {sample}: Cluster {label}")
```

### Example 2: HDBSCAN with K-means Fallback

```python
from methyl_cluster import MethylCluster, MethylClusterConfig, ClusteringMethod

config = MethylClusterConfig(
    samples=sample_paths,
    chrom='1',
    ctx='CG',
    clustering_method=ClusteringMethod.HDBSCAN,
    min_cluster_size=5,
    enable_kmeans_fallback=True,
    output_dir='/output/hdbscan'
)

cluster = MethylCluster(config)
result = cluster.run()

print(f"Method used: {result['clustering_method']}")  # Could be 'hdbscan' or 'kmeans'
print(f"Clusters: {result['metrics']['n_clusters']}")
print(f"Noise points: {result['metrics']['n_noise']}")

if result['clustering_method'] == 'kmeans':
    print("Note: HDBSCAN was ambiguous, used K-means fallback")
```

### Example 3: Centroid-Based (Unsupervised)

```python
from methyl_cluster import MethylCluster, MethylClusterConfig, ClusteringMethod

config = MethylClusterConfig(
    samples=sample_paths,
    chrom='1',
    ctx='CG',
    clustering_method=ClusteringMethod.CENTROID,
    force_k=3,  # Specify K
    num_restarts=5,  # More restarts for better convergence
    output_dir='/output/centroid'
)

cluster = MethylCluster(config)
result = cluster.run()

print(f"Found {result['metrics']['n_clusters']} clusters")
print(f"Silhouette score: {result['metrics']['silhouette_score']:.3f}")

# Access cluster centroids (ClusterCentroid objects)
centroids = result.get('centroids', [])
for centroid in centroids:
    print(f"Cluster {centroid.cluster_id}: {centroid.get_sample_count()} samples")
    # Can save centroids for downstream analysis
    centroid.save(f"/output/centroid/cluster_{centroid.cluster_id}.h5")
```

### Example 4: Forced Groups (Supervised Clustering)

```python
from methyl_cluster import MethylCluster, MethylClusterConfig, ClusteringMethod

# First 35 samples are healthy, next 12 are cancer
healthy_samples = [f'/data/healthy{i}' for i in range(1, 36)]
cancer_samples = [f'/data/cancer{i}' for i in range(1, 13)]
all_samples = healthy_samples + cancer_samples

config = MethylClusterConfig(
    samples=all_samples,
    chrom='1',
    ctx='CG',
    clustering_method=ClusteringMethod.CENTROID,
    forced_groups={
        'Healthy': 35,
        'Cancer': 12
    },
    soft_assignment=True,  # Get membership probabilities
    assignment_temperature=1.0,
    output_dir='/output/forced'
)

cluster = MethylCluster(config)
result = cluster.run()

print(f"Clusters: {result['metrics']['n_clusters']}")
print(f"Silhouette: {result['metrics']['silhouette_score']:.3f}")

# Check soft assignments
if 'soft_assignments' in result:
    probs = result['soft_assignments']
    for i, sample in enumerate(all_samples):
        print(f"{sample}: Healthy={probs[i,0]:.3f}, Cancer={probs[i,1]:.3f}")
```

### Example 5: Quality Control Clustering

```python
from methyl_cluster import MethylCluster, MethylClusterConfig, ClusteringMethod

# Cluster all samples to detect batch effects or outliers
config = MethylClusterConfig(
    samples=all_sample_paths,  # 50+ samples
    chrom='1',
    ctx='CG',
    clustering_method=ClusteringMethod.HDBSCAN,
    metric='jensen_shannon',
    min_cluster_size=5,
    enable_kmeans_fallback=True,
    output_dir='/output/qc_clustering'
)

cluster = MethylCluster(config)
result = cluster.run()

# Identify outliers (noise = -1 for HDBSCAN)
outliers = [
    sample for sample, label in result['cluster_assignments'].items()
    if label == -1
]

print(f"Potential outliers: {len(outliers)}")
for outlier in outliers:
    print(f"  {outlier}")
```

### Example 6: Subtype Discovery

```python
# Find methylation-based subtypes within disease group

cancer_samples = [f'/data/cancer/sample{i}' for i in range(1, 31)]

config = MethylClusterConfig(
    samples=cancer_samples,
    chrom='1',
    ctx='CG',
    metric='hellinger',
    min_cluster_size=3,
    output_dir='/output/subtype_discovery'
)

cluster = MethylCluster(config)
result = cluster.run()

# Analyze subtypes
for cluster_id in set(result['cluster_assignments'].values()):
    if cluster_id == -1:
        continue
    
    samples_in_cluster = [
        s for s, label in result['cluster_assignments'].items()
        if label == cluster_id
    ]
    
    print(f"Subtype {cluster_id}: {len(samples_in_cluster)} samples")
    for sample in samples_in_cluster:
        print(f"  {sample}")
```

### Example 4: Comparison with Expected Groups

```python
# Verify that clustering matches known groups

config = MethylClusterConfig(
    samples=healthy_samples + cancer_samples,
    chrom='1',
    ctx='CG',
    output_dir='/output/validation'
)

cluster = MethylCluster(config)
result = cluster.run()

# Compare with ground truth
from sklearn.metrics import adjusted_rand_score

true_labels = [0]*len(healthy_samples) + [1]*len(cancer_samples)
predicted_labels = list(result['cluster_assignments'].values())

ari = adjusted_rand_score(true_labels, predicted_labels)
print(f"Adjusted Rand Index: {ari:.3f}")
```

### Example 5: Using Cached Distance Matrix

```python
# First run: compute and cache
config = MethylClusterConfig(
    samples=sample_paths,
    chrom='1',
    ctx='CG',
    cache_distance_matrix=True,
    distance_matrix_cache='/cache/matrix.npz',
    output_dir='/output/clustering_run1'
)

cluster1 = MethylCluster(config)
cluster1.compute_distances()  # Slow, but cached
cluster1.save_distance_matrix('/cache/matrix.npz')

# Second run: different HDBSCAN parameters, same distance matrix
cluster2 = MethylCluster(config)
cluster2.load_distance_matrix('/cache/matrix.npz')  # Fast!
cluster2.config.min_cluster_size = 10  # Change parameter
cluster2.cluster()  # Re-cluster with new parameters
```

### Example 6: Multiple Metrics Comparison

```python
metrics = ['jensen_shannon', 'hellinger', 'wasserstein']
results = {}

for metric in metrics:
    config = MethylClusterConfig(
        samples=sample_paths,
        chrom='1',
        ctx='CG',
        metric=metric,
        output_dir=f'/output/clustering_{metric}'
    )
    
    cluster = MethylCluster(config)
    result = cluster.run()
    
    results[metric] = {
        'n_clusters': result['metrics']['n_clusters'],
        'silhouette': result['metrics']['silhouette_score']
    }

# Compare
import pandas as pd
comparison_df = pd.DataFrame(results).T
print(comparison_df)
```

---

## Troubleshooting

### Common Issues

#### 1. All Samples in Single Cluster

**Problem**: HDBSCAN finds only one cluster

**Solutions**:
```python
# Reduce min_cluster_size
config = MethylClusterConfig(..., min_cluster_size=2)

# Try different metric
config = MethylClusterConfig(..., metric='hellinger')

# Check distance distribution
import matplotlib.pyplot as plt
plt.hist(distance_matrix[np.triu_indices_from(distance_matrix, k=1)])
plt.show()
```

#### 2. All Samples Labeled as Noise

**Problem**: All labels are -1 (noise)

**Solutions**:
```python
# Increase cluster_selection_epsilon
config = MethylClusterConfig(..., cluster_selection_epsilon=0.1)

# Reduce min_cluster_size
config = MethylClusterConfig(..., min_cluster_size=2)
```

#### 3. GPU Out of Memory

**Problem**: CUDA out of memory during distance computation

**Solutions**:
```python
# Disable GPU
config = MethylClusterConfig(..., use_gpu=False)

# Process in batches
from methyl_utils import cleanup_gpu_memory
cleanup_gpu_memory()
```

#### 4. Slow Distance Computation

**Problem**: Distance matrix takes too long

**Solutions**:
```python
# Enable GPU
config = MethylClusterConfig(..., use_gpu=True)

# Use faster metric
config = MethylClusterConfig(..., metric='hellinger')  # Faster than Wasserstein

# Cache for reuse
config = MethylClusterConfig(..., cache_distance_matrix=True)
```

---

## Integration with MethylPipeline

### Use Cases

#### 1. Pre-Classification QC

```python
# Before centroid creation, cluster to identify outliers
from methyl_cluster import MethylCluster
from methyl_centroid import MethylCentroid

# Cluster
cluster_result = MethylCluster(config).run()

# Remove outliers (noise samples)
good_samples = [
    s for s, label in cluster_result['cluster_assignments'].items()
    if label != -1
]

# Create centroid without outliers
centroid = MethylCentroid(add_samples=good_samples, ...).build_centroid()
```

#### 2. Subtype Discovery

```python
# Find subtypes within disease group
cluster_result = MethylCluster(cancer_samples_config).run()

# Create separate centroids for each subtype
for subtype_id in set(cluster_result['cluster_assignments'].values()):
    if subtype_id == -1:
        continue
    
    subtype_samples = [
        s for s, l in cluster_result['cluster_assignments'].items()
        if l == subtype_id
    ]
    
    centroid = MethylCentroid(
        add_samples=subtype_samples,
        group=f'Cancer_Subtype_{subtype_id}',
        ...
    ).build_centroid()
```

#### 3. Validation

```python
# Verify classifier predictions cluster correctly
from methyl_classifier import MethylClassifier

classifier = MethylClassifier(model_path='classifier.pkl')
predictions = [classifier.predict(s) for s in test_samples]

# Cluster test samples
cluster_result = MethylCluster(test_samples_config).run()

# Check if clustering matches predictions
# (Should cluster by predicted class)
```

---

## Performance

### Benchmarks

#### Distance Matrix Computation

| Samples | Positions | CPU Time | GPU Time | Speedup |
|---------|-----------|----------|----------|---------|
| 10 | 1M | 20s | 1s | 20x |
| 50 | 1M | 500s | 15s | 33x |
| 100 | 1M | 2000s | 50s | 40x |

#### HDBSCAN Clustering

| Samples | Distance Matrix | Clustering Time |
|---------|----------------|-----------------|
| 10 | Precomputed | 0.5s |
| 50 | Precomputed | 2s |
| 100 | Precomputed | 5s |

### Memory Usage

- Distance matrix (n samples): $n^2 \times 8$ bytes (float64)
  - 50 samples: 20 KB
  - 100 samples: 80 KB
  - 1000 samples: 8 MB

---

## License

MethylCluster is licensed under the MIT License.

---

## Citation

```bibtex
@software{methylcluster2024,
  title={MethylCluster: HDBSCAN Clustering for Methylation Data},
  author={MethylPipeline Contributors},
  year={2024},
  url={https://github.com/yourusername/MethylPipeline}
}
```

---

*End of MethylCluster Comprehensive Documentation*

**Last Updated**: October 2024  
**Version**: 1.0.0

