#!/usr/bin/env python3
"""
Tests for extended centroid functionality with methylation level statistics.
"""

import pytest
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


class TestExtendedCentroid:
    """Test extended centroid functionality."""
    
    def test_basic_vs_extended_centroid(self):
        """Test that extended centroids include additional columns."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create sample files
            sample1_file = temp_path / "sample1" / "1-CG.h5"
            sample1_file.parent.mkdir(exist_ok=True)
            positions1 = np.array([1000, 2000], dtype=np.uint32)
            mC1 = np.array([10, 20], dtype=np.uint32)
            uC1 = np.array([5, 15], dtype=np.uint32)
            tnc1 = np.array([1, 2], dtype=np.uint8)
            create_sample_file(sample1_file, positions1, mC1, uC1, tnc1)
            
            sample2_file = temp_path / "sample2" / "1-CG.h5"
            sample2_file.parent.mkdir(exist_ok=True)
            positions2 = np.array([1500, 2000], dtype=np.uint32)
            mC2 = np.array([15, 25], dtype=np.uint32)
            uC2 = np.array([8, 18], dtype=np.uint32)
            tnc2 = np.array([2, 3], dtype=np.uint8)
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
            
            # Build basic centroid
            basic_centroid_path = methyl_centroid.calculate_centroid(str(output_dir), extended=False)
            
            # Check basic centroid columns
            with h5py.File(basic_centroid_path, "r") as f:
                data = f["methylation_data"]
                basic_columns = list(data.keys())
                assert "pos" in basic_columns
                assert "mC" in basic_columns
                assert "uC" in basic_columns
                assert "tnc" in basic_columns
                assert "N" in basic_columns
                assert "Sx" not in basic_columns
                assert "Sx2" not in basic_columns
            
            # Reset for extended centroid
            methyl_centroid.position_aligner.reset()
            methyl_centroid.active_samples.clear()
            
            # Build extended centroid
            extended_centroid_path = methyl_centroid.calculate_centroid(str(output_dir), extended=True)
            
            # Check extended centroid columns
            with h5py.File(extended_centroid_path, "r") as f:
                data = f["methylation_data"]
                extended_columns = list(data.keys())
                assert "pos" in extended_columns
                assert "mC" in extended_columns
                assert "uC" in extended_columns
                assert "tnc" in extended_columns
                assert "N" in extended_columns
                assert "Sx" in extended_columns
                assert "Sx2" in extended_columns
    
    def test_extended_centroid_calculations(self):
        """Test that Sx and Sx2 calculations are correct."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create sample files with known values
            sample1_file = temp_path / "sample1" / "1-CG.h5"
            sample1_file.parent.mkdir(exist_ok=True)
            positions1 = np.array([1000, 2000], dtype=np.uint32)
            mC1 = np.array([10, 20], dtype=np.uint32)
            uC1 = np.array([5, 15], dtype=np.uint32)
            tnc1 = np.array([1, 2], dtype=np.uint8)
            create_sample_file(sample1_file, positions1, mC1, uC1, tnc1)
            
            sample2_file = temp_path / "sample2" / "1-CG.h5"
            sample2_file.parent.mkdir(exist_ok=True)
            positions2 = np.array([1500, 2000], dtype=np.uint32)
            mC2 = np.array([15, 25], dtype=np.uint32)
            uC2 = np.array([8, 18], dtype=np.uint32)
            tnc2 = np.array([2, 3], dtype=np.uint8)
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
            
            # Build extended centroid
            extended_centroid_path = methyl_centroid.calculate_centroid(str(output_dir), extended=True)
            
            # Check calculations
            with h5py.File(extended_centroid_path, "r") as f:
                data = f["methylation_data"]
                
                # For position 2000, we have data from both samples
                pos_2000_idx = np.where(data['pos'][:] == 2000)[0][0]
                
                mC_2000 = data['mC'][pos_2000_idx]
                uC_2000 = data['uC'][pos_2000_idx]
                N_2000 = data['N'][pos_2000_idx]
                Sx_2000 = data['Sx'][pos_2000_idx]
                Sx2_2000 = data['Sx2'][pos_2000_idx]
                
                # Expected values:
                # Sample 1: mC=20, uC=15, methylation_level = 20/(20+15) = 0.571
                # Sample 2: mC=25, uC=18, methylation_level = 25/(25+18) = 0.581
                # Sx should be the sum of individual methylation levels: 0.571 + 0.581 = 1.152
                # Sx2 should be the sum of squared methylation levels: 0.571^2 + 0.581^2 = 0.326 + 0.338 = 0.664
                expected_Sx = (20 / (20 + 15)) + (25 / (25 + 18))  # Sum of individual methylation levels
                expected_Sx2 = (20 / (20 + 15)) ** 2 + (25 / (25 + 18)) ** 2  # Sum of squared methylation levels
                
                assert N_2000 == 2
                assert abs(Sx_2000 - expected_Sx) < 1e-6
                assert abs(Sx2_2000 - expected_Sx2) < 1e-6
    
    def test_incremental_operations(self):
        """Test adding and removing samples from extended centroids."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create initial sample files
            sample1_file = temp_path / "sample1" / "1-CG.h5"
            sample1_file.parent.mkdir(exist_ok=True)
            positions1 = np.array([1000, 2000], dtype=np.uint32)
            mC1 = np.array([10, 20], dtype=np.uint32)
            uC1 = np.array([5, 15], dtype=np.uint32)
            tnc1 = np.array([1, 2], dtype=np.uint8)
            create_sample_file(sample1_file, positions1, mC1, uC1, tnc1)
            
            sample2_file = temp_path / "sample2" / "1-CG.h5"
            sample2_file.parent.mkdir(exist_ok=True)
            positions2 = np.array([2000, 3000], dtype=np.uint32)
            mC2 = np.array([15, 25], dtype=np.uint32)
            uC2 = np.array([8, 18], dtype=np.uint32)
            tnc2 = np.array([2, 3], dtype=np.uint8)
            create_sample_file(sample2_file, positions2, mC2, uC2, tnc2)
            
            # Create new sample for incremental addition
            sample3_file = temp_path / "sample3" / "1-CG.h5"
            sample3_file.parent.mkdir(exist_ok=True)
            positions3 = np.array([1500, 2000], dtype=np.uint32)
            mC3 = np.array([12, 22], dtype=np.uint32)
            uC3 = np.array([6, 16], dtype=np.uint32)
            tnc3 = np.array([3, 4], dtype=np.uint8)
            create_sample_file(sample3_file, positions3, mC3, uC3, tnc3)
            
            # Create output directory
            output_dir = temp_path / "output"
            output_dir.mkdir(exist_ok=True)
            
            # Initialize MethylCentroid
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
            
            # Build initial centroid
            for i in range(len(original_samples)):
                methyl_centroid.add_sample(i, is_new_sample=False)
            
            initial_centroid_path = methyl_centroid.save_centroid(str(output_dir), extended=True)
            
            # Check initial N values
            with h5py.File(initial_centroid_path, "r") as f:
                data = f["methylation_data"]
                pos_2000_idx = np.where(data['pos'][:] == 2000)[0][0]
                assert data['N'][pos_2000_idx] == 2  # Both samples have position 2000
            
            # Add new sample
            methyl_centroid.add_sample(0, is_new_sample=True)
            updated_centroid_path = methyl_centroid.save_centroid(str(output_dir), extended=True)
            
            # Check updated N values
            with h5py.File(updated_centroid_path, "r") as f:
                data = f["methylation_data"]
                pos_2000_idx = np.where(data['pos'][:] == 2000)[0][0]
                assert data['N'][pos_2000_idx] == 3  # All three samples have position 2000
            
            # Remove new sample
            methyl_centroid.remove_sample(0, is_new_sample=True)
            final_centroid_path = methyl_centroid.save_centroid(str(output_dir), extended=True)
            
            # Check final N values (should be back to initial)
            with h5py.File(final_centroid_path, "r") as f:
                data = f["methylation_data"]
                pos_2000_idx = np.where(data['pos'][:] == 2000)[0][0]
                assert data['N'][pos_2000_idx] == 2  # Back to 2 samples
    
    def test_build_extended_centroid(self):
        """Test the build_extended_centroid method."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create multiple sample files
            sample_files = []
            for i in range(3):
                sample_file = temp_path / f"sample{i+1}" / "1-CG.h5"
                sample_file.parent.mkdir(exist_ok=True)
                
                positions = np.array([1000, 2000], dtype=np.uint32)
                mC = np.array([10 + i, 20 + i], dtype=np.uint32)
                uC = np.array([5 + i, 15 + i], dtype=np.uint32)
                tnc = np.array([1, 2], dtype=np.uint8)
                
                create_sample_file(sample_file, positions, mC, uC, tnc)
                sample_files.append(str(sample_file.parent))
            
            # Create output directory
            output_dir = temp_path / "output"
            output_dir.mkdir(exist_ok=True)
            
            # Initialize MethylCentroid
            methyl_centroid = MethylCentroid(
                samples=sample_files,
                chrom="1",
                ctx="CG",
                output_dir=output_dir,
                output_dir=output_dir,
                min_coverage=4,
            )
            
            # Build extended centroid
            results = methyl_centroid.build_centroid()

            # Check results
            assert results.final_centroid_path is not None
            assert Path(results.final_centroid_path).exists()
            
            # Check final centroid has extended data
            with h5py.File(results.final_centroid_path, "r") as f:
                data = f["methylation_data"]
                assert "Sx" in data
                assert "Sx2" in data
                assert len(data['pos']) > 0


    
    def test_position_aligner_extended_methods(self):
        """Test the new PositionAligner methods for extended centroids."""
        from genomic_position_aligner import PositionAligner
        
        # Create a simple position aligner
        aligner = PositionAligner(max_samples=2, use_gpu=False)
        aligner.set_min_coverage(1)
        
        # Add sample data
        positions = np.array([1000, 2000], dtype=np.uint32)
        mC = np.array([10, 20], dtype=np.uint32)
        uC = np.array([5, 15], dtype=np.uint32)
        tnc = np.array([1, 2], dtype=np.uint8)
        
        success = aligner.add_sample_data(positions, mC, uC, tnc, sample_index=0)
        assert success
        
        # Test get_centroid_sample for extended data
        centroid_sample = aligner.get_centroid_sample()

        assert centroid_sample is not None
        assert len(centroid_sample.pos) == 2
        assert len(centroid_sample.Sx) == 2
        assert len(centroid_sample.Sx2) == 2

        # Verify calculations
        expected_methylation_1000 = 10 / (10 + 5)  # 0.667
        expected_methylation_2000 = 20 / (20 + 15)  # 0.571

        assert abs(centroid_sample.Sx[0] - expected_methylation_1000) < 1e-6
        assert abs(centroid_sample.Sx[1] - expected_methylation_2000) < 1e-6
        assert abs(centroid_sample.Sx2[0] - (expected_methylation_1000 ** 2)) < 1e-6
        assert abs(centroid_sample.Sx2[1] - (expected_methylation_2000 ** 2)) < 1e-6


def test_basic_import():
    """Test that MethylCentroid can be imported and basic functionality works."""
    from methyl_centroid.methyl_centroid import MethylCentroid
    from methyl_utils import is_gpu_available

    # Test basic instantiation
    mc = MethylCentroid(
        samples=["dummy"],
        chrom="1",
        ctx="CG",
        output_dir="/tmp",
        verbose=True
    )

    # Test that components are initialized
    assert mc.memory_manager is not None
    assert mc.performance_profiler is not None
    assert mc.chunked_processor is not None
    assert mc.logger is not None

    # Test GPU detection integration
    gpu_available = is_gpu_available()
    assert isinstance(gpu_available, bool)

    print("✅ Basic import and initialization test passed")


if __name__ == "__main__":
    # Run basic functionality test first
    test_basic_import()

    # Then run pytest if available
    try:
        pytest.main([__file__, "-v"])
    except NameError:
        print("⚠️  pytest not available, but basic import test passed") 