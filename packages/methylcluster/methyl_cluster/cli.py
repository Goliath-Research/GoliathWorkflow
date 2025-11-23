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
from methyl_utils import MethylSample


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

  # Enable soft assignments with temperature
  python -m methyl_cluster.cli --config config.json --soft --temperature 2.5

Configuration file format:
  {
    "samples": ["/path/to/sample1", "/path/to/sample2", ...],
    "chrom": "1",
    "ctx": "CG",
    "metric": "jensen_shannon",
    "min_cluster_size": 5,
    "output_dir": "./results",
    "cache_distance_matrix": true,
    "use_gpu": true,
    "soft_assignment": false,  # New: Enable soft probabilities
    "assignment_temperature": 1.0  # New: Softmax temperature (>=0.1, <=10.0)
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
    
    # New arguments for overrides
    parser.add_argument(
        "--soft",
        action="store_true",
        help="Enable soft cluster assignments with membership probabilities (overrides config)"
    )
    
    parser.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Temperature parameter for softmax in soft assignments (overrides config; default=1.0, range [0.1,10.0])"
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
        
        # Create and validate config
        config = MethylClusterConfig(**config_data)
        
        # Apply CLI overrides after loading
        if args.soft:
            config.soft_assignment = True
            logger.info("CLI override: soft_assignment = True")
        
        if args.temperature != 1.0:
            config.assignment_temperature = args.temperature
            logger.info(f"CLI override: assignment_temperature = {args.temperature}")
        
        # Re-validate after overrides (Pydantic ensures bounds)
        config = MethylClusterConfig.model_validate(config.model_dump())
        
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
        logger.info(f"Soft assignment: {config.soft_assignment}")
        logger.info(f"Assignment temperature: {config.assignment_temperature}")
        logger.info("="*60)
        
        # Normalize output directory path
        config.output_dir = str(Path(config.output_dir).resolve())
        logger.info(f"Normalized output directory: {config.output_dir}")
        
        # Create and run clustering pipeline
        # Samples will be loaded without global alignment
        # Distance computation will align each sample pair individually
        logger.info("Starting clustering pipeline...")
        cluster = MethylCluster(config)
        results = cluster.run()
        
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

