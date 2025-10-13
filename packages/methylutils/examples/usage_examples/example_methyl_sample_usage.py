#!/usr/bin/env python3
"""
Example demonstrating the new MethylSample usage in PositionAligner.

This example shows how to use the new add_sample() and remove_sample() methods
with MethylSample objects for better type safety and clarity.
"""

import numpy as np
from methyl_utils.methyl_sample import MethylSample
from methyl_utils import PositionAligner


def create_sample_data():
    """Create sample methylation data for demonstration."""
    # Create some sample positions
    positions = np.array([1000, 2000, 3000, 4000, 5000], dtype=np.uint32)
    
    # Create methylation data
    mC = np.array([10, 15, 8, 20, 12], dtype=np.uint32)
    uC = np.array([5, 10, 12, 8, 18], dtype=np.uint32)
    tnc = np.array([1, 2, 3, 1, 2], dtype=np.uint8)
    
    return positions, mC, uC, tnc


def create_centroid_data():
    """Create centroid methylation data for demonstration."""
    positions = np.array([1000, 2000, 3000, 4000, 5000], dtype=np.uint32)
    mC = np.array([25, 30, 20, 40, 24], dtype=np.uint32)
    uC = np.array([10, 15, 20, 16, 36], dtype=np.uint32)
    tnc = np.array([1, 2, 3, 1, 2], dtype=np.uint8)
    
    # Centroid-specific fields
    N = np.array([2, 2, 2, 2, 2], dtype=np.uint32)  # 2 samples contributed
    Sx = np.array([0.8, 0.7, 0.5, 0.8, 0.4], dtype=np.float32)
    Sx2 = np.array([0.64, 0.49, 0.25, 0.64, 0.16], dtype=np.float32)
    log_x_sum = np.array([-0.223, -0.357, -0.693, -0.223, -0.916], dtype=np.float32)
    log_1_minus_x_sum = np.array([-0.223, -0.357, -0.693, -0.223, -0.916], dtype=np.float32)
    
    return positions, mC, uC, tnc, N, Sx, Sx2, log_x_sum, log_1_minus_x_sum


