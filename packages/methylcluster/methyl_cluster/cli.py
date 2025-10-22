"""
Command-line interface for MethylCluster.

This module provides a CLI for clustering methylation samples using
configuration files, similar to other MethylPipeline tools.
"""

import argparse
import sys
import json
import logging
import numpy as np
from pathlib import Path

from .config import MethylClusterConfig
from .cluster import MethylCluster
from methyl_utils.methyl_sample import MethylSample


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging for the CLI.
    
    Args:
        verbose: Enable verbose (DEBUG) logging
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Cluster methylation samples using HDBSCAN with GPU-accelerated distance metrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run clustering with configuration file
  python -m methyl_cluster.cli --config config.json

  # Run with verbose output
  python -m methyl_cluster.cli --config config.json --verbose

Configuration file format:
  {
    "samples": ["/path/to/sample1", "/path/to/sample2", ...],
    "chrom": "1",
    "ctx": "CG",
    "metric": "jensen_shannon",
    "min_cluster_size": 5,
    "output_dir": "./results",
    "cache_distance_matrix": true,
    "use_gpu": true
  }

Available metrics:
  - jensen_shannon: Jensen-Shannon distance (default)
  - hellinger: Hellinger distance

For more information, see the README.md file.
        """
    )
    
    # Required arguments
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to JSON configuration file"
    )
    
    # Optional arguments
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output (DEBUG level logging)"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)
    
    try:
        # Validate configuration file exists
        if not args.config.exists():
            logger.error(f"Configuration file not found: {args.config}")
            sys.exit(1)
        
        # Load configuration
        logger.info(f"Loading configuration from {args.config}")
        with open(args.config, 'r') as f:
            config_data = json.load(f)
        
        # Validate configuration
        try:
            config = MethylClusterConfig(**config_data)
        except Exception as e:
            logger.error(f"Invalid configuration: {e}")
            sys.exit(1)
        
        # Log configuration summary
        logger.info("="*60)
        logger.info("MethylCluster Configuration")
        logger.info("="*60)
        logger.info(f"Samples: {len(config.samples)}")
        logger.info(f"Chromosome: {config.chrom}")
        logger.info(f"Context: {config.ctx}")
        logger.info(f"Metric: {config.metric.value}")
        logger.info(f"Min cluster size: {config.min_cluster_size}")
        logger.info(f"Output directory: {config.output_dir}")
        logger.info(f"GPU acceleration: {config.use_gpu}")
        logger.info(f"Cache distance matrix: {config.cache_distance_matrix}")
        logger.info("="*60)
        
        # Normalize output directory path
        config.output_dir = str(Path(config.output_dir).resolve())
        logger.info(f"Normalized output directory: {config.output_dir}")
        
        # Load and align samples before clustering
        logger.info("Loading and aligning samples...")
        samples = []
        for sample_path in config.samples:
            h5_file = Path(sample_path) / f"{config.chrom}-{config.ctx}.h5"
            if h5_file.exists():
                sample = MethylSample.load_from_h5(h5_file)
                samples.append(sample)
                logger.info(f"  Loaded sample: {len(sample.pos)} positions")
            else:
                logger.warning(f"  Sample file not found: {h5_file}")
        
        if len(samples) < 2:
            logger.error("Need at least 2 samples for clustering")
            sys.exit(1)
        
        # Find common positions across all samples
        logger.info("Finding common positions across all samples...")
        common_positions = set(samples[0].pos)
        for sample in samples[1:]:
            common_positions = common_positions.intersection(set(sample.pos))
        
        common_positions = np.array(sorted(list(common_positions)), dtype=np.uint32)
        logger.info(f"Found {len(common_positions)} common positions")
        
        if len(common_positions) == 0:
            logger.error("No common positions found between samples")
            sys.exit(1)
        
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
            logger.info(f"  Aligned sample {i+1}: {np.sum(valid_mask)} valid positions")
        
        logger.info(f"✓ All samples aligned to {len(common_positions)} common positions")
        
        # Create and run clustering with aligned samples
        logger.info("Starting clustering pipeline with aligned samples...")
        cluster = MethylCluster(config)
        cluster.samples = aligned_samples  # Use aligned samples
        cluster.sample_paths = [Path(p) for p in config.samples]  # Keep original paths
        
        # Skip load_samples() since we already have aligned samples
        # Call compute_distances() and cluster() directly
        cluster.compute_distances()
        
        # Ensure distance matrix is double precision for HDBSCAN
        if cluster.distance_matrix is not None:
            cluster.distance_matrix = cluster.distance_matrix.astype(np.float64)
        
        results = cluster.cluster()
        cluster.save_results(results)
        
        # Display results
        logger.info("="*60)
        logger.info("Clustering Results")
        logger.info("="*60)
        logger.info(f"Number of clusters: {results['n_clusters']}")
        logger.info(f"Noise samples: {results['n_noise']}")
        logger.info("")
        logger.info("Cluster sizes:")
        for cluster_name, size in results['cluster_sizes'].items():
            logger.info(f"  {cluster_name}: {size} samples")
        logger.info("="*60)
        logger.info(f"Results saved to: {config.output_dir}")
        logger.info("="*60)
        
        logger.info("Clustering complete!")
        
    except KeyboardInterrupt:
        logger.info("\nClustering interrupted by user")
        sys.exit(130)
    
    except Exception as e:
        logger.exception(f"Clustering failed with error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

