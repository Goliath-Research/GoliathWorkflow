#!/usr/bin/env python3
"""
Example demonstrating extended centroid functionality with methylation level statistics.

This example shows how to build extended centroid files that include additional
columns: N (sample count), Sx (methylation level sum), and Sx2 (squared methylation level sum).
"""

import numpy as np
import h5py
from pathlib import Path
import tempfile

from methyl_centroid.methyl_centroid import MethylCentroid


def create_sample_file(filepath: Path, positions: np.ndarray, mC: np.ndarray, 
                      uC: np.ndarray, tnc: np.ndarray):
    """Create a sample HDF5 file for testing."""
    with h5py.File(filepath, "w") as f:
        data_group = f.create_group("methylation_data")
        data_group.create_dataset("pos", data=positions, dtype=np.uint32)
        data_group.create_dataset("mC", data=mC, dtype=np.uint32)
        data_group.create_dataset("uC", data=uC, dtype=np.uint32)
        data_group.create_dataset("tnc", data=tnc, dtype=np.uint8)


def demonstrate_basic_vs_extended_centroid():
    """Demonstrate the difference between basic and extended centroids."""
    print("=== Basic vs Extended Centroid Demonstration ===")
    
    # Create temporary directory for sample files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create sample files
        sample1_file = temp_path / "sample1" / "1-CG.h5"
        sample1_file.parent.mkdir(exist_ok=True)
        positions1 = np.array([1000, 2000, 3000, 4000], dtype=np.uint32)
        mC1 = np.array([10, 20, 30, 40], dtype=np.uint32)
        uC1 = np.array([5, 15, 25, 35], dtype=np.uint32)
        tnc1 = np.array([1, 2, 3, 4], dtype=np.uint8)
        create_sample_file(sample1_file, positions1, mC1, uC1, tnc1)
        
        sample2_file = temp_path / "sample2" / "1-CG.h5"
        sample2_file.parent.mkdir(exist_ok=True)
        positions2 = np.array([1500, 2000, 2500, 3000], dtype=np.uint32)
        mC2 = np.array([15, 25, 35, 45], dtype=np.uint32)
        uC2 = np.array([8, 18, 28, 38], dtype=np.uint32)
        tnc2 = np.array([2, 3, 4, 5], dtype=np.uint8)
        create_sample_file(sample2_file, positions2, mC2, uC2, tnc2)
        
        # Create output directory
        output_dir = temp_path / "output"
        output_dir.mkdir(exist_ok=True)
        
        # Initialize MethylCentroid
        samples = [str(sample1_file.parent), str(sample2_file.parent)]
        methyl_centroid = MethylCentroid(
            samples=samples,
            chrom="1",
            ctx="CG",
            output_dir=output_dir,
            min_coverage=4
        )
        
        print("1. Building Basic Centroid:")
        basic_centroid_path = methyl_centroid.calculate_centroid(str(output_dir), extended=False)
        print(f"   Basic centroid saved to: {basic_centroid_path}")
        
        # Examine basic centroid
        with h5py.File(basic_centroid_path, "r") as f:
            data = f["methylation_data"]
            print(f"   Basic centroid columns: {list(data.keys())}")
            print(f"   Number of positions: {len(data['pos'])}")
            print(f"   Positions: {data['pos'][:]}")
            print(f"   mC values: {data['mC'][:]}")
            print(f"   uC values: {data['uC'][:]}")
            print(f"   N values: {data['N'][:]}")
        
        print("\n2. Building Extended Centroid:")
        # Reset for extended centroid
        methyl_centroid.position_aligner.reset()
        methyl_centroid.active_samples.clear()
        
        extended_centroid_path = methyl_centroid.calculate_centroid(str(output_dir), extended=True)
        print(f"   Extended centroid saved to: {extended_centroid_path}")
        
        # Examine extended centroid
        with h5py.File(extended_centroid_path, "r") as f:
            data = f["methylation_data"]
            print(f"   Extended centroid columns: {list(data.keys())}")
            print(f"   Number of positions: {len(data['pos'])}")
            print(f"   Positions: {data['pos'][:]}")
            print(f"   mC values: {data['mC'][:]}")
            print(f"   uC values: {data['uC'][:]}")
            print(f"   N values: {data['N'][:]}")
            print(f"   Sx values: {data['Sx'][:]}")
            print(f"   Sx2 values: {data['Sx2'][:]}")
            
            # Verify calculations
            print("\n3. Verification of Extended Data:")
            for i in range(len(data['pos'])):
                pos = data['pos'][i]
                mC = data['mC'][i]
                uC = data['uC'][i]
                N = data['N'][i]
                Sx = data['Sx'][i]
                Sx2 = data['Sx2'][i]
                
                # Calculate expected methylation level
                total_coverage = mC + uC
                if total_coverage > 0:
                    expected_methylation = mC / total_coverage
                    expected_Sx = expected_methylation * N
                    expected_Sx2 = (expected_methylation ** 2) * N
                    
                    print(f"   Position {pos}:")
                    print(f"     - mC={mC}, uC={uC}, N={N}")
                    print(f"     - Methylation level: {expected_methylation:.3f}")
                    print(f"     - Sx: expected={expected_Sx:.3f}, actual={Sx:.3f}")
                    print(f"     - Sx2: expected={expected_Sx2:.3f}, actual={Sx2:.3f}")


