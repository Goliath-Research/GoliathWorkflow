"""CLI for MethylDetectorExplorer: two-phase effect size analysis and optimization."""

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import click

try:
    from ..explorer import MethylDetectorExplorer
    from ..utils.core import setup_logging
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from methyl_detector.explorer import MethylDetectorExplorer
    from methyl_detector.utils.core import setup_logging

logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--centroid1-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    required=False,
    help="Directory containing centroid H5 files (e.g. {chrom}-{context}.h5).",
)
@click.option(
    "--centroid2-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    required=False,
    help="Directory containing second centroid H5 files.",
)
@click.option(
    "--centroid1",
    type=click.Path(path_type=Path, exists=True),
    required=False,
    help="Path to first centroid H5 file (alternative to centroid1-dir + chromosome + context).",
)
@click.option(
    "--centroid2",
    type=click.Path(path_type=Path, exists=True),
    required=False,
    help="Path to second centroid H5 file.",
)
@click.option(
    "--chromosome",
    default="1",
    help="Chromosome identifier (e.g. 1, 2, X). Used with centroid1-dir/centroid2-dir and --context.",
)
@click.option(
    "--context",
    default="CG",
    type=click.Choice(["CG", "CHG", "CHH"]),
    help="Methylation context. Used with centroid1-dir/centroid2-dir and --chromosome.",
)
@click.option(
    "--sample-fraction",
    type=float,
    default=0.01,
    help="Fraction of positions to use in Phase 1 (e.g. 0.01 = 1%%). Use 1.0 for all positions.",
)
@click.option(
    "--refine-top-k",
    type=int,
    default=None,
    help="Fixed number of top positions to refine with ECDF (overrides --k-heuristic).",
)
@click.option(
    "--k-heuristic",
    type=click.Choice(["decay_limit", "knee", "threshold", "fraction", "fixed"]),
    default="decay_limit",
    help="Heuristic to choose how many positions get refined effect_size.",
)
@click.option(
    "--max-decay-per-position",
    type=float,
    default=0.01,
    help="For decay_limit heuristic: max allowed decay rate per position before stopping K.",
)
@click.option(
    "--threshold-fraction",
    type=float,
    default=0.1,
    help="For threshold heuristic: keep positions with effect_size >= this fraction of max.",
)
@click.option(
    "--fraction-top",
    type=float,
    default=0.01,
    help="For fraction heuristic: fraction of (sorted) positions to refine.",
)
@click.option(
    "--min-coverage",
    type=int,
    default=4,
    help="Minimum coverage (min_coverage) for load_and_align.",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
    help="Output directory for report JSON and optional CSV.",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file path for report (JSON). Overrides --output-dir for report location.",
)
@click.option(
    "--csv",
    is_flag=True,
    default=False,
    help="Write result table to CSV in output-dir (or current dir if no output-dir).",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Enable verbose logging.",
)
def main(
    centroid1_dir: Optional[Path],
    centroid2_dir: Optional[Path],
    centroid1: Optional[Path],
    centroid2: Optional[Path],
    chromosome: str,
    context: str,
    sample_fraction: float,
    refine_top_k: Optional[int],
    k_heuristic: str,
    max_decay_per_position: float,
    threshold_fraction: float,
    fraction_top: float,
    min_coverage: int,
    output_dir: Optional[Path],
    output: Optional[Path],
    csv: bool,
    verbose: bool,
) -> None:
    """MethylDetectorExplorer: Analyze and optimize DMP detection with two-phase effect size.

    Phase 1: Approximate bounded_effect_size (delta_mean, variances, discrete overlap) for a
    sample of positions; sort descending. Phase 2: Choose K via decay analysis (or override),
    then compute refined bounded_effect_size using ECDF overlap only for the top K positions.
    """
    setup_logging(verbose=verbose)

    if centroid1 is not None and centroid2 is not None:
        c1_path = centroid1
        c2_path = centroid2
    elif centroid1_dir is not None and centroid2_dir is not None:
        c1_path = centroid1_dir / f"{chromosome}-{context}.h5"
        c2_path = centroid2_dir / f"{chromosome}-{context}.h5"
        if not c1_path.exists():
            click.echo(f"Error: {c1_path} not found.", err=True)
            sys.exit(1)
        if not c2_path.exists():
            click.echo(f"Error: {c2_path} not found.", err=True)
            sys.exit(1)
    else:
        click.echo(
            "Error: Provide either (--centroid1 and --centroid2) or (--centroid1-dir and --centroid2-dir).",
            err=True,
        )
        sys.exit(1)

    # User override: --refine-top-k forces K (use fixed heuristic)
    effective_heuristic = "fixed" if refine_top_k is not None else k_heuristic
    explorer = MethylDetectorExplorer(
        centroid1_path=c1_path,
        centroid2_path=c2_path,
        min_coverage=min_coverage,
        sample_fraction=sample_fraction,
        k_heuristic=effective_heuristic,
        refine_top_k=refine_top_k,
        max_decay_per_position=max_decay_per_position,
        threshold_fraction=threshold_fraction,
        fraction_top=fraction_top,
    )
    try:
        df, report = explorer.run()
    except Exception as e:
        logger.exception("MethylDetectorExplorer failed")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    out_dir = output_dir or Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = output if output is not None else (out_dir / "methyldetectorexplorer_report.json")
    if report_path.suffix != ".json":
        report_path = Path(str(report_path) + ".json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    click.echo(f"Report written to {report_path}")
    click.echo(
        f"Total positions: {report['total_positions']:,}, "
        f"Phase 1 sample: {report['phase1_sample_size']:,}, "
        f"K chosen: {report['k_chosen']}, "
        f"heuristic: {report['k_heuristic']}, "
        f"time: {report['time_total_s']:.2f}s"
    )

    if csv:
        csv_path = out_dir / "methyldetectorexplorer_results.csv"
        df.to_csv(csv_path, index=False)
        click.echo(f"Results CSV written to {csv_path}")


if __name__ == "__main__":
    main()
