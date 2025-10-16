"""
Command-line interface for MethylCluster.

This module provides a CLI for clustering methylation samples using
configuration files, similar to other MethylPipeline tools.
"""

import argparse
import sys
import json
import logging
from pathlib import Path

from .config import MethylClusterConfig
from .cluster import MethylCluster


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
        
        # Create and run clustering
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

