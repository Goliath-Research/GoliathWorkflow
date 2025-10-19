"""
Command-line interface for MethylCentroid.

This module provides a clean, modular CLI that demonstrates
the refactored architecture following SOLID principles.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional, List

from .config import MethylCentroidConfig, BatchProcessingConfig, ProcessingConfig
from .core import MethylCentroid
from methyl_utils.logging_utils import setup_logging


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser with clean, organized options."""
    parser = argparse.ArgumentParser(
        description="MethylCentroid - Advanced Methylation Centroid Calculation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process single chromosome/context
  python -m methylcentroid.cli -c 1 -x CG -s samples.csv -o ./output

  # Use configuration file
  python -m methylcentroid.cli --config config.json

  # Batch processing
  python -m methylcentroid.cli --batch-config batch_config.json
        """
    )

    # Input configuration
    config_group = parser.add_argument_group('Configuration')
    config_group.add_argument(
        '--config', '-c',
        type=Path,
        help='Path to JSON configuration file'
    )
    config_group.add_argument(
        '--batch-config',
        type=Path,
        help='Path to batch processing configuration file'
    )

    # Individual parameters (when not using config file)
    params_group = parser.add_argument_group('Individual Parameters')
    params_group.add_argument(
        '--chromosome', '-C',
        help='Chromosome identifier (e.g., "1", "X")'
    )
    params_group.add_argument(
        '--context', '-x',
        choices=['CG', 'CHG', 'CHH'],
        help='Context type'
    )
    params_group.add_argument(
        '--samples', '-s',
        type=Path,
        help='Path to CSV file containing sample directory paths'
    )
    params_group.add_argument(
        '--output-dir', '-o',
        type=Path,
        help='Output directory for results'
    )
    
    # Metadata parameters
    metadata_group = parser.add_argument_group('Metadata')
    metadata_group.add_argument(
        '--laboratory',
        help='Laboratory or institution name'
    )
    metadata_group.add_argument(
        '--disease',
        help='Disease or condition being studied'
    )
    metadata_group.add_argument(
        '--group',
        help='Sample group identifier (e.g., "cancer", "control")'
    )
    metadata_group.add_argument(
        '--batch',
        help='Batch identifier for sample processing'
    )

    # Processing options
    processing_group = parser.add_argument_group('Processing Options')
    processing_group.add_argument(
        '--min-coverage',
        type=int,
        default=4,
        help='Minimum coverage threshold (default: 4)'
    )
    processing_group.add_argument(
        '--max-iterations',
        type=int,
        default=10,
        help='Maximum outlier removal iterations (default: 10)'
    )
    processing_group.add_argument(
        '--alpha',
        type=float,
        default=0.05,
        help='Significance level for outlier detection (default: 0.05)'
    )

    # Output options
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    output_group.add_argument(
        '--save-intermediate',
        action='store_true',
        help='Save intermediate results and debug information'
    )
    output_group.add_argument(
        '--disable-validation',
        action='store_true',
        help='Disable centroid validation (faster but less safe)'
    )
    output_group.add_argument(
        '--disable-visualization',
        action='store_true',
        help='Disable result visualization'
    )

    return parser


def read_samples_from_csv(csv_file: Path) -> List[str]:
    """
    Read sample paths from CSV file.

    Args:
        csv_file: Path to CSV file containing sample paths

    Returns:
        List of sample directory paths
    """
    try:
        with open(csv_file, 'r') as f:
            samples = [line.strip() for line in f if line.strip()]

        if not samples:
            raise ValueError(f"No samples found in {csv_file}")

        return samples

    except FileNotFoundError:
        raise FileNotFoundError(f"Sample file not found: {csv_file}")
    except Exception as e:
        raise RuntimeError(f"Error reading sample file {csv_file}: {e}")


def create_config_from_args(args: argparse.Namespace) -> MethylCentroidConfig:
    """
    Create configuration from command line arguments.

    Args:
        args: Parsed command line arguments

    Returns:
        MethylCentroidConfig instance
    """
    if not all([args.chromosome, args.context, args.samples, args.output_dir]):
        raise ValueError("When not using --config, all of --chromosome, --context, --samples, and --output-dir are required")

    # Check that all metadata fields are provided
    if not all([args.laboratory, args.disease, args.group, args.batch]):
        raise ValueError("When not using --config, all metadata fields (--laboratory, --disease, --group, --batch) are required")

    # Read samples from CSV
    sample_paths = read_samples_from_csv(args.samples)

    return MethylCentroidConfig(
        laboratory=args.laboratory,
        disease=args.disease,
        group=args.group,
        batch=args.batch,
        chrom=args.chromosome,
        ctx=args.context,
        output_dir=str(args.output_dir),
        samples=sample_paths,
        min_coverage=args.min_coverage,
        max_iterations=args.max_iterations,
        α=args.alpha
    )


def create_processing_config(args: argparse.Namespace) -> ProcessingConfig:
    """
    Create processing configuration from arguments.

    Args:
        args: Parsed command line arguments

    Returns:
        ProcessingConfig instance
    """
    return ProcessingConfig(
        enable_profiling=True,  # Always enable profiling for CLI
        save_intermediate=args.save_intermediate,
        verbose_logging=args.verbose,
        enable_validation=not args.disable_validation,
        enable_visualization=not args.disable_visualization
    )


def run_single_processing(config: MethylCentroidConfig,
                         processing_config: ProcessingConfig) -> None:
    """
    Run single chromosome/context processing.

    Args:
        config: MethylCentroid configuration
        processing_config: Processing configuration
    """
    print(f"🚀 Starting MethylCentroid processing for {config.chrom}-{config.ctx}")
    print(f"📁 Output directory: {config.output_dir}")
    print(f"📊 Samples: {len(config.samples)}")
    print(f"🎯 Minimum coverage: {config.min_coverage}")
    print()

    try:
        # Create and run MethylCentroid
        mc = MethylCentroid.from_config(config)
        results = mc.build_centroid()

        # Print results
        print("\n✅ Processing completed successfully!")
        print(f"📈 Outliers removed: {results.total_samples_removed}")
        print(f"💾 Final centroid: {results.final_centroid_path}")

        if results.iterations:
            print(f"📋 Iterations performed: {len(results.iterations)}")
            for iteration in results.iterations[-3:]:  # Show last 3 iterations
                print(f"   Iteration {iteration.iteration}: p-value = {iteration.p_value:.6f}")

    except Exception as e:
        print(f"❌ Error during processing: {e}", file=sys.stderr)
        if processing_config.verbose_logging:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def run_batch_processing(batch_config: BatchProcessingConfig) -> None:
    """
    Run batch processing for multiple chromosome/context combinations.

    Args:
        batch_config: Batch processing configuration
    """
    print("🚀 Starting batch MethylCentroid processing")
    print(f"📊 Combinations to process: {len(batch_config.chromosomes)} chromosomes × {len(batch_config.contexts)} contexts")
    print(f"📁 Base output directory: {batch_config.base_config.output_dir}")
    print()

    total_combinations = len(batch_config.chromosomes) * len(batch_config.contexts)
    processed_combinations = 0
    total_outliers = 0

    for chrom in batch_config.chromosomes:
        for ctx in batch_config.contexts:
            processed_combinations += 1
            print(f"\n{'='*60}")
            print(f"Processing {processed_combinations}/{total_combinations}: {chrom}-{ctx}")
            print('='*60)

            try:
                # Create config for this combination
                base_data = batch_config.base_config.model_dump()
                # Remove chrom and ctx from base_data to avoid conflicts
                base_data.pop('chrom', None)
                base_data.pop('ctx', None)

                combination_config = MethylCentroidConfig(
                    **base_data,
                    chrom=chrom,
                    ctx=ctx
                )

                # Create default processing config
                processing_config = ProcessingConfig()

                # Run processing
                run_single_processing(combination_config, processing_config)

                # Accumulate statistics (this would be improved with actual result tracking)
                total_outliers += 0  # Placeholder

            except Exception as e:
                error_msg = f"Failed to process {chrom}-{ctx}: {e}"
                print(f"❌ {error_msg}", file=sys.stderr)

                if batch_config.continue_on_error:
                    print("Continuing with next combination...")
                    continue
                else:
                    print("Stopping batch processing due to error.")
                    sys.exit(1)

    print(f"\n{'='*60}")
    print("🎉 Batch processing completed!")
    print(f"📊 Total combinations processed: {processed_combinations}")
    print(f"📈 Total outliers removed: {total_outliers}")
    print('='*60)


def main() -> None:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose)

    try:
        if args.batch_config:
            # Batch processing mode
            if not args.batch_config.exists():
                raise FileNotFoundError(f"Batch configuration file not found: {args.batch_config}")

            batch_config = BatchProcessingConfig.from_file(args.batch_config)
            run_batch_processing(batch_config)

        elif args.config:
            # Single processing with config file
            if not args.config.exists():
                raise FileNotFoundError(f"Configuration file not found: {args.config}")

            config = MethylCentroidConfig.from_file(args.config)
            processing_config = create_processing_config(args)
            run_single_processing(config, processing_config)

        else:
            # Single processing with command line arguments
            config = create_config_from_args(args)
            processing_config = create_processing_config(args)
            run_single_processing(config, processing_config)

    except KeyboardInterrupt:
        print("\n⚠️  Processing interrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"❌ Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
