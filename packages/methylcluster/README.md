# MethylCluster

**Multi-Method Clustering for Methylation Samples with GPU Acceleration**

## Overview

MethylCluster is a high-performance clustering tool for methylation samples offering three clustering methods: HDBSCAN (density-based), Hierarchical (tree-based), and Centroid-based (EM-like iterative). It includes intelligent fallback mechanisms and creates actual cluster-level centroids for downstream analysis.

### What is MethylCluster?

MethylCluster enables exploratory analysis of methylation data:

- **Quality Control**: Detect batch effects and outliers
- **Subtype Discovery**: Find methylation-based subtypes within disease groups
- **Validation**: Verify expected groupings (e.g., healthy vs cancer)
- **Supervised Clustering**: Force group assignments for confirmation analyses
- **Centroid Creation**: Generate cluster-level centroids for downstream use

## Key Features

- 🎯 **Three Clustering Methods**: HDBSCAN, Hierarchical, Centroid-based
- 🔄 **K-means Fallback**: Automatic fallback when HDBSCAN is ambiguous
- 📊 **Multiple Distance Metrics**: Jensen-Shannon, Hellinger, Wasserstein, Jeffreys, Bhattacharyya
- 🧬 **Cluster Centroids**: Creates actual `ClusterCentroid` objects (centroid method)
- 🎲 **Soft Assignments**: Probabilistic cluster membership
- 👥 **Forced Groups**: Supervised/confirmation clustering
- 🚀 **GPU Acceleration**: 20-50x speedup for distance computations
- 💾 **Distance Matrix Caching**: Reuse computed matrices
- 📈 **Rich Visualizations**: Heatmaps, dendrograms, MDS, cluster trees

## Installation

```bash
# Install from source
cd packages/methylcluster
pip install -e .

# Or as part of MethylPipeline
pip install methylpipeline
```

## Quick Start

### Hierarchical Clustering (Recommended)

```python
from methyl_cluster import MethylCluster, MethylClusterConfig, ClusteringMethod

config = MethylClusterConfig(
    samples=['/data/sample1', '/data/sample2', '/data/sample3', ...],
    chrom='1',
    ctx='CG',
    clustering_method=ClusteringMethod.HIERARCHICAL,
    linkage_method='average',
    output_dir='/output/clustering'
)

cluster = MethylCluster(config)
result = cluster.run()

print(f"Found {result['metrics']['n_clusters']} clusters")
print(f"Silhouette score: {result['metrics']['silhouette_score']:.3f}")
```

### HDBSCAN with K-means Fallback

```python
config = MethylClusterConfig(
    samples=sample_paths,
    chrom='1',
    ctx='CG',
    clustering_method=ClusteringMethod.HDBSCAN,
    min_cluster_size=5,
    enable_kmeans_fallback=True,  # Automatic fallback if needed
    output_dir='/output/hdbscan'
)

result = MethylCluster(config).run()

print(f"Method used: {result['clustering_method']}")  # 'hdbscan' or 'kmeans'
print(f"Clusters: {result['metrics']['n_clusters']}")
```

### Centroid-Based with Forced Groups (Supervised)

```python
# Validate expected groupings
healthy_samples = [f'/data/healthy{i}' for i in range(1, 36)]
cancer_samples = [f'/data/cancer{i}' for i in range(1, 13)]

config = MethylClusterConfig(
    samples=healthy_samples + cancer_samples,
    chrom='1',
    ctx='CG',
    clustering_method=ClusteringMethod.CENTROID,
    forced_groups={
        'Healthy': 35,
        'Cancer': 12
    },
    soft_assignment=True,  # Get membership probabilities
    output_dir='/output/validation'
)

result = MethylCluster(config).run()

# Check how well samples match expected groups
print(f"Silhouette: {result['metrics']['silhouette_score']:.3f}")

# Access cluster centroids
centroids = result.get('centroids', [])
for centroid in centroids:
    print(f"Cluster {centroid.cluster_id}: {centroid.get_sample_count()} samples")
```

## Three Clustering Methods

### 1. HDBSCAN (Density-Based)

**When to use**: Exploratory analysis, expect outliers, unknown number of clusters

**Features**:
- Finds clusters of varying density
- Labels outliers as noise (label = -1)
- No need to specify K
- K-means fallback if results are ambiguous

**Configuration**:
```python
clustering_method=ClusteringMethod.HDBSCAN
min_cluster_size=5
min_samples=1
enable_kmeans_fallback=True  # Recommended
```

### 2. Hierarchical (Agglomerative)

**When to use**: Need stable, interpretable hierarchy; dendrogram visualization

**Features**:
- Creates hierarchical tree
- Multiple linkage methods
- Automatic K selection via silhouette
- Deterministic results

**Configuration**:
```python
clustering_method=ClusteringMethod.HIERARCHICAL
linkage_method='average'  # or 'ward', 'complete', 'single'
max_k=10  # Maximum clusters to test
```

### 3. Centroid-Based (EM-like Iterative)

