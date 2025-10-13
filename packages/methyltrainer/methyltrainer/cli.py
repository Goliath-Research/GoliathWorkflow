"""
Command-line interface for MethylTrainer
"""

import argparse
import sys
from pathlib import Path

from methyl_utils import get_logger

from .trainer import train_from_centroids, train_from_config_file
from .config import create_default_config

logger = get_logger(__name__)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="MethylTrainer - Train Bayesian classifiers from methylation centroids",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic training
  methyltrainer --centroid1 group1.h5 --centroid2 group2.h5 --output model.pkl

  # Training with custom parameters
  methyltrainer --centroid1 group1.h5 --centroid2 group2.h5 --output model.pkl \\
                --max-dmps 500 --max-q-value 0.01

  # Training from configuration file
  methyltrainer --config training_config.json

  # Training with metadata
  methyltrainer --centroid1 chr1-CG.h5 --centroid2 chr1-CG.h5 --output model.pkl \\
                --chromosome chr1 --context CG \\
                --centroid1-name "healthy" --centroid2-name "disease"
        """
    )
    
    # Input/Output arguments
    io_group = parser.add_argument_group('Input/Output')
    io_group.add_argument(
        '--centroid1', '-c1',
        type=str,
        help='Path to first centroid HDF5 file (extended_centroid type)'
    )
    io_group.add_argument(
        '--centroid2', '-c2',
        type=str,
        help='Path to second centroid HDF5 file (extended_centroid type)'
    )
    io_group.add_argument(
        '--output', '-o',
        type=str,
        help='Output path for trained model (.pkl file)'
    )
    io_group.add_argument(
        '--config',
        type=str,
        help='Path to JSON configuration file (overrides other arguments)'
    )
    
    # Metadata arguments
    meta_group = parser.add_argument_group('Metadata')
    meta_group.add_argument(
        '--centroid1-name',
        type=str,
        help='Name/label for centroid 1 (default: filename)'
    )
    meta_group.add_argument(
        '--centroid2-name',
        type=str,
        help='Name/label for centroid 2 (default: filename)'
    )
    meta_group.add_argument(
        '--chromosome',
        type=str,
        help='Chromosome identifier (e.g., chr1, chr2, ...)'
    )
    meta_group.add_argument(
        '--context',
        type=str,
        help='Methylation context (e.g., CG, CHG, CHH)'
    )
    
    # Comparison configuration
    comp_group = parser.add_argument_group('Comparison Configuration')
    comp_group.add_argument(
        '--min-coverage',
        type=int,
        default=10,
        help='Minimum coverage threshold (default: 10)'
    )
    
    # Filter configuration
    filter_group = parser.add_argument_group('Filter Configuration')
    filter_group.add_argument(
        '--max-q-value',
        type=float,
        default=0.05,
        help='Maximum q-value for DMPs (default: 0.05)'
    )
    filter_group.add_argument(
        '--min-delta-mean',
        type=float,
        default=0.1,
        help='Minimum absolute difference in means (default: 0.1)'
    )
    filter_group.add_argument(
        '--max-overlap',
        type=float,
        default=0.6,
        help='Maximum distribution overlap (default: 0.6)'
    )
    filter_group.add_argument(
        '--min-jeffreys',
        type=float,
        default=0.3,
        help='Minimum Jeffreys divergence (default: 0.3)'
    )
    filter_group.add_argument(
        '--min-auc',
        type=float,
        default=0.6,
        help='Minimum AUC score (default: 0.6)'
    )
    filter_group.add_argument(
        '--max-dmps',
        type=int,
        default=1000,
        help='Maximum number of DMPs to use (default: 1000)'
    )
    filter_group.add_argument(
        '--sort-by',
        type=str,
        default='jeffreys_divergence',
        choices=['jeffreys_divergence', 'q_value', 'overlap', 'auc', 'effect_size'],
        help='Metric to sort DMPs by for top-k selection (default: jeffreys_divergence)'
    )
    
    # Other options
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--version',
        action='version',
        version='MethylTrainer 0.1.0'
    )
    
    return parser.parse_args()


def main():
    """Main entry point for MethylTrainer CLI."""
    args = parse_args()
    
    try:
        # Check if using config file
        if args.config:
            logger.info("Using configuration file...")
            model_package = train_from_config_file(Path(args.config))
        else:
            # Validate required arguments
            if not args.centroid1 or not args.centroid2 or not args.output:
                logger.error("❌ Error: --centroid1, --centroid2, and --output are required")
                logger.error("   Or use --config to load from configuration file")
                sys.exit(1)
            
            # Create configuration from arguments
            config = create_default_config(
                centroid1_path=args.centroid1,
                centroid2_path=args.centroid2,
                output_path=args.output,
                centroid1_name=args.centroid1_name,
                centroid2_name=args.centroid2_name,
                chromosome=args.chromosome,
                context=args.context,
                min_coverage=args.min_coverage,
                max_q_value=args.max_q_value,
                min_delta_mean=args.min_delta_mean,
                max_overlap=args.max_overlap,
                min_jeffreys_divergence=args.min_jeffreys,
                min_auc=args.min_auc,
                max_dmps=args.max_dmps,
                sort_by=args.sort_by,
                verbose=args.verbose
            )
            
            # Train
            model_package = train_from_centroids(
                centroid1_path=Path(args.centroid1),
                centroid2_path=Path(args.centroid2),
                output_path=Path(args.output),
                config=config,
                verbose=args.verbose
            )
        
        logger.info("🎉 Training completed successfully!")
        sys.exit(0)
        
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Training interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

