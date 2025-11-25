#!/usr/bin/env python3
"""
Test Centroid Creation from Real Sample Data
=============================================

Tests the creation of centroids from real methylation samples.
Expects sample files with the naming pattern {chrom}-{ctx}.h5 where:
- chrom: '1', '2', ..., '22', 'X', 'Y'
- ctx: 'CG', 'CHG', 'CHH'

The test loads real sample data, creates centroids by combining samples,
and saves the final centroids to HDF5.
"""

import numpy as np
import tempfile
import os
import sys
from pathlib import Path
from typing import List, Optional, Union

# Import MethylUtils components
try:
    import methyl_utils
    from methyl_utils import MethylSample
    METHYLUTILS_AVAILABLE = True
except ImportError as e:
    METHYLUTILS_AVAILABLE = False
    print(f"Error: MethylUtils not available: {e}")
    sys.exit(1)

# Import pytest only if available (for testing)
try:
    import pytest
except ImportError:
    pytest = None

import numpy as np
import pytest
from methyl_utils.core.methyl_frame import MethylExtendedCentroid, MethylSample

def test_centroid_creation():
    # Create samples
    pos = np.array([1, 2, 3], dtype=np.uint32)
    sample1 = MethylSample.from_sample_data(pos, np.array([10, 20, 30]), np.array([5, 15, 25]), np.array([0,0,0]))
    sample2 = MethylSample.from_sample_data(pos, np.array([15, 25, 35]), np.array([10, 20, 30]), np.array([0,0,0]))
    
    # Create centroid
    centroid = sample1.add_sample(sample2)
    
    assert centroid.is_extended_centroid
    assert np.all(centroid.N == 2)
    assert np.all(centroid.mC == (10+15)//2)  # Average, but actual implementation may vary


def create_temp_directory():
    """Create a temporary directory for output files."""
    temp_dir = tempfile.mkdtemp()
    return Path(temp_dir)


class TestCentroidCreation:
    """Test suite for creating centroids from real sample data."""

    if pytest:
        @pytest.fixture
        def temp_directory(self):
            """Create a temporary directory for output files."""
            with tempfile.TemporaryDirectory() as temp_dir:
                yield Path(temp_dir)

    def create_optimized_centroid_from_samples_list(self, sample_directories: List[Path],
                                                   output_directory: Optional[Path] = None,
                                                   chromosomes: Optional[List[str]] = None,
                                                   contexts: Optional[List[str]] = None) -> List[Path]:
        """
        Create centroids using an optimized approach that maintains chromosome-context granularity.

        This method creates separate centroids for each chromosome-context combination,
        following the same file structure as input samples ({chrom}-{ctx}.h5).
        This allows loading individual chromosome-context combinations and minimizes memory usage.

        Args:
            sample_directories: List of directories containing sample files
            output_directory: Directory to save centroids
            chromosomes: List of chromosomes to include
            contexts: List of contexts to include

        Returns:
            List of centroid paths (one per chromosome-context combination)
        """
        try:
            from methyl_utils.position_aligner import PositionAligner
        except ImportError:
            from ..methyl_utils.position_aligner import PositionAligner

        if not output_directory:
            output_directory = sample_directories[0]

        if chromosomes is None:
            chromosomes = [str(i) for i in range(1, 23)] + ['X', 'Y']
        if contexts is None:
            contexts = ['CG', 'CHG', 'CHH']

        print(f"Creating optimized centroids per chromosome-context from {len(sample_directories)} sample directories...")

        created_centroids = []

        try:
            # Process each chromosome-context combination separately
            for chrom in chromosomes:
                for ctx in contexts:
                    print(f"\n📊 Processing {chrom}-{ctx} (optimized)...")

                    # Create one PositionAligner per chromosome-context combination
                    aligner = PositionAligner(use_gpu=False)  # Start with CPU for stability
                    context_samples_processed = 0
                    first_sample = True

                    # Find all samples for this chromosome-context combination across all directories
                    for sample_dir in sample_directories:
                        if not sample_dir.exists():
                            continue

                        sample_name = sample_dir.name

                        # Check if this specific chromosome-context file exists
                        expected_filename = f"{chrom}-{ctx}.h5"
                        filepath = sample_dir / expected_filename
                        if filepath.exists():
                            try:
                                sample = MethylSample.load_from_h5(filepath)
                                if first_sample:
                                    # Initialize the aligner with the first sample
                                    print(f"  Initializing {chrom}-{ctx} aligner with {sample_name} ({len(sample.pos)} positions)")
                                    success = aligner.add_sample(sample, sample_index=0)
                                    if not success:
                                        print(f"  Failed to add first sample {sample_name}")
                                        continue
                                    first_sample = False
                                else:
                                    # Add subsequent samples directly to the existing aligner
                                    sample_index = context_samples_processed
                                    print(f"  Adding {sample_name} to {chrom}-{ctx} aligner (sample_index: {sample_index})")
                                    success = aligner.add_sample(sample, sample_index=sample_index)
                                    if not success:
                                        print(f"  Failed to add sample {sample_name}")
                                        continue

                                context_samples_processed += 1
                                print(f"  Loaded: {sample_name}/{expected_filename} ({len(sample.pos)} positions)")

                            except Exception as e:
                                print(f"  Warning: Failed to load {filepath}: {e}")

                    # Create final centroid from the aligner
                    if context_samples_processed > 0:
                        print(f"  Creating final centroid for {chrom}-{ctx}...")
                        context_centroid = aligner.get_centroid_sample()

                        # Save chromosome-context centroid with same naming as input
                        centroid_filename = f"{chrom}-{ctx}.h5"
                        centroid_filepath = output_directory / centroid_filename
                        self.save_centroid_to_h5(context_centroid, centroid_filepath)

                        print(f"✓ {chrom}-{ctx} centroid: {len(context_centroid.pos)} positions from {context_samples_processed} samples")
                        created_centroids.append(centroid_filepath)
                    else:
                        print(f"⚠️  No samples found for {chrom}-{ctx}")

            if not created_centroids:
                print("No centroids were created")
                return []

            print(f"\n🎉 Created {len(created_centroids)} optimized chromosome-context centroids")
            return created_centroids

        except Exception as e:
            print(f"❌ Failed to create centroids: {e}")
            import traceback
            traceback.print_exc()
            return []

    def find_sample_files(self, input_directory: Path, chromosomes: Optional[List[str]] = None,
                         contexts: Optional[List[str]] = None) -> List[Path]:
        """
        Find all sample files in the input directory matching the expected pattern.

        Args:
            input_directory: Directory containing sample files
            chromosomes: List of chromosomes to include (optional, includes all if None)
            contexts: List of contexts to include (optional, includes all if None)

        Returns:
            List of paths to sample files
        """
        if chromosomes is None:
            chromosomes = [str(i) for i in range(1, 23)] + ['X', 'Y']
        if contexts is None:
            contexts = ['CG', 'CHG', 'CHH']

        sample_files = []
        for chrom in chromosomes:
            for ctx in contexts:
                expected_filename = f"{chrom}-{ctx}.h5"
                filepath = input_directory / expected_filename
                if filepath.exists():
                    sample_files.append(filepath)

        return sorted(sample_files)

    def load_samples_from_directory(self, input_directory: Path,
                                  chromosomes: Optional[List[str]] = None,
                                  contexts: Optional[List[str]] = None) -> List[MethylSample]:
        """
        Load all valid sample files from a directory.

        Args:
            input_directory: Directory containing sample files
            chromosomes: List of chromosomes to include
            contexts: List of contexts to include

        Returns:
            List of loaded MethylSample objects

        Raises:
            FileNotFoundError: If no sample files are found
        """
        sample_files = self.find_sample_files(input_directory, chromosomes, contexts)

        if not sample_files:
            available_files = list(input_directory.glob("*.h5"))
            raise FileNotFoundError(
                f"No sample files found in {input_directory}. "
                f"Expected pattern: {{chrom}}-{{ctx}}.h5 where chrom in {chromosomes} and ctx in {contexts}. "
                f"Found files: {[f.name for f in available_files]}"
            )

        samples = []
        for filepath in sample_files:
            try:
                sample = MethylSample.load_from_h5(filepath)
                samples.append(sample)
                print(f"Loaded sample: {filepath.name} ({len(sample.pos)} positions)")
            except Exception as e:
                print(f"Warning: Failed to load {filepath}: {e}")
                continue

        if not samples:
            raise RuntimeError("No valid sample files could be loaded")

        return samples

    def save_centroid_to_h5(self, centroid: MethylSample, filepath: Path):
        """Save a centroid to HDF5 file."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        centroid.save_to_h5(filepath)
        print(f"Saved centroid to: {filepath}")

    def test_centroid_creation_from_real_samples(self, input_directory: Path, output_directory: Optional[Path] = None):
        """
        Test creating a centroid from real sample files in a directory.

        This test:
        1. Finds all sample files matching {chrom}-{ctx}.h5 pattern
        2. Loads the real samples from HDF5 files
        3. Creates a centroid using create_centroid_from_samples
        4. Saves the centroid and verifies it

        Args:
            input_directory: Directory containing sample files
            output_directory: Directory to save centroid (defaults to input_directory)
        """
        if output_directory is None:
            output_directory = input_directory

        print(f"Looking for sample files in: {input_directory}")

        # Load all samples from the directory
        try:
            samples = self.load_samples_from_directory(input_directory)
        except FileNotFoundError as e:
            print(f"Error: {e}")
            return None

        if not samples:
            print("No samples found to create centroid")
            return None

        print(f"Loaded {len(samples)} samples")

        # Create centroid from all samples using the class method
        print("Creating centroid from samples...")
        centroid = MethylSample.create_centroid_from_samples(samples, use_gpu=False)

        # Verify centroid properties
        assert centroid.is_centroid, "Result should be a centroid"
        assert centroid.N is not None, "Centroid should have N field (sample counts)"
        assert len(centroid.pos) > 0, "Centroid should have positions"

        # The centroid should have positions from all samples (aligned)
        total_input_positions = sum(len(s.pos) for s in samples)
        assert len(centroid.pos) <= total_input_positions, "Centroid positions should not exceed total input positions"

        # N field should reflect the number of samples contributing to each position
        assert np.all(centroid.N >= 1), "Each position should have at least one contributing sample"
        assert np.max(centroid.N) <= len(samples), "No position should have more samples than we provided"

        # Save the centroid
        centroid_filepath = output_directory / "centroid.h5"
        self.save_centroid_to_h5(centroid, centroid_filepath)

        # Verify centroid can be loaded back
        loaded_centroid = MethylSample.load_from_h5(centroid_filepath)
        assert loaded_centroid.is_centroid, "Loaded centroid should still be a centroid"
        assert np.array_equal(loaded_centroid.pos, centroid.pos), "Positions should match"
        assert np.array_equal(loaded_centroid.N, centroid.N), "Sample counts should match"

        print(f"✓ Successfully created centroid with {len(centroid.pos)} positions from {len(samples)} samples")
        return centroid_filepath

    def create_centroids_per_chromosome(self, sample_directories: List[Path],
                                       output_directory: Optional[Path] = None,
                                       chromosomes: Optional[List[str]] = None,
                                       contexts: Optional[List[str]] = None) -> List[Path]:
        """
        Create separate centroids for each chromosome by combining all contexts for that chromosome.

        This creates per-chromosome centroids where each chromosome combines CG, CHG, CHH contexts.
        Each chromosome should have ~85M positions total across all contexts.

        Args:
            sample_directories: List of directories containing sample files
            output_directory: Directory to save centroids
            chromosomes: List of chromosomes to include
            contexts: List of contexts to include

        Returns:
            List of paths to saved centroid files (one per chromosome)
        """
        if not output_directory:
            # Use the first sample directory as output if none specified
            output_directory = sample_directories[0]

        if chromosomes is None:
            chromosomes = [str(i) for i in range(1, 23)] + ['X', 'Y']

        print(f"Creating centroids per chromosome from {len(sample_directories)} sample directories...")

        created_centroids = []

        try:
            # Process each chromosome separately
            for chrom in chromosomes:
                print(f"\n📊 Processing chromosome {chrom}...")

                chrom_centroid = None
                chrom_samples_processed = 0

                # Find all samples for this chromosome across all directories
                for sample_dir in sample_directories:
                    if not sample_dir.exists():
                        continue

                    sample_name = sample_dir.name  # Extract sample name from directory

                    # Get samples for this specific chromosome from this sample directory
                    chrom_samples = []
                    for ctx in (contexts or ['CG', 'CHG', 'CHH']):
                        expected_filename = f"{chrom}-{ctx}.h5"
                        filepath = sample_dir / expected_filename
                        if filepath.exists():
                            try:
                                sample = MethylSample.load_from_h5(filepath)
                                chrom_samples.append((sample_name, filepath.name, sample))
                                print(f"  Loaded: {sample_name}/{filepath.name} ({len(sample.pos)} positions)")
                            except Exception as e:
                                print(f"  Warning: Failed to load {filepath}: {e}")

                    # Add samples for this chromosome from this sample directory
                    for sample_name, sample_file, sample in chrom_samples:
                        if chrom_centroid is None:
                            # First sample becomes the initial centroid for this chromosome
                            print(f"  Initializing chromosome {chrom} centroid with {sample_name} ({len(sample.pos)} positions)")
                            chrom_centroid = MethylSample.create_centroid_from_samples([sample], use_gpu=False)
                        else:
                            # Add subsequent samples to existing chromosome centroid
                            print(f"  Adding {sample_name} to chromosome {chrom} centroid (current: {len(chrom_centroid.pos)} positions, adding: {len(sample.pos)} positions)")
                            # Note: add_sample can be slow due to array copying for 85M+ positions
                            chrom_centroid = chrom_centroid.add_sample(sample, use_gpu=False)

                    chrom_samples_processed += 1

                # Save chromosome centroid
                if chrom_centroid is not None and chrom_samples_processed > 0:
                    centroid_filename = f"{chrom}.h5"
                    centroid_filepath = output_directory / centroid_filename
                    self.save_centroid_to_h5(chrom_centroid, centroid_filepath)

                    print(f"✓ Chromosome {chrom} centroid: {len(chrom_centroid.pos)} positions from {chrom_samples_processed} samples")
                    created_centroids.append(centroid_filepath)
                else:
                    print(f"⚠️  No samples found for chromosome {chrom}")

            if not created_centroids:
                print("No centroids were created")
                return []

            print(f"\n🎉 Created {len(created_centroids)} chromosome centroids")
            return created_centroids

        except Exception as e:
            print(f"❌ Failed to create centroids: {e}")
            import traceback
            traceback.print_exc()
            return []

    def create_centroids_from_samples_list(self, sample_directories: List[Path],
                                          output_directory: Optional[Path] = None,
                                          chromosomes: Optional[List[str]] = None,
                                          contexts: Optional[List[str]] = None) -> List[Path]:
        """
        Create centroids from all sample files across multiple directories.

        Always creates per-chromosome centroids to maintain chromosome isolation.

        Args:
            sample_directories: List of directories containing sample files
            output_directory: Directory to save centroids
            chromosomes: List of chromosomes to include
            contexts: List of contexts to include

        Returns:
            List of centroid paths (one per chromosome)
        """
        return self.create_centroids_per_chromosome(sample_directories, output_directory, chromosomes, contexts)



def main():
    """Main function for command-line execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Create centroids from methylation sample files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create chromosome centroids from hardcoded sample list (when no args provided)
  python test_centroid_creation.py

  # Create chromosome centroids from all samples in current directory
  python test_centroid_creation.py .

  # Create chromosome centroids from multiple sample directories
  python test_centroid_creation.py /path/to/samples1 /path/to/samples2 /path/to/samples3

  # Create chromosome centroids from samples in input_dir, save to output_dir
  python test_centroid_creation.py /path/to/samples -o /path/to/output

  # Create centroids from specific chromosomes and contexts
  python test_centroid_creation.py /path/to/samples -c 1 2 X --contexts CG CHG

  # Test mode (create mock samples first, then create chromosome centroids)
  python test_centroid_creation.py --test-mode
        """
    )

    parser.add_argument(
        'input_directories',
        nargs='*',
        type=str,
        help='Directories containing sample files (default: current directory, or use hardcoded list if no args provided)'
    )

    parser.add_argument(
        '-o', '--output-directory',
        type=str,
        help='Directory to save centroid (default: same as input)'
    )

    parser.add_argument(
        '-c', '--chromosomes',
        nargs='+',
        help='Chromosomes to include (default: all)'
    )

    parser.add_argument(
        '--contexts',
        nargs='+',
        default=['CG', 'CHG', 'CHH'],
        help='Contexts to include (default: CG CHG CHH)'
    )

    parser.add_argument(
        '--test-mode',
        action='store_true',
        help='Create mock samples for testing, then create centroid'
    )



    args = parser.parse_args()

    # Set default input directories
    if not args.input_directories:
        if args.test_mode:
            # For test mode, we'll create a temp directory
            pass
        else:
            args.input_directories = ["."]

    # Create test instance
    test_instance = TestCentroidCreation()

    try:
        if args.test_mode:
            # Test mode: create mock samples and then create centroid
            print("🧪 Running in test mode (creating mock samples)...")

            temp_path = create_temp_directory()

            # Create some mock samples for testing with overlapping positions
            print("Creating mock samples with overlapping genomic positions...")
            mock_chroms = ['1', '2', 'X'] if not args.chromosomes else args.chromosomes
            mock_contexts = args.contexts

            # Generate mock data with overlapping positions (simulating real genomic data)
            for chrom in mock_chroms:
                # Create base positions for this chromosome (representing all possible CpG sites)
                np.random.seed(hash(f"base_{chrom}") % 2**32)
                base_positions = np.sort(np.random.randint(1, 1000000, 800, dtype=np.uint32))
                base_positions = np.unique(base_positions)  # Ensure unique

                for ctx in mock_contexts:
                    # Each context samples from the base positions with some overlap
                    # This simulates how CG, CHG, CHH contexts share many positions but have different coverage
                    np.random.seed(hash(f"{chrom}-{ctx}") % 2**32)
                    n_positions = np.random.randint(600, 800)  # Most positions covered
                    keep_indices = np.random.choice(len(base_positions), size=n_positions, replace=False)
                    pos = base_positions[keep_indices]
                    pos = np.sort(pos)  # Ensure sorted

                    total_reads = np.random.randint(10, 100, n_positions, dtype=np.uint32)
                    methylation_levels = np.random.beta(2, 2, n_positions)
                    mC = np.round(total_reads * methylation_levels).astype(np.uint32)
                    uC = (total_reads - mC).astype(np.uint32)
                    tnc = np.random.randint(0, 32, n_positions, dtype=np.uint8)

                    # Create and save sample
                    sample = MethylSample.from_sample_data(pos, mC, uC, tnc)
                    filepath = temp_path / f"{chrom}-{ctx}.h5"
                    sample.save_to_h5(filepath)
                    print(f"  Created: {filepath.name} ({len(pos)} positions)")

            # Now create centroid from the mock samples
            output_dir = Path(args.output_directory) if args.output_directory else temp_path
            # Use optimized approach (always better for large datasets)
            centroid_paths = test_instance.create_optimized_centroid_from_samples_list(
                [temp_path], output_dir, mock_chroms, mock_contexts
            )

            if centroid_paths:
                print(f"\n🎉 Test mode completed! Created {len(centroid_paths)} chromosome centroids:")
                for path in centroid_paths:
                    print(f"  {path}")
            else:
                print("\n❌ Test mode failed!")
                sys.exit(1)

        else:
            # Check if using hardcoded sample list or command line arguments
            if len(args.input_directories) == 1 and args.input_directories[0] == "." and not args.output_directory:
                # Use hardcoded sample list
                centroid_samples = [
                    # "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/HBCST-042525-95676",
                    # "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/HBCST-042825-39553",
                    # "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/HBCST-042925-105788",
                    # "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/HBCST-051325-25543",
                    # "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/HBCST-051425-74294",
                    # "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/HBCST-052125-32336",
                    # "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/HBCST-052125-87293",
                    # "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/HBCST-052225-74758",
                    # "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/HBCST-060425-107956",
                    # "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/HBCST-060625-104673",
                    # "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/HBCST-060925-66247",
                    # "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/HBCST-061125-42608",
                    # "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/HBCST-061825-52197",
                    # "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/HBCST-063025-77476",
                    # "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/HBCST-071625-48267"
                    "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/DBCST-051425-111148",
                    "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/DBCST-060525-111386",
                    "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/DBCST-060525-111387",
                    "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/DBCST-060625-111394",
                    "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/DBCST-061025-111424",
                    "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/DBCST-061025-111427",
                    "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/DBCST-061325-111495",
                    "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/DBCST-062725-111661",
                    "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/DBCST-063025-111652",
                    "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/DBCST-071025-111803",
                    "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/DBCST-071025-111804",
                    "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/DBCST-071025-111805",
                    "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/DBCST-071025-111806",
                    "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/DBCST-071025-111807",
                    "/home/ubuntu/Work/samples/humans/psomagen/old.data.AN00025834/DBCST-071125-111814"
                ]               
                centroid_dir = "/home/ubuntu/Work/w/humans/psomagen/pc/centroids/c"

                sample_dirs = [Path(sample) for sample in centroid_samples]
                output_dir = Path(centroid_dir)
            else:
                # Use command line arguments
                sample_dirs = [Path(d) for d in args.input_directories]
                output_dir = Path(args.output_directory) if args.output_directory else None

                # Validate input directories
                for input_dir in sample_dirs:
                    if not input_dir.exists():
                        print(f"❌ Input directory does not exist: {input_dir}")
                        sys.exit(1)

            print(f"📁 Processing {len(sample_dirs)} sample directories")
            if output_dir:
                print(f"💾 Saving centroid to: {output_dir}")

            # Use optimized approach (always better for large datasets)
            centroid_paths = test_instance.create_optimized_centroid_from_samples_list(
                sample_dirs,
                output_dir,
                args.chromosomes,
                args.contexts
            )

            if centroid_paths:
                print(f"\n🎉 Created {len(centroid_paths)} chromosome centroids:")
                for path in centroid_paths:
                    print(f"  {path}")
            else:
                print("\n❌ Failed to create chromosome centroids!")
                sys.exit(1)

    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