**When to use**: Need actual cluster centroids, forced groups, soft assignments

**Features**:
- Creates `ClusterCentroid` objects (not just labels)
- EM-like iterative assignment
- Multiple restarts to avoid local optima
- Forced group initialization
- Soft assignments with probabilities

**Configuration**:
```python
clustering_method=ClusteringMethod.CENTROID
force_k=3  # Or use forced_groups
num_restarts=3
soft_assignment=True
```

## Configuration Examples

### Example 1: Exploratory QC Clustering

```json
{
  "samples": ["/data/sample1", "/data/sample2", ...],
  "chrom": "1",
  "ctx": "CG",
  "clustering_method": "hierarchical",
  "metric": "jensen_shannon",
  "linkage_method": "average",
  "output_dir": "/output/qc"
}
```

### Example 2: Subtype Discovery

```json
{
  "samples": ["/data/cancer1", "/data/cancer2", ...],
  "chrom": "1",
  "ctx": "CG",
  "clustering_method": "centroid",
  "force_k": 3,
  "num_restarts": 5,
  "output_dir": "/output/subtypes"
}
```

### Example 3: Validation with Forced Groups

```json
{
  "samples": [
    "/data/healthy1", "/data/healthy2", "/data/healthy3",
    "/data/cancer1", "/data/cancer2"
  ],
  "chrom": "1",
  "ctx": "CG",
  "clustering_method": "centroid",
  "forced_groups": {
    "Healthy": 3,
    "Cancer": 2
  },
  "soft_assignment": true,
  "output_dir": "/output/validation"
}
```

## Distance Metrics

- **`jensen_shannon`**: Bounded, symmetric (default, recommended)
- **`hellinger`**: Geometric distance, proper metric
- **`wasserstein`**: Optimal transport (slower, but accounts for distribution shape)
- **`jeffreys`**: Symmetric KL divergence
- **`bhattacharyya`**: Distribution overlap
- **`weighted_jensen_shannon`**: Entropy-weighted (downweights uncertain positions)

## Documentation

📚 **[Comprehensive Documentation](docs/METHYLCLUSTER_COMPREHENSIVE_DOCUMENTATION.md)** - Complete guide covering:
- Mathematical theory for all three methods
- HDBSCAN algorithm and K-means fallback logic
- Centroid-based EM algorithm with enhancements
- Distance metrics for Beta distributions
- Configuration for each method
- Usage examples (QC, subtype discovery, validation)
- Troubleshooting and best practices

## Output Files

### All Methods

- **`cluster_assignments.json`**: Cluster labels for each sample
- **`distance_matrix.npz`**: Precomputed distance matrix (cached)
- **`silhouette_scores.json`**: Quality metrics
- **`distance_heatmap.html`**: Interactive heatmap
- **`mds_projection.html`**: 2D MDS visualization

### Centroid Method Only

- **`cluster_centroids/`**: Directory with centroid HDF5 files
- **`soft_assignments.csv`**: Membership probabilities (if enabled)

### HDBSCAN Only

- **`cluster_tree.html`**: HDBSCAN condensed tree
- **`noise_samples.txt`**: List of outlier samples

## Examples

### Example 1: Find Outliers

```python
from methyl_cluster import MethylCluster, MethylClusterConfig, ClusteringMethod

config = MethylClusterConfig(
    samples=all_sample_paths,
    chrom='1',
    ctx='CG',
    clustering_method=ClusteringMethod.HDBSCAN,
    min_cluster_size=5,
    output_dir='/output/qc'
)

result = MethylCluster(config).run()

# Identify outliers (noise = -1)
outliers = [
    sample for sample, label in result['cluster_assignments'].items()
    if label == -1
]

print(f"Found {len(outliers)} outliers")
for outlier in outliers:
    print(f"  {outlier}")
```

### Example 2: Discover Subtypes

```python
cancer_samples = [f'/data/cancer/sample{i}' for i in range(1, 31)]

config = MethylClusterConfig(
    samples=cancer_samples,
    chrom='1',
    ctx='CG',
    clustering_method=ClusteringMethod.CENTROID,
    force_k=3,  # Expect 3 subtypes
    num_restarts=5,
    output_dir='/output/subtypes'
)

result = MethylCluster(config).run()

# Analyze subtypes
for cluster_id in set(result['cluster_assignments'].values()):
    samples_in_cluster = [
        s for s, label in result['cluster_assignments'].items()
        if label == cluster_id
    ]
    print(f"Subtype {cluster_id}: {len(samples_in_cluster)} samples")
```

### Example 3: Validate Groupings with Soft Assignments

