"""Command line interface for MethylDetector."""

import logging
import sys
from pathlib import Path
from typing import Optional, List, Union

import click

# Handle imports for both direct execution and module execution
try:
    from ..core.methyldetector import MethylDetector
    from ..utils.core import load_config_from_json, setup_logging
except ImportError:
    # When running directly, add parent directory to path
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
    from methyl_detector.core.methyldetector import MethylDetector
    from methyl_detector.utils.core import load_config_from_json, setup_logging

@click.command()
@click.argument(
    'config',
    type=click.Path(exists=True, path_type=Path),
    required=True
)
@click.option(
    '--verbose', '-v',
    is_flag=True,
    default=False,
    help='Enable verbose logging'
)
@click.option(
    '--log-file',
    type=click.Path(path_type=Path),
    default=None,
    help='Path to log file for detailed logging (summary/errors still shown on screen)'
)
@click.version_option(version='0.3.0')
def main(config: Path, verbose: bool, log_file: Optional[Path]) -> None:
    """
    MethylDetector - Genomics sample classification using enhanced centroid-based approach.

    CONFIG is the path to a JSON configuration file compatible with the Pydantic model.
    """
    # Configure logging with dual handlers if log_file specified
    if log_file:
        # All logs go to file, but errors and info (summary) still appear on console
        setup_logging(
            verbose=verbose,
            log_file=log_file,
            console_level='INFO',  # Show INFO (summary) and above on console
            file_level='DEBUG' if verbose else 'INFO'  # All logs to file
        )
        logger = logging.getLogger(__name__)
        logger.info(f"Logging to file: {log_file}")
    else:
        # Standard logging to console only
        setup_logging(verbose=verbose)
        logger = logging.getLogger(__name__)
    
    try:
        logger.debug(f"Loading configuration from {config}")
        loaded_config = load_config_from_json(config)

        detector = MethylDetector(loaded_config)
        results = detector.run()

        # Handle both single result and list of results (multi-chromosome mode)
        if isinstance(results, list):
            # Multi-chromosome mode: summarize all results
            logger.info(f"\n{'='*80}")
            logger.info(f"MethylDetector Multi-Chromosome Analysis Results")
            logger.info(f"{'='*80}")
            logger.info(f"\n📊 Processed {len(results)} chromosomes")
            
            total_statistical = sum(r.total_statistical_dmps for r in results)
            total_biological = sum(r.total_biological_dmps for r in results)
            
            summary_lines = [
                "\n" + "="*80,
                "MethylDetector Multi-Chromosome Analysis Summary",
                "="*80,
                f"\n📊 Overall Summary:",
                f"  Chromosomes Processed: {len(results)}",
                f"  Total Statistical DMPs: {total_statistical:,}",
                f"  Total Biological DMPs: {total_biological:,}",
                f"  Average Retention Rate: {sum(r.biological_retention_rate for r in results) / len(results):.1%}"
            ]
            
            summary_lines.append("\n🔬 Per-Chromosome Results:")
            chromosomes = loaded_config.chromosome if isinstance(loaded_config.chromosome, list) else [loaded_config.chromosome]

            for i, result in enumerate(results, 1):
                # Use the chromosome from the config list (results are in same order as config)
                chrom = chromosomes[i-1] if i <= len(chromosomes) else f'Chromosome {i}'

                dmp_count = len(result.biologically_significant_dmps_df) if result.biologically_significant_dmps_df is not None else 0
                summary_lines.extend([
                    f"  [{i}] {chrom}:",
                    f"    Statistical DMPs: {result.total_statistical_dmps:,}",
                    f"    Biological DMPs: {result.total_biological_dmps:,}",
                    f"    Retention Rate: {result.biological_retention_rate:.1%}",
                    f"    Final DMPs: {dmp_count:,}"
                ])
            
            summary_lines.append("\n✅ Multi-chromosome analysis complete!")
            
            # Print summary to screen
            for line in summary_lines:
                logger.info(line)
                if log_file:
                    click.echo(line)
        else:
            # Single chromosome mode: original behavior
            result = results
            # Debug: check result structure
            logger.debug(f"Result type: {type(result)}")
            logger.debug(f"Result config_summary type: {type(result.config_summary)}")
            logger.debug(f"Result config_summary: {result.config_summary}")
            
            # Summary output - always shown on screen, also logged to file if log_file specified
            summary_lines = [
                "\n" + "="*60,
                "MethylDetector Analysis Results",
                "="*60,
                "\n📊 Summary:",
                f"  Statistical DMPs: {result.total_statistical_dmps:,}",
                f"  Biological DMPs: {result.total_biological_dmps:,}",
                f"  Retention Rate: {result.biological_retention_rate:.1%}",
                f"  Analysis Time: {result.timestamp}"
            ]
            
            if result.comparison_stats:
                summary_lines.append("\n🔬 Comparison Details:")
                for stats in result.comparison_stats:
                    summary_lines.extend([
                        f"  {stats.comparison_name}:",
                        f"    Positions: {stats.total_positions:,}",
                        f"    Statistical DMPs: {stats.statistical_dmps:,}",
                        f"    Biological DMPs: {stats.biological_dmps:,}",
                        f"    Processing Time: {stats.processing_time_seconds:.2f}s",
                        f"    GPU Used: {'Yes' if stats.gpu_used else 'No'}"
                    ])

            dmp_count = len(result.biologically_significant_dmps_df) if result.biologically_significant_dmps_df is not None else 0
            summary_lines.append(f"\n✅ Analysis complete! Found {dmp_count} DMPs")
            
            # Print summary to screen (and log if log_file specified)
            for line in summary_lines:
                logger.info(line)
                # Also use click.echo to ensure it appears on screen even with file logging
                if log_file:
                    click.echo(line)

    except Exception as e:
        error_msg = f"Analysis failed: {e}"
        logger.error(error_msg)
        import traceback
        traceback_str = traceback.format_exc()
        logger.error(f"Full traceback:\n{traceback_str}")
        # Error always appears on screen
        click.echo(f"\n❌ Error: {e}", err=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
