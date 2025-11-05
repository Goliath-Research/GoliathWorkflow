"""
Data loading functionality for MethylClassifier
"""

from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import numpy as np
from collections import defaultdict


class DataLoader:
    """
    Data loader for methylation samples.
    
    Handles loading samples from various sources and formats.
    """

    @staticmethod
    def load_sample(h5_path: Path, debug: bool = False):
        """
        Load a single methylation sample from file.

        Args:
            h5_path: Path to the sample file
            debug: Enable debug output

        Returns:
            MethylSample instance
        """
        from methyl_utils import MethylSample

        if h5_path.suffix.lower() == '.h5':
            return MethylSample.load_from_h5(h5_path, debug=debug)
        else:
            raise ValueError(f"Unsupported file format: {h5_path.suffix}")

    @staticmethod
    def load_samples_from_directory(h5_dir: Path,
                                 chrom: str = None,
                                 context: str = None,
                                 debug: bool = False) -> List[Tuple[str, Any]]:
        """
        Load all methylation samples from a directory.

        Args:
            h5_dir: Directory containing sample files
            chrom: Optional chromosome filter
            context: Optional context filter
            debug: Enable debug output

        Returns:
            List of (sample_name, sample) tuples
        """
        from methyl_utils import MethylSample
        
        samples = []
        all_h5_files = list(h5_dir.rglob("*.h5"))

        if not all_h5_files:
            raise FileNotFoundError(f"No .h5 files found in {h5_dir} or its subdirectories")

        # Filter by chromosome and context if specified
        if chrom and context:
            h5_files = DataLoader._filter_h5_files_by_chrom_context(all_h5_files, chrom, context)
            print(f"Found {len(all_h5_files)} total .h5 files, {len(h5_files)} match {chrom}-{context}")
        else:
            h5_files = all_h5_files
            print(f"Found {len(h5_files)} .h5 files")

        if not h5_files:
            filter_msg = f" matching {chrom}-{context}" if chrom and context else ""
            raise FileNotFoundError(f"No .h5 files{filter_msg} found in {h5_dir} or its subdirectories")

        for h5_file in sorted(h5_files):
            try:
                sample = DataLoader.load_sample(h5_file, debug=debug)
                sample_name = h5_file.parent.name  # Use parent directory name as sample identifier

                # Collect statistical information for enhanced analysis
                coverage = sample.get_coverage()
                avg_coverage = np.mean(coverage) if len(coverage) > 0 else 0

                samples.append((sample_name, sample))

                # Provide more informative loading message
                print(f"    ✅ Loaded {sample_name} ({sample.sample_type}, avg coverage: {avg_coverage:.1f})")

            except Exception as e:
                sample_name = h5_file.parent.name
                print(f"    ❌ Failed to load {sample_name}: {e}")

        return samples

    @staticmethod
    def _filter_h5_files_by_chrom_context(h5_files: List[Path], chrom: str, context: str) -> List[Path]:
        """
        Filter .h5 files to only include those matching the specified chromosome and context.
        Expects files to be named {prefix}-{chrom}-{context}.h5 (exact chromosome match).
        """
        expected_pattern = f"{chrom}-{context}.h5"
        filtered_files = []

        for h5_file in h5_files:
            # Check if filename exactly matches the pattern
            # This prevents "11-CG.h5" from matching when chrom="1"
            if h5_file.name == expected_pattern:
                filtered_files.append(h5_file)

        return filtered_files

    @staticmethod
    def load_sample_from_directory(
        sample_dir: Path,
        chromosomes: Optional[List[str]] = None,
        debug: bool = False,
        required_chromosomes: Optional[List[str]] = None,
        positions: Optional[np.ndarray] = None,
        dmp_positions_by_chrom: Optional[Dict[str, np.ndarray]] = None
    ) -> Dict[str, Any]:
        """
        Load a sample from a directory, merging CG, CHG, and CHH contexts.
        
        Each sample directory should contain files named {chrom}-CG.h5, {chrom}-CHG.h5, {chrom}-CHH.h5
        for each chromosome. The contexts are merged per chromosome using MethylSample.merge_contexts().
        
        Args:
            sample_dir: Directory containing {chrom}-{context}.h5 files
            chromosomes: Optional list of chromosomes to load. If None, auto-detect from files.
        
        Returns:
            Dictionary mapping chromosome to merged MethylSample (all contexts combined)
        """
        from methyl_utils import MethylSample
        
        sample_dir = Path(sample_dir)
        
        # Find all chromosome-context files
        h5_files = list(sample_dir.glob("*-CG.h5")) + list(sample_dir.glob("*-CHG.h5")) + list(sample_dir.glob("*-CHH.h5"))
        
        if not h5_files:
            raise FileNotFoundError(f"No .h5 files found in {sample_dir}")
        
        # Group files by chromosome
        chrom_files: Dict[str, Dict[str, Path]] = defaultdict(dict)
        
        for h5_file in h5_files:
            # Extract chromosome from filename (e.g., "1-CG.h5" -> chrom="1", context="CG")
            parts = h5_file.stem.split('-')
            if len(parts) >= 2:
                chrom = parts[0]
                context = parts[-1]  # Last part is context
                if context in ['CG', 'CHG', 'CHH']:
                    chrom_files[chrom][context] = h5_file
        
        # Filter chromosomes if specified
        if chromosomes:
            chrom_files = {chrom: files for chrom, files in chrom_files.items() if chrom in chromosomes}

        # Filter to required chromosomes if specified (for performance optimization)
        if required_chromosomes:
            chrom_files = {chrom: files for chrom, files in chrom_files.items() if chrom in required_chromosomes}

        if not chrom_files:
            raise FileNotFoundError(f"No valid chromosome files found in {sample_dir}")
        
        merged_samples = {}
        
        # Merge contexts for each chromosome
        for chrom, context_files in chrom_files.items():
            # Load and merge contexts
            contexts_to_merge = []
            
            # Load CG (required as base) - use chromosome-specific positions for optimal performance
            if 'CG' in context_files:
                # Use chromosome-specific DMP positions if available
                chrom_positions = None
                if dmp_positions_by_chrom is not None and chrom in dmp_positions_by_chrom:
                    chrom_positions = dmp_positions_by_chrom[chrom]

                cg_sample = MethylSample.load_from_h5(context_files['CG'], chrom_positions, debug)
                contexts_to_merge.append(cg_sample)
            else:
                print(f"⚠️ Warning: {chrom}-CG.h5 not found in {sample_dir}, skipping chromosome {chrom}")
                continue

            # Load CHG and CHH if available
            for context in ['CHG', 'CHH']:
                if context in context_files:
                    try:
                        context_sample = MethylSample.load_from_h5(context_files[context], chrom_positions, debug)
                        contexts_to_merge.append(context_sample)
                    except Exception as e:
                        print(f"⚠️ Warning: Failed to load {chrom}-{context}.h5: {e}")
            
            if len(contexts_to_merge) == 0:
                continue
            
            # Merge all contexts using MethylSample.merge_contexts()
            try:
                merged_sample = MethylSample.merge_contexts(contexts_to_merge)
            except Exception as e:
                import traceback
                print(f"❌ Failed to merge contexts for chromosome {chrom}: {e}")
                print(f"   Error type: {type(e).__name__}")
                print("   Traceback:")
                traceback.print_exc()
                continue
            
            # Skip if merged sample is empty (no positions after merging)
            if len(merged_sample.pos) == 0:
                if debug:
                    print(f"⚠️ Warning: {chrom} merged sample is empty (no DMP positions), skipping")
                continue
            
            merged_samples[chrom] = merged_sample
        
        return merged_samples
    
    @staticmethod
    def load_samples_from_list(
        sample_paths: List[str],
        chromosomes: Optional[List[str]] = None,
        debug: bool = False,
        required_chromosomes: Optional[List[str]] = None,
        positions: Optional[np.ndarray] = None,
        dmp_positions_by_chrom: Optional[Dict[str, np.ndarray]] = None
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Load multiple samples from a list of directory paths.

        Each directory should contain {chrom}-CG.h5, {chrom}-CHG.h5, {chrom}-CHH.h5 files.
        Contexts are merged per chromosome using MethylSample.merge_contexts().

        Args:
            sample_paths: List of sample directory paths
            chromosomes: Optional list of chromosomes to load. If None, auto-detect.
            debug: Enable debug output
            required_chromosomes: If provided, only load these specific chromosomes (for performance)
            positions: If provided, only load data for these positions (ultra-performance)
            dmp_positions_by_chrom: DMP positions organized by chromosome (chromosome-specific optimization)

        Returns:
            List of (sample_name, {chrom: merged_MethylSample}) tuples
        """
        samples = []
        import time

        for i, sample_path in enumerate(sample_paths, 1):
            sample_dir = Path(sample_path)
            sample_name = sample_dir.name

            print(f"    ✅ Loading sample {i}/{len(sample_paths)}: {sample_name}")
            start_time = time.time()

            try:
                # Load and merge contexts for this sample
                merged_samples = DataLoader.load_sample_from_directory(
                    sample_dir, chromosomes, debug, required_chromosomes, positions, dmp_positions_by_chrom
                )
                
                # Skip sample if no chromosomes were loaded (all were empty or missing)
                if len(merged_samples) == 0:
                    print(f"⚠️ Warning: Sample {sample_name} has no valid chromosomes (all empty or missing), skipping")
                    continue
                
                load_time = time.time() - start_time
                samples.append((sample_name, merged_samples))
                if debug:
                    print(f"✅ Loaded sample: {sample_name} ({len(merged_samples)} chromosomes) in {load_time:.1f}s")
            except Exception as e:
                import traceback
                print(f"❌ Failed to load sample {sample_name}: {e}")
                print(f"   Error type: {type(e).__name__}")
                print("   Traceback:")
                traceback.print_exc()
                continue
        
        return samples

    @staticmethod
    def extract_sample_features(sample: Any,
                              dmp_positions: np.ndarray) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        """
        Extract DMP features from a methylation sample.

        Args:
            sample: MethylSample instance
            dmp_positions: Array of DMP positions used by the classifier

        Returns:
            Tuple of (feature_vector, availability_mask, stats_info)
        """
        # Get methylation levels with proper handling
        methylation_levels = sample.get_methylation_levels()
        # Handle NaN values and ensure proper range
        methylation_levels = np.nan_to_num(methylation_levels, nan=0.5)
        methylation_levels = np.clip(methylation_levels, 0.0, 1.0)
        
        pos_to_methylation = dict(zip(sample.pos, methylation_levels))

        feature_vector = []
        availability_mask = []
        missing_positions = 0

        for dmp_pos in dmp_positions:
            if dmp_pos in pos_to_methylation:
                methylation = pos_to_methylation[dmp_pos]
                methylation = np.clip(methylation, 0.0, 1.0)
                feature_vector.append(methylation)
                availability_mask.append(True)
            else:
                # Position not found in sample - use 0.5 (neutral) but mark as unavailable
                feature_vector.append(0.5)
                availability_mask.append(False)
                missing_positions += 1

        # Collect statistical information
        coverage = sample.get_coverage()
        avg_coverage = np.mean(coverage) if len(coverage) > 0 else 0
        stats_info = {
            'avg_coverage': avg_coverage,
            'total_positions': len(sample.pos),
            'sample_type': sample.sample_type,
            'missing_positions': missing_positions,
            'dmp_coverage_pct': (len(dmp_positions) - missing_positions) / len(dmp_positions) * 100
        }

        # Add statistical properties if available (for centroids)
        if sample.is_centroid:
            try:
                alpha, beta = sample.get_beta_parameters()
                stats_info.update({
                    'avg_alpha': np.mean(alpha),
                    'avg_beta': np.mean(beta),
                    'avg_tau': np.mean(sample.tau),
                    'avg_variance': np.mean(sample.variance)
                })
            except Exception as e:
                # If statistical properties can't be computed, continue without them
                pass

        return np.array(feature_vector), np.array(availability_mask), stats_info