```python
config = MethylClusterConfig(
    samples=healthy_samples + cancer_samples,
    chrom='1',
    ctx='CG',
    clustering_method=ClusteringMethod.CENTROID,
    forced_groups={
        'Healthy': len(healthy_samples),
        'Cancer': len(cancer_samples)
    },
    soft_assignment=True,
    assignment_temperature=1.0,
    output_dir='/output/validation'
)

result = MethylCluster(config).run()

# Check soft assignments
if 'soft_assignments' in result:
    probs = result['soft_assignments']
    
    # Check if any samples have ambiguous membership
    for i, sample in enumerate(healthy_samples + cancer_samples):
        healthy_prob = probs[i, 0]
        cancer_prob = probs[i, 1]
        
        if abs(healthy_prob - cancer_prob) < 0.3:
            print(f"Ambiguous: {sample} (H={healthy_prob:.2f}, C={cancer_prob:.2f})")
```

### Example 4: Cache Distance Matrix

```python
# First run: compute and cache
config = MethylClusterConfig(
    samples=sample_paths,
    chrom='1',
    ctx='CG',
    clustering_method=ClusteringMethod.HIERARCHICAL,
    cache_distance_matrix=True,
    output_dir='/output/run1'
)

cluster1 = MethylCluster(config)
cluster1.compute_distances()  # Saved to cache

# Second run: reuse cached matrix with different parameters
config2 = MethylClusterConfig(
    samples=sample_paths,  # Same samples!
    chrom='1',
    ctx='CG',
    clustering_method=ClusteringMethod.HDBSCAN,
    min_cluster_size=10,  # Different parameter
    cache_distance_matrix=True,
    output_dir='/output/run2'
)

cluster2 = MethylCluster(config2)
# Automatically loads cached distance matrix
result2 = cluster2.run()
```

## K-means Fallback

HDBSCAN automatically falls back to K-means when:

1. No clusters found (all noise)
2. Single cluster with >20% noise (ambiguous)
3. >50% noise overall (weak structure)

**Enable fallback**:
```python
enable_kmeans_fallback=True
```

The best K is selected via silhouette analysis (K=2 to K=max_k).

## Integration with MethylPipeline

### Use Cases

1. **Pre-Centroid QC**: Remove outliers before creating centroids
2. **Subtype Discovery**: Find methylation-based subtypes
3. **Post-Classification Validation**: Verify predictions cluster correctly
4. **Batch Effect Detection**: Identify technical artifacts

### Workflow Examples

```
# QC workflow
Samples → MethylCluster → Remove outliers → MethylCentroid

# Subtype workflow
Samples → MethylCluster → Create centroid per subtype → MethylDetector

# Validation workflow
Samples → MethylClassifier → Predictions → MethylCluster → Compare
```

## Performance

### GPU Acceleration

| Samples | Positions | CPU Time | GPU Time | Speedup |
|---------|-----------|----------|----------|---------|
| 50 | 1M | 500s | 15s | 33x |
| 100 | 1M | 2000s | 50s | 40x |

### Memory Usage

- Distance matrix (50 samples): 20 KB
- Distance matrix (100 samples): 80 KB
- Cluster centroids: 2-4 MB per centroid

## Troubleshooting

### All Samples in One Cluster

**Solutions**:
```python
# Reduce min_cluster_size
min_cluster_size=2

# Try different metric
metric='hellinger'

# Use hierarchical instead of HDBSCAN
clustering_method=ClusteringMethod.HIERARCHICAL
```

### All Samples Labeled as Noise

**Solutions**:
```python
# Increase cluster_selection_epsilon
cluster_selection_epsilon=0.1

# Enable K-means fallback
enable_kmeans_fallback=True
```

### Centroid Clustering Not Converging

**Solutions**:
```python
# Increase iterations
max_em_iterations=100

# More restarts
num_restarts=5

# Check if forced_groups sizes are correct
```

## API Reference

### Main Class

```python
class MethylCluster:
    def __init__(self, config: MethylClusterConfig)
    def load_samples(self) -> None
    def compute_distances(self) -> None
    def cluster(self) -> Dict[str, Any]
    def run(self) -> Dict[str, Any]  # Complete workflow
```

### Configuration

```python
class MethylClusterConfig(BaseModel):
    samples: List[str]
    chrom: str
    ctx: str
    
    clustering_method: ClusteringMethod = ClusteringMethod.HIERARCHICAL
    metric: ClusterMetric = ClusterMetric.JENSEN_SHANNON
    
    # HDBSCAN parameters
    min_cluster_size: int = 5
    enable_kmeans_fallback: bool = False
    
    # Hierarchical parameters
    linkage_method: str = "average"
    
    # Centroid parameters
    force_k: Optional[int] = None
    forced_groups: Optional[Dict[str, int]] = None
    num_restarts: int = 3
    soft_assignment: bool = False
    
    output_dir: str
    use_gpu: bool = True
```

See [Comprehensive Documentation](docs/METHYLCLUSTER_COMPREHENSIVE_DOCUMENTATION.md) for complete API.

## License

MIT License - see [LICENSE](../../LICENSE) file for details.

---

For more information, see:
- [MethylCluster Comprehensive Documentation](docs/METHYLCLUSTER_COMPREHENSIVE_DOCUMENTATION.md)
- [MethylPipeline Documentation](../../docs/METHYLPIPELINE_COMPREHENSIVE_DOCUMENTATION.md)
