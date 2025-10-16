"""
Example script demonstrating MethylCluster Python API usage.

This script shows how to:
1. Create a configuration programmatically
2. Run clustering
3. Access and analyze results
"""

from pathlib import Path
from methyl_cluster import MethylCluster, MethylClusterConfig, ClusterMetric


def main():
    """Run clustering example."""
    
    # Define sample paths
    sample_paths = [
        "/home/ubuntu/Work/samples/sample1",
        "/home/ubuntu/Work/samples/sample2",
        "/home/ubuntu/Work/samples/sample3",
        "/home/ubuntu/Work/samples/sample4",
        "/home/ubuntu/Work/samples/sample5",
    ]
    
    # Create configuration
    config = MethylClusterConfig(
        samples=sample_paths,
        chrom="1",
        ctx="CG",
        metric=ClusterMetric.JENSEN_SHANNON,
        min_cluster_size=2,
        min_samples=2,
        cluster_selection_epsilon=0.0,
        cluster_selection_method="eom",
        output_dir="./clustering_results",
        cache_distance_matrix=True,
        use_gpu=True
    )
    
    # Save configuration for reproducibility
    config.to_file("my_clustering_config.json")
    print("Configuration saved to my_clustering_config.json")
    
    # Run clustering
    print("\nStarting clustering...")
    cluster = MethylCluster(config)
    results = cluster.run()
    
    # Print results
    print("\n" + "="*60)
    print("Clustering Results")
    print("="*60)
    print(f"Number of clusters: {results['n_clusters']}")
    print(f"Noise samples: {results['n_noise']}")
    print(f"\nCluster sizes:")
    for cluster_name, size in results['cluster_sizes'].items():
        print(f"  {cluster_name}: {size} samples")
    
    print(f"\nDetailed cluster assignments:")
    for cluster_name, samples in results['cluster_assignments'].items():
        print(f"\n{cluster_name}:")
        for sample in samples:
            print(f"  - {sample}")
    
    print(f"\nResults saved to: {config.output_dir}")
    print("="*60)
    
    # Example: Load and reuse configuration
    print("\nExample: Loading configuration from file...")
    loaded_config = MethylClusterConfig.from_file("my_clustering_config.json")
    print(f"Loaded config for {loaded_config.chrom}-{loaded_config.ctx}")
    

if __name__ == "__main__":
    main()

