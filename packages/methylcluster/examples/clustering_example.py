"""
Example script demonstrating MethylCluster Python API usage.

This script shows how to:
1. Create a configuration programmatically
2. Load and align samples properly
3. Run clustering on aligned samples
4. Access and analyze results
"""

from pathlib import Path
import numpy as np
from methyl_cluster import MethylCluster, MethylClusterConfig, ClusterMetric
from methyl_utils import MethylSample
# PositionAligner removed - functionality now in MethylCentroidPair


def main():
    """Run clustering example."""
    
    # Define sample paths
    sample_paths = [
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/013361_10C26_34",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/010608_9N27_56",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/006655_9A_27_12",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/005315_9E16_11",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/028479_17D_23_51",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/024801_16Q_16_6",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/024775_16P_13_77",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/026702_15G_2_41",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/017918_10N_17_23",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/009600_9K28_87",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/015376_10_G12_1",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/015282_10_G9_89",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/033333_17T_21_76",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/026339_15O_2_66",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/035235_18O_12_11",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/024111_16D_28_61",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/008291_9G9_56",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/014924_10_F22_56",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/027168_16A_3_26",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/017500_10M_15_56",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/006534_9A_21_7",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/022372_15A_25_67",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/030761_17K_19_81",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/024972_17D_25_31",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/005943_7E9_37",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/021699_14_D2_67",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/024813_16Q_24_1",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/008860_9I11_23",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/004560_7D15_63",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/016687_10J_28_23",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/027019_15N_15_36",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/033941_18M_5_41",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/033214_17P_11_21",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/024943_17D_5_66",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/025138_17M_22_31",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/033699_17X_20_46",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/024962_17D_21_56",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/022495_15C_28_34",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/015826_10_H5_1",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/035734__21Y_24_1",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/027074_15Q_01_11",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/015403_10G_15_56",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/033234_17P_21_71",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/019896_10_X24_23",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/018700_16O_9_1",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/005992_7E14_1",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/024848_16R_27_21",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/030792_17L_17_1",
        "/home/ubuntu/Work/samples/humans/psomagen/AN00026418/022336_15A_8_34"
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
    
    # Load and align samples before clustering
    print("\nLoading and aligning samples...")
    samples = []
    for sample_path in sample_paths:
        h5_file = Path(sample_path) / f"{config.chrom}-{config.ctx}.h5"
        if h5_file.exists():
            sample = MethylSample.load_from_h5(h5_file)
            samples.append(sample)
            print(f"  Loaded sample: {len(sample.pos)} positions")
        else:
            print(f"  Warning: Sample file not found: {h5_file}")
    
    if len(samples) < 2:
        raise ValueError("Need at least 2 samples for clustering")
    
    # Align samples to common positions
    print(f"Aligning {len(samples)} samples to common positions...")
    # PositionAligner removed - functionality now in MethylCentroidPair
    # aligner = PositionAligner(max_samples=len(samples), use_gpu=False)  # Use CPU for alignment
    
    for i, sample in enumerate(samples):
        aligner.add_sample(sample, sample_index=i)
    
    print(f"Aligner initialized with {aligner.sample_count} samples")
    print(f"Position range: {aligner.position_range}")
    print(f"Total positions: {aligner.total_positions}")
    
    # Find common positions across all samples
    print("Finding common positions across all samples...")
    common_positions = set(samples[0].pos)
    for sample in samples[1:]:
        common_positions = common_positions.intersection(set(sample.pos))
    
    common_positions = np.array(sorted(list(common_positions)), dtype=np.uint32)
    print(f"Found {len(common_positions)} common positions")
    
    if len(common_positions) == 0:
        raise ValueError("No common positions found between samples")
    
    # Align all samples to common positions
    aligned_samples = []
    for i, sample in enumerate(samples):
        # Find indices of common positions in this sample
        common_indices = np.searchsorted(sample.pos, common_positions)
        
        # Check which positions actually exist
        valid_mask = (common_indices < len(sample.pos)) & (sample.pos[common_indices] == common_positions)
        
        # Create aligned arrays
        aligned_mC = np.zeros(len(common_positions), dtype=np.uint32)
        aligned_uC = np.zeros(len(common_positions), dtype=np.uint32)
        aligned_tnc = np.zeros(len(common_positions), dtype=np.uint8)
        
        aligned_mC[valid_mask] = sample.mC[common_indices[valid_mask]]
        aligned_uC[valid_mask] = sample.uC[common_indices[valid_mask]]
        aligned_tnc[valid_mask] = sample.tnc[common_indices[valid_mask]]
        
        # Create aligned sample
        aligned_sample = MethylSample(
            pos=common_positions,
            mC=aligned_mC,
            uC=aligned_uC,
            tnc=aligned_tnc
        )
        aligned_samples.append(aligned_sample)
        print(f"  Aligned sample {i+1}: {np.sum(valid_mask)} valid positions")
    
    print(f"✓ All samples aligned to {len(common_positions)} common positions")
    
    # Run clustering with aligned samples
    print("\nStarting clustering with aligned samples...")
    cluster = MethylCluster(config)
    cluster.samples = aligned_samples  # Use aligned samples
    cluster.sample_paths = [Path(p) for p in sample_paths]  # Keep original paths
    
    # Skip load_samples() since we already have aligned samples
    # Call compute_distances() and cluster() directly
    cluster.compute_distances()
    
    # Ensure distance matrix is double precision for HDBSCAN
    if cluster.distance_matrix is not None:
        cluster.distance_matrix = cluster.distance_matrix.astype(np.float64)
    
    results = cluster.cluster()
    cluster.save_results(results)
    
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

