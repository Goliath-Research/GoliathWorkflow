#!/usr/bin/env python3
"""
Integrated Architecture for MethylUtils

This module provides a unified architecture that integrates all MethylUtils components:
- methyl_utils (core statistical functions and genomic position aligner)
- Shared utilities and models
- Container optimization
- Performance monitoring

Key Features:
- Unified API across all modules
- Shared type system with Pydantic models
- Integrated performance monitoring
- Container-aware resource management
- Seamless GPU/CPU backend switching
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional, List, Union
from pathlib import Path
import numpy as np
from dataclasses import dataclass
from abc import ABC, abstractmethod

# Import all modules with proper error handling
try:
    # Core statistical functions
    from methyl_utils import (
        auto_compute_distance,
        get_metric_factory,
        storey_qvalues,
        stouffer_global_p,
        MethylSample,
        Metric
    )

    # Genomic position aligner
    from methyl_utils import PositionAligner

    # Shared utilities
    from methyl_utils.gpu_detection import (
        is_gpu_available,
        get_gpu_state,
        get_cupy,
        cleanup_gpu_memory
    )
    from methyl_utils.logging_utils import setup_logging, get_logger
    from methyl_utils.metric_validations import validate_methylation_data

    # Models
    from methyl_utils import (
        PositionMethylationStats,
        GroupMethylationStats,
        AlignmentStats,
        MethylationAnalysisResults
    )

except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.error(f"Import error: {e}")
    logger.error("Please ensure all MethylUtils modules are properly installed")
    raise

logger = logging.getLogger(__name__)

class GenomeProcessor(ABC):
    """
    Abstract base class for genome-scale methylation processors.

    This class defines the interface for processing large genomic datasets
    with optimized memory management and GPU acceleration.
    """

    def __init__(self, chunk_size: int = 10_000_000, use_gpu: bool = True):
        """
        Initialize genome processor.

        Args:
            chunk_size: Number of positions to process per chunk
            use_gpu: Whether to use GPU acceleration
        """
        self.chunk_size = chunk_size
        self.use_gpu = use_gpu and is_gpu_available()

        # Performance monitoring
        self.performance_stats = {
            'chunks_processed': 0,
            'total_positions': 0,
            'processing_time': 0.0,
            'memory_peak': 0.0,
            'gpu_memory_peak': 0.0
        }

        logger.info(f"Initialized {self.__class__.__name__} with chunk_size={chunk_size:,}, use_gpu={self.use_gpu}")

    @abstractmethod
    def process_chunk(self, chunk_data: Dict[str, np.ndarray]) -> Dict[str, Any]:
        """
        Process a single chunk of genomic data.

        Args:
            chunk_data: Dictionary containing chunk data

        Returns:
            Processing results for this chunk
        """
        pass

    @abstractmethod
    def combine_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Combine results from multiple chunks.

        Args:
            results: List of chunk results

        Returns:
            Combined final results
        """
        pass

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get current performance statistics."""
        return self.performance_stats.copy()

    def reset_stats(self) -> None:
        """Reset performance statistics."""
        self.performance_stats = {
            'chunks_processed': 0,
            'total_positions': 0,
            'processing_time': 0.0,
            'memory_peak': 0.0,
            'gpu_memory_peak': 0.0
        }

@dataclass
class GenomeScaleConfig:
    """
    Configuration for genome-scale processing.

    This class encapsulates all configuration parameters needed for
    processing large genomic datasets efficiently.
    """
    # Data processing
    chunk_size: int = 10_000_000
    overlap_size: int = 1_000
    compression_level: int = 9

    # Hardware resources
    use_gpu: bool = True
    gpu_memory_fraction: float = 0.8
    cpu_threads: int = 8
    max_memory_gb: int = 350

    # I/O optimization
    buffer_size_mb: int = 256
    parallel_reads: int = 4
    write_buffering: bool = True

    # Performance monitoring
    enable_profiling: bool = True
    log_level: str = "INFO"

    # Container settings
    container_work_dir: Path = Path("/home/ubuntu/Work/cuda")
    host_work_dir: Path = Path.home() / "Work" / "cuda"

    def validate(self) -> None:
        """Validate configuration parameters."""
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if not (0 < self.gpu_memory_fraction <= 1):
            raise ValueError("gpu_memory_fraction must be between 0 and 1")
        if self.cpu_threads <= 0:
            raise ValueError("cpu_threads must be positive")

class IntegratedMethylUtils:
    """
    Unified interface for all MethylUtils functionality.

    This class provides a single entry point for all methylation analysis
    operations, integrating the statistical functions, position aligner,
    and utility modules into a cohesive system.
    """

    def __init__(self, config: Optional[GenomeScaleConfig] = None):
        """
        Initialize integrated MethylUtils system.

        Args:
            config: Configuration for genome-scale processing
        """
        self.config = config or GenomeScaleConfig()

        # Validate configuration
        self.config.validate()

        # Setup logging
        setup_logging(verbose=(self.config.log_level == "DEBUG"))

        # Initialize components
        self.metric_factory = get_metric_factory()
        self.gpu_available = is_gpu_available()
        self.cupy = get_cupy() if self.gpu_available else None

        # Performance tracking
        self.logger = get_logger(__name__)
        self.logger.info("Integrated MethylUtils initialized")
        self.logger.info(f"GPU available: {self.gpu_available}")
        if self.gpu_available:
            gpu_state = get_gpu_state()
            self.logger.info(f"GPU: {gpu_state['gpu_name']} ({gpu_state['memory_gb']:.1f}GB)")

    def create_position_aligner(self, max_samples: int = 1000) -> PositionAligner:
        """
        Create a position aligner with optimized settings.

        Args:
            max_samples: Maximum number of samples to support

        Returns:
            Configured PositionAligner instance
        """
        aligner = PositionAligner(
            max_samples=max_samples,
            use_gpu=self.config.use_gpu
        )

        # Set coverage threshold
        aligner.set_min_coverage(1)  # Default minimum coverage

        self.logger.info(f"Created PositionAligner with max_samples={max_samples}")
        return aligner

    def compute_distance_matrix(
        self,
        samples: List[MethylSample],
        metric: Metric = "jensen_shannon",
        use_gpu: Optional[bool] = None
    ) -> np.ndarray:
        """
        Compute distance matrix between multiple samples.

        Args:
            samples: List of MethylSample objects
            metric: Distance metric to use
            use_gpu: Override GPU usage setting

        Returns:
            Distance matrix (n_samples x n_samples)
        """
        if use_gpu is None:
            use_gpu = self.config.use_gpu

        n_samples = len(samples)
        distance_matrix = np.zeros((n_samples, n_samples), dtype=np.float32)

        self.logger.info(f"Computing distance matrix for {n_samples} samples using {metric}")

        # Compute pairwise distances
        for i in range(n_samples):
            for j in range(i + 1, n_samples):
                # Extract methylation levels
                levels_i = samples[i].get_methylation_levels()
                levels_j = samples[j].get_methylation_levels()

                # Align positions (simplified - in practice use PositionAligner)
                # For now, assume samples have compatible positions
                if len(levels_i) != len(levels_j):
                    self.logger.warning(f"Sample {i} and {j} have different position counts")
                    continue

                # Compute distance
                distance = auto_compute_distance(
                    levels_i.reshape(1, -1),  # Add batch dimension
                    np.ones_like(levels_i).reshape(1, -1),  # Dummy beta values
                    levels_j.reshape(1, -1),
                    np.ones_like(levels_j).reshape(1, -1),
                    metric=metric,
                    use_gpu=use_gpu
                )

                distance_matrix[i, j] = distance[0]  # Extract scalar
                distance_matrix[j, i] = distance[0]  # Symmetric

        return distance_matrix

    def analyze_methylation_patterns(
        self,
        sample_files: List[Union[str, Path]],
        output_dir: Union[str, Path],
        metrics: List[Metric] = None
    ) -> MethylationAnalysisResults:
        """
        Perform comprehensive methylation pattern analysis.

        Args:
            sample_files: List of sample file paths
            output_dir: Output directory for results
            metrics: List of metrics to compute

        Returns:
            Complete analysis results
        """
        if metrics is None:
            metrics = ["jensen_shannon", "hellinger", "wasserstein"]

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"Analyzing {len(sample_files)} samples")
        self.logger.info(f"Computing metrics: {metrics}")

        # Load samples
        samples = []
        for file_path in sample_files:
            try:
                sample = MethylSample.load_from_h5(file_path)
                samples.append(sample)
                self.logger.info(f"Loaded sample: {Path(file_path).name}")
            except Exception as e:
                self.logger.error(f"Failed to load {file_path}: {e}")
                continue

        if not samples:
            raise ValueError("No valid samples loaded")

        # Create position aligner
        aligner = self.create_position_aligner(max_samples=len(samples))

        # Add samples to aligner
        for i, sample in enumerate(samples):
            success = aligner.add_sample(sample, sample_index=i)
            if success:
                self.logger.info(f"Added sample {i} to aligner")
            else:
                self.logger.warning(f"Failed to add sample {i}")

        # Compute distance matrices for each metric
        distance_matrices = {}
        for metric in metrics:
            try:
                matrix = self.compute_distance_matrix(samples, metric=metric)
                distance_matrices[metric] = matrix
                self.logger.info(f"Computed {metric} distance matrix")
            except Exception as e:
                self.logger.error(f"Failed to compute {metric}: {e}")

        # Create analysis results
        analysis_results = MethylationAnalysisResults(
            analysis_id=f"methylation_analysis_{len(samples)}_samples",
            alignment_stats=AlignmentStats(
                total_positions=aligner.total_positions,
                valid_positions=aligner.valid_positions,
                sample_count=aligner.sample_count,
                gpu_acceleration=self.gpu_available
            ),
            metadata={
                "metrics_computed": list(distance_matrices.keys()),
                "sample_files": [str(f) for f in sample_files],
                "config": self.config.__dict__
            }
        )

        # Save results
        results_file = output_dir / "analysis_results.json"
        analysis_results.save_to_json(results_file)

        # Save distance matrices
        for metric, matrix in distance_matrices.items():
            matrix_file = output_dir / f"distance_matrix_{metric}.npy"
            np.save(matrix_file, matrix)

        self.logger.info(f"Analysis complete. Results saved to {output_dir}")
        return analysis_results

    def process_genome_chunks(
        self,
        genome_file: Union[str, Path],
        processor: GenomeProcessor,
        output_dir: Union[str, Path]
    ) -> Dict[str, Any]:
        """
        Process a genome file in chunks for memory efficiency.

        Args:
            genome_file: Path to genome methylation file
            processor: GenomeProcessor instance for chunk processing
            output_dir: Output directory for chunk results

        Returns:
            Combined processing results
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"Processing genome file: {genome_file}")
        self.logger.info(f"Chunk size: {self.config.chunk_size:,} positions")

        # Load genome data
        try:
            genome_data = MethylSample.load_from_h5(genome_file)
            total_positions = len(genome_data.pos)
            self.logger.info(f"Genome loaded: {total_positions:,} positions")
        except Exception as e:
            self.logger.error(f"Failed to load genome file: {e}")
            raise

        # Process in chunks
        chunk_results = []
        for start_pos in range(0, total_positions, self.config.chunk_size):
            end_pos = min(start_pos + self.config.chunk_size, total_positions)

            # Extract chunk data
            chunk_data = {
                'positions': genome_data.pos[start_pos:end_pos],
                'mC': genome_data.mC[start_pos:end_pos],
                'uC': genome_data.uC[start_pos:end_pos],
                'tnc': genome_data.tnc[start_pos:end_pos],
                'chunk_id': len(chunk_results),
                'start_pos': start_pos,
                'end_pos': end_pos
            }

            # Add centroid data if available
            if genome_data.N is not None:
                chunk_data['N'] = genome_data.N[start_pos:end_pos]
            if genome_data.Sx is not None:
                chunk_data['Sx'] = genome_data.Sx[start_pos:end_pos]

            # Process chunk
            self.logger.info(f"Processing chunk {len(chunk_results)}: positions {start_pos:,}-{end_pos:,}")
            try:
                result = processor.process_chunk(chunk_data)
                chunk_results.append(result)

                # Save intermediate results
                chunk_file = output_dir / f"chunk_{len(chunk_results)-1:04d}.json"
                import json
                with open(chunk_file, 'w') as f:
                    json.dump(result, f, indent=2, default=str)

            except Exception as e:
                self.logger.error(f"Failed to process chunk {len(chunk_results)}: {e}")
                continue

        # Combine results
        self.logger.info(f"Combining results from {len(chunk_results)} chunks")
        final_results = processor.combine_results(chunk_results)

        # Save final results
        final_file = output_dir / "final_results.json"
        import json
        with open(final_file, 'w') as f:
            json.dump(final_results, f, indent=2, default=str)

        self.logger.info(f"Genome processing complete. Results saved to {output_dir}")
        return final_results

    def cleanup_resources(self) -> None:
        """Clean up system resources."""
        try:
            cleanup_gpu_memory()
            self.logger.info("Resources cleaned up successfully")
        except Exception as e:
            self.logger.warning(f"Resource cleanup failed: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup_resources()

def create_genome_processor_class(processing_function):
    """
    Factory function to create a GenomeProcessor class from a processing function.

    Args:
        processing_function: Function that takes chunk_data and returns results

    Returns:
        GenomeProcessor subclass
    """

    class CustomGenomeProcessor(GenomeProcessor):
        def __init__(self, processing_func, **kwargs):
            super().__init__(**kwargs)
            self.processing_func = processing_func

        def process_chunk(self, chunk_data):
            return self.processing_func(chunk_data)

        def combine_results(self, results):
            # Default combination - can be overridden
            if not results:
                return {}

            # Combine numeric results
            combined = {}
            for key in results[0].keys():
                if isinstance(results[0][key], (int, float)):
                    combined[key] = sum(r[key] for r in results)
                elif isinstance(results[0][key], list):
                    combined[key] = []
                    for r in results:
                        combined[key].extend(r[key])
                else:
                    combined[key] = results[-1][key]  # Take last value

            return combined

    return CustomGenomeProcessor

# Convenience functions
def create_integrated_system(config: Optional[GenomeScaleConfig] = None) -> IntegratedMethylUtils:
    """
    Create an integrated MethylUtils system.

    Args:
        config: Optional configuration

    Returns:
        IntegratedMethylUtils instance
    """
    return IntegratedMethylUtils(config)

def process_genome_file(
    genome_file: Union[str, Path],
    output_dir: Union[str, Path],
    processing_function,
    config: Optional[GenomeScaleConfig] = None
) -> Dict[str, Any]:
    """
    Process a genome file using a custom processing function.

    Args:
        genome_file: Path to genome file
        output_dir: Output directory
        processing_function: Function to process each chunk
        config: Optional configuration

    Returns:
        Processing results
    """
    processor_class = create_genome_processor_class(processing_function)
    processor = processor_class()

    with create_integrated_system(config) as system:
        return system.process_genome_chunks(genome_file, processor, output_dir)

if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    # Create configuration for genome-scale processing
    config = GenomeScaleConfig(
        chunk_size=5_000_000,  # 5M positions per chunk
        use_gpu=True,
        cpu_threads=8,
        enable_profiling=True
    )

    # Create integrated system
    system = create_integrated_system(config)

    print("🔬 Integrated MethylUtils System Ready")
    print(f"GPU Available: {system.gpu_available}")
    print(f"Chunk Size: {config.chunk_size:,} positions")
    print(f"CPU Threads: {config.cpu_threads}")

    # Example processing function
    def methylation_statistics_processor(chunk_data):
        """Example processor that computes methylation statistics."""
        mC = chunk_data['mC']
        uC = chunk_data['uC']

        # Compute methylation levels
        methylation_levels = mC / (mC + uC)

        return {
            'chunk_id': chunk_data['chunk_id'],
            'positions_processed': len(methylation_levels),
            'mean_methylation': float(np.mean(methylation_levels)),
            'median_methylation': float(np.median(methylation_levels)),
            'methylation_std': float(np.std(methylation_levels)),
            'positions_range': [int(chunk_data['start_pos']), int(chunk_data['end_pos'])]
        }

    # Example of how to use the processor
    print("\n📊 Example Processor Created:")
    print("Function: methylation_statistics_processor")
    print("Computes: mean, median, std of methylation levels per chunk")

    print("\n✅ System ready for genome-scale processing!")
