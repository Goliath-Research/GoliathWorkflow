"""Command line interface for MethylDetector."""

import logging
import sys
from pathlib import Path

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
@click.version_option(version='0.3.0')
def main(config: Path, verbose: bool) -> None:
    """
    MethylDetector - Genomics sample classification using enhanced centroid-based approach.

    CONFIG is the path to a JSON configuration file compatible with the Pydantic model.
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)
    
    try:
        logger.debug(f"Loading configuration from {config}")
        loaded_config = load_config_from_json(config)

        detector = MethylDetector(loaded_config)
        result = detector.run()

        # Debug: check result structure
        logger.debug(f"Result type: {type(result)}")
        logger.debug(f"Result config_summary type: {type(result.config_summary)}")
        logger.debug(f"Result config_summary: {result.config_summary}")
        
        click.echo("\n" + "="*60)
        click.echo("MethylDetector Analysis Results")
        click.echo("="*60)
        click.echo("\n📊 Summary:")
        click.echo(f"  Statistical DMPs: {result.total_statistical_dmps:,}")
        click.echo(f"  Biological DMPs: {result.total_biological_dmps:,}")
        click.echo(f"  Retention Rate: {result.biological_retention_rate:.1%}")
        click.echo(f"  Analysis Time: {result.timestamp}")

        if result.comparison_stats:
            click.echo("\n🔬 Comparison Details:")
            for stats in result.comparison_stats:
                click.echo(f"  {stats.comparison_name}:")
                click.echo(f"    Positions: {stats.total_positions:,}")
                click.echo(f"    Statistical DMPs: {stats.statistical_dmps:,}")
                click.echo(f"    Biological DMPs: {stats.biological_dmps:,}")
                click.echo(f"    Processing Time: {stats.processing_time_seconds:.2f}s")
                click.echo(f"    GPU Used: {'Yes' if stats.gpu_used else 'No'}")

        dmp_count = len(result.biologically_significant_dmps_df) if result.biologically_significant_dmps_df is not None else 0
        click.echo(f"\n✅ Analysis complete! Found {dmp_count} DMPs")

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        click.echo(f"\n❌ Error: {e}", err=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