def main():
    """Demonstrate the new MethylSample usage."""
    print("PositionAligner MethylSample Usage Example")
    print("=" * 50)
    
    # Create a PositionAligner
    aligner = PositionAligner(max_samples=10, use_gpu=False)
    aligner.set_min_coverage(2)
    
    # Create sample data
    pos, mC, uC, tnc = create_sample_data()
    
    # Create MethylSample objects
    sample1 = MethylSample.from_sample_data(pos, mC, uC, tnc)
    sample2 = MethylSample.from_sample_data(pos + 100, mC + 5, uC + 3, tnc)
    
    print(f"Created sample1 with {len(sample1.pos)} positions")
    print(f"Created sample2 with {len(sample2.pos)} positions")
    
    # Add samples using the new add_sample method
    print("\nAdding samples using add_sample()...")
    success1 = aligner.add_sample(sample1, sample_index=0)
    success2 = aligner.add_sample(sample2, sample_index=1)
    
    print(f"Sample 1 added: {success1}")
    print(f"Sample 2 added: {success2}")
    
    # Check aligner state
    print("\nAligner state:")
    print(f"  Sample count: {aligner.sample_count}")
    print(f"  Position range: {aligner.position_range}")
    print(f"  Total positions: {aligner.total_positions}")
    print(f"  Valid positions: {aligner.valid_positions}")
    
    # Create a centroid sample
    pos_c, mC_c, uC_c, tnc_c, N_c, Sx_c, Sx2_c, log_x_c, log_1_minus_x_c = create_centroid_data()
    centroid = MethylSample(
        pos=pos_c,
        mC=mC_c,
        uC=uC_c,
        tnc=tnc_c,
        N=N_c,
        Sx=Sx_c,
        Sx2=Sx2_c,
        log_x_sum=log_x_c,
        log_1_minus_x_sum=log_1_minus_x_c
    )
    
    print(f"\nCreated centroid with {len(centroid.pos)} positions")
    print(f"Centroid type: {centroid.sample_type}")
    print(f"Is centroid: {centroid.is_centroid}")
    
    # Add centroid using add_sample
    print("\nAdding centroid using add_sample()...")
    success_centroid = aligner.add_sample(centroid, sample_index=2)
    print(f"Centroid added: {success_centroid}")
    
    # Check updated state
    print("\nUpdated aligner state:")
    print(f"  Sample count: {aligner.sample_count}")
    print(f"  Valid positions: {aligner.valid_positions}")
    
    # Demonstrate remove_sample
    print("\nRemoving sample 1 using remove_sample()...")
    success_remove = aligner.remove_sample(sample1, sample_index=0)
    print(f"Sample 1 removed: {success_remove}")
    
    print("\nFinal aligner state:")
    print(f"  Sample count: {aligner.sample_count}")
    print(f"  Valid positions: {aligner.valid_positions}")
    
    # Demonstrate new methods
    print("\n" + "=" * 50)
    print("New MethylSample Methods Demo")
    print("=" * 50)
    
    # Test get_valid_positions
    print("\nTesting get_valid_positions()...")
    valid_positions = aligner.get_valid_positions(sample2)
    print(f"Valid positions in sample2: {len(valid_positions)}")

    # Test get_valid_positions_from_centroid
    print("\nTesting get_valid_positions_from_centroid()...")
    centroid_valid_pos = aligner.get_valid_positions_from_centroid()
    print(f"Valid positions in centroid: {len(centroid_valid_pos)}")

    # Test get_common_positions
    print("\nTesting get_common_positions()...")
    common_pos = aligner.get_common_positions(sample2)
    print(f"Common positions found: {len(common_pos)}")

    # Test align_sample_to_centroid
    print("\nTesting align_sample_to_centroid()...")
    sample_mC, sample_uC = aligner.align_sample_to_centroid(sample2)
    print(f"Aligned sample data points: {len(sample_mC)}")
    
    # Test load_extended_centroid
    print("\nTesting load_extended_centroid()...")
    # Create a new aligner to test loading
    aligner3 = PositionAligner(max_samples=10, use_gpu=False)
    aligner3.set_min_coverage(2)
    success_load = aligner3.load_extended_centroid(centroid)
    print(f"Centroid loaded: {success_load}")
    print(f"Loaded aligner sample count: {aligner3.sample_count}")
    
    # Demonstrate GPU optimization features
    print("\n" + "=" * 50)
    print("GPU Optimization Features Demo")
    print("=" * 50)
    
    # Check GPU memory info
    print("\nGPU Memory Information:")
    memory_info = aligner.get_gpu_memory_info()
    if memory_info.get("gpu_available", False):
        print(f"  GPU Memory Used: {memory_info['gpu_memory_used_gb']:.2f} GB")
        print(f"  GPU Memory Total: {memory_info['gpu_memory_total_gb']:.2f} GB")
        print(f"  Memory Utilization: {memory_info['memory_utilization_percent']:.1f}%")
        print(f"  Aligner Memory: {memory_info['aligner_memory_mb']:.1f} MB")
    else:
        print("  GPU not available")
    
    # Check optimization recommendations
    print("\nOptimization Analysis:")
    optimization = aligner.optimize_for_large_datasets()
    print(f"  Optimized: {optimization['optimized']}")
    print(f"  Total Positions: {optimization['total_positions']:,}")
    print(f"  GPU Available: {optimization['gpu_available']}")
    
    if optimization['recommendations']:
        print("  Recommendations:")
        for rec in optimization['recommendations']:
            print(f"    - {rec}")
    
    # Demonstrate memory cleanup
    print("\nGPU Memory Cleanup:")
    cleanup_success = aligner.cleanup_gpu_memory()
    print(f"  Cleanup successful: {cleanup_success}")
    
    print("\n" + "=" * 50)
    print("MethylSample Usage Complete!")
    print("=" * 50)
    
    print("The PositionAligner now uses MethylSample objects exclusively.")
    print("This provides better type safety, clearer API, and improved maintainability.")


if __name__ == "__main__":
    main()