def demonstrate_incremental_operations():
    """Demonstrate adding and removing samples from an existing extended centroid."""
    print("\n=== Incremental Operations Demonstration ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create initial sample files
        sample1_file = temp_path / "sample1" / "1-CG.h5"
        sample1_file.parent.mkdir(exist_ok=True)
        positions1 = np.array([1000, 2000, 3000], dtype=np.uint32)
        mC1 = np.array([10, 20, 30], dtype=np.uint32)
        uC1 = np.array([5, 15, 25], dtype=np.uint32)
        tnc1 = np.array([1, 2, 3], dtype=np.uint8)
        create_sample_file(sample1_file, positions1, mC1, uC1, tnc1)
        
        sample2_file = temp_path / "sample2" / "1-CG.h5"
        sample2_file.parent.mkdir(exist_ok=True)
        positions2 = np.array([2000, 3000, 4000], dtype=np.uint32)
        mC2 = np.array([15, 25, 35], dtype=np.uint32)
        uC2 = np.array([8, 18, 28], dtype=np.uint32)
        tnc2 = np.array([2, 3, 4], dtype=np.uint8)
        create_sample_file(sample2_file, positions2, mC2, uC2, tnc2)
        
        # Create new sample for incremental addition
        sample3_file = temp_path / "sample3" / "1-CG.h5"
        sample3_file.parent.mkdir(exist_ok=True)
        positions3 = np.array([1500, 2000, 2500], dtype=np.uint32)
        mC3 = np.array([12, 22, 32], dtype=np.uint32)
        uC3 = np.array([6, 16, 26], dtype=np.uint32)
        tnc3 = np.array([3, 4, 5], dtype=np.uint8)
        create_sample_file(sample3_file, positions3, mC3, uC3, tnc3)
        
        # Create output directory
        output_dir = temp_path / "output"
        output_dir.mkdir(exist_ok=True)
        
        # Initialize MethylCentroid with original samples
        original_samples = [str(sample1_file.parent), str(sample2_file.parent)]
        new_samples = [str(sample3_file.parent)]
        
        methyl_centroid = MethylCentroid(
            samples=original_samples,
            chrom="1",
            ctx="CG",
            output_dir=output_dir,
            new_samples=new_samples,
            min_coverage=4
        )
        
        print("1. Building Initial Extended Centroid:")
        # Build initial centroid with original samples
        for i in range(len(original_samples)):
            methyl_centroid.add_sample(i, is_new_sample=False)
        
        initial_centroid_path = methyl_centroid.save_centroid(str(output_dir), extended=True)
        print(f"   Initial centroid saved to: {initial_centroid_path}")
        
        # Examine initial centroid
        with h5py.File(initial_centroid_path, "r") as f:
            data = f["methylation_data"]
            print(f"   Initial positions: {data['pos'][:]}")
            print(f"   Initial N values: {data['N'][:]}")
        
        print("\n2. Adding New Sample Incrementally:")
        # Add new sample
        methyl_centroid.add_sample(0, is_new_sample=True)
        
        updated_centroid_path = methyl_centroid.save_centroid(str(output_dir), extended=True)
        print(f"   Updated centroid saved to: {updated_centroid_path}")
        
        # Examine updated centroid
        with h5py.File(updated_centroid_path, "r") as f:
            data = f["methylation_data"]
            print(f"   Updated positions: {data['pos'][:]}")
            print(f"   Updated N values: {data['N'][:]}")
            print(f"   Updated Sx values: {data['Sx'][:]}")
        
        print("\n3. Removing Sample Incrementally:")
        # Remove the new sample
        methyl_centroid.remove_sample(0, is_new_sample=True)
        
        final_centroid_path = methyl_centroid.save_centroid(str(output_dir), extended=True)
        print(f"   Final centroid saved to: {final_centroid_path}")
        
        # Verify we're back to the initial state
        with h5py.File(final_centroid_path, "r") as f:
            data = f["methylation_data"]
            print(f"   Final positions: {data['pos'][:]}")
            print(f"   Final N values: {data['N'][:]}")





def main():
    """Run the extended centroid demonstration."""
    print("MethylCentroid - Extended Centroid Example")
    print("=" * 60)
    
    try:
        # Demonstrate basic vs extended centroids
        demonstrate_basic_vs_extended_centroid()
        
        # Demonstrate incremental operations
        demonstrate_incremental_operations()
        

        
        print("\n" + "=" * 60)
        print("Extended centroid demonstration completed successfully!")
        print("Key features demonstrated:")
        print("- Extended centroid files with N, Sx, Sx2 columns")
        print("- Incremental sample addition and removal")

        print("- Verification of methylation level calculations")
        
    except Exception as e:
        print(f"Error during demonstration: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 