"""
Command-line interface for MethylEnricher
"""

import argparse
import json
import sys
from pathlib import Path

from .enricher import run_enrichment, DEFAULT_LIBRARIES
from .module_pipeline import run_module_pipeline


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="MethylEnricher - Gene enrichment analysis for methylation DMPs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # MethylMapper combined CSV: focus on disease-associated genes only
  methyl_enricher --input /path/to/all-gene_name-combined.csv --disease-only --top 200 --outdir results

  # PCa-focused: disease-associated, direct/indirect, minimum evidence and score
  methyl_enricher --input all-gene_name-combined.csv --gene-column gene_name \\
    --disease-only --disease-association-type direct indirect \\
    --min-disease-evidence-level medium --min-disease-score 0.2 \\
    --min-dmp-count 2 --max-gene-q-value 0.05 --top 150 --outdir enricher_pca

  # Sort by total_weight before selecting top genes
  methyl_enricher --input all-gene_name-combined.csv --gene-column gene_name \\
    --sort-by total_weight --top 200 --outdir results

  # Use a config file (CLI overrides config)
  methyl_enricher --config enricher_config.json
  methyl_enricher --config enricher_config.json --top 100 --outdir other_dir

For more information, visit: https://github.com/your-org/methyl_enricher
        """
    )
    
    # Input/Output arguments
    io_group = parser.add_argument_group('Input/Output')
    io_group.add_argument(
        '--config', '-C',
        type=str,
        default=None,
        metavar='JSON',
        help='Load options from JSON config file (CLI overrides config)'
    )
    io_group.add_argument(
        '--input', '-i',
        type=str,
        default=None,
        help='Input file with gene symbols (or set "input" in --config)'
    )
    io_group.add_argument(
        '--gene-column',
        type=str,
        default=None,
        help='Gene column name when input is CSV/TSV (default: auto-detect)'
    )
    io_group.add_argument(
        '--disease-only',
        action='store_true',
        help='When input is MethylMapper CSV, keep only disease_associated == True'
    )
    io_group.add_argument(
        '--disease-association-type',
        type=str,
        nargs='+',
        default=None,
        metavar='TYPE',
        help='Keep only these association types (e.g. direct indirect). Default: all'
    )
    io_group.add_argument(
        '--min-disease-evidence-level',
        type=str,
        choices=['low', 'medium', 'high'],
        default=None,
        help='Minimum disease_evidence_level (high = strictest)'
    )
    io_group.add_argument(
        '--min-disease-publications',
        type=int,
        default=None,
        metavar='N',
        help='Minimum disease_publications count'
    )
    io_group.add_argument(
        '--min-disease-score',
        type=float,
        default=None,
        metavar='S',
        help='Minimum disease_score (Open Targets)'
    )
    io_group.add_argument(
        '--min-dmp-count',
        type=int,
        default=None,
        metavar='N',
        help='Minimum dmp_count per gene'
    )
    io_group.add_argument(
        '--min-unique-dmps',
        type=int,
        default=None,
        metavar='N',
        help='Minimum unique_dmps per gene'
    )
    io_group.add_argument(
        '--max-gene-q-value',
        type=float,
        default=None,
        metavar='Q',
        help='Maximum gene_q_value (keep more significant genes)'
    )
    io_group.add_argument(
        '--min-mean-effect-size',
        type=float,
        default=None,
        metavar='E',
        help='Minimum mean_effect_size (or total_weight if present)'
    )
    io_group.add_argument(
        '--min-gene-z',
        type=float,
        default=None,
        metavar='Z',
        help='Minimum |gene_z| (effect strength)'
    )
    io_group.add_argument(
        '--min-gene-importance',
        type=float,
        default=None,
        metavar='I',
        help='Minimum gene_importance (or total_weight)'
    )
    io_group.add_argument(
        '--feature-types',
        type=str,
        nargs='+',
        default=None,
        metavar='TYPE',
        help='Keep only these feature_type values (e.g. gene exon)'
    )
    io_group.add_argument(
        '--sort-by',
        type=str,
        default=None,
        help='Column to sort by when input is CSV/TSV (default: auto total_weight if present)'
    )
    io_group.add_argument(
        '--sort-ascending',
        action='store_true',
        help='Sort ascending (default: descending)'
    )
    io_group.add_argument(
        '--outdir', '-o',
        type=str,
        default='results',
        help='Output directory for results (default: results)'
    )
    io_group.add_argument(
        '--project', '-p',
        type=str,
        default=None,
        metavar='JSON',
        help='Path to pipeline project config; sets input to mapper combined CSV and output to enricher dir'
    )
    io_group.add_argument(
        '--step-override',
        type=str,
        default=None,
        metavar='JSON',
        help='Optional JSON overrides for enricher step when using --project (e.g. input, output_dir)'
    )
    
    # Enrichment parameters
    enrich_group = parser.add_argument_group('Enrichment Parameters')
    enrich_group.add_argument(
        '--libraries', '-l',
        nargs='+',
        default=None,
        help=f'Enrichr libraries to query (default: {len(DEFAULT_LIBRARIES)} standard libraries)'
    )
    enrich_group.add_argument(
        '--top', '-t',
        type=int,
        default=200,
        help='Use only top N genes from the input list (default: 200)'
    )
    enrich_group.add_argument(
        '--cutoff', '-c',
        type=float,
        default=0.05,
        help='Adjusted p-value cutoff for filtering significant results (default: 0.05)'
    )
    enrich_group.add_argument(
        '--organism',
        type=str,
        default='Human',
        help='Organism for Enrichr analysis (default: Human)'
    )
    
    # Module pipeline (pathway-to-module)
    parser.add_argument(
        '--modules', '-m',
        action='store_true',
        help='Run pathway-to-module pipeline: cluster pathways into modules, score and rank, write modules_ranked.csv'
    )
    parser.add_argument(
        '--similarity-threshold',
        type=float,
        default=0.15,
        metavar='F',
        help='Pathway similarity threshold for clustering (default: 0.15). Lower values yield more edges and fewer, larger modules.'
    )
    parser.add_argument(
        '--cluster-resolution',
        type=float,
        default=0.8,
        metavar='F',
        help='Louvain cluster resolution (default: 0.8). Lower values yield fewer, larger modules. Tune with --similarity-threshold to target 3-5 modules.'
    )
    parser.add_argument(
        '--network-plot',
        type=str,
        default=None,
        choices=['none', 'plotly', 'pyvis', 'cytoscape', 'all'],
        metavar='MODE',
        help='When --modules: generate network plot. none=skip; plotly=Plotly HTML (default when -m); pyvis=PyVis HTML; cytoscape=Cytoscape.js HTML+JSON; all=all three.'
    )

    # Other options
    parser.add_argument(
        '--list-libraries',
        action='store_true',
        help='List all available Enrichr libraries and exit'
    )
    parser.add_argument(
        '--version',
        action='version',
        version='MethylEnricher 0.1.0'
    )

    # Apply config file before parsing so CLI overrides config
    argv = sys.argv[1:]
    config_path = None
    for i, a in enumerate(argv):
        if a in ("--config", "-C") and i + 1 < len(argv):
            config_path = Path(argv[i + 1])
            break
    if config_path and config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        ns = argparse.Namespace()
        for action in parser._actions:
            if getattr(action, "dest", None) and action.dest not in ("help",) and not action.dest.startswith("_"):
                ns.__setattr__(action.dest, action.default)
        for key, value in cfg.items():
            attr = key.replace("-", "_")
            if hasattr(ns, attr):
                ns.__setattr__(attr, value)
        return parser.parse_args(namespace=ns)
    return parser.parse_args()


def _apply_enricher_config_to_args(args, config: "EnricherStepConfig") -> None:
    """Apply EnricherStepConfig to parsed args (config values override only when set)."""
    from .config import EnricherStepConfig
    # I/O: config may use input_file/input, output_dir/outdir
    if config.input_file is not None:
        args.input = config.input_file
    if config.input is not None:
        args.input = config.input
    if config.output_dir is not None:
        args.outdir = config.output_dir
    if config.outdir is not None:
        args.outdir = config.outdir
    # Rest: same attribute name as args
    for name in EnricherStepConfig.model_fields:
        if name in ("input", "input_file", "output_dir", "outdir"):
            continue
        val = getattr(config, name, None)
        if val is None:
            continue
        if hasattr(args, name):
            setattr(args, name, val)


def list_available_libraries():
    """List all available Enrichr libraries."""
    try:
        import gseapy as gp
    except ImportError:
        print("[ERROR] gseapy is required. Install with: pip install gseapy")
        sys.exit(1)
    
    print("Available Enrichr libraries:")
    print("=" * 70)
    
    try:
        libraries = gp.get_library_name(organism='Human')
        for i, lib in enumerate(libraries, 1):
            print(f"{i:3d}. {lib}")
        print("=" * 70)
        print(f"Total: {len(libraries)} libraries available")
    except Exception as e:
        print(f"[ERROR] Could not retrieve library list: {e}")
        sys.exit(1)


def main():
    """Main entry point for MethylEnricher CLI."""
    args = parse_args()

    # Resolve paths and apply step_config from --project if set
    if args.project:
        from methyl_utils import load_project
        from .project_resolver import resolve_enricher_paths, resolve_enricher_paths_per_cancer_group
        from .config import EnricherStepConfig
        project_path = Path(args.project)
        if not project_path.exists() and not project_path.is_absolute():
            # When run from a package dir (e.g. packages/methylenricher), try repo root
            _repo_root = Path(__file__).resolve().parent.parent.parent.parent
            _alt = (_repo_root / args.project).resolve()
            if _alt.exists():
                project_path = _alt
        if not project_path.exists():
            print(f"[ERROR] Project config not found: {project_path}")
            sys.exit(1)
        project = load_project(project_path)
        step_cfg = project.get_step_config("enricher")
        if step_cfg:
            enricher_config = EnricherStepConfig.model_validate(step_cfg)
            _apply_enricher_config_to_args(args, enricher_config)
        step_override = Path(args.step_override) if args.step_override else None
        # Use per-cancer-group layout (enricher/cancer/<label> per group) when project has multiple groups
        per_group = resolve_enricher_paths_per_cancer_group(project_path, step_override)
        if per_group and args.input is None and (args.outdir == "results" or args.outdir is None):
            args.enricher_per_group = per_group
            args.input = None
            args.outdir = None
        elif per_group and (args.input is not None or (args.outdir != "results" and args.outdir is not None)):
            # Explicit --input or --outdir: single run, clear per-group
            args.enricher_per_group = None
            paths = resolve_enricher_paths(project_path, step_override)
            if not args.input:
                args.input = paths.input_file
            if args.outdir == "results" or args.outdir is None:
                args.outdir = paths.output_dir
        else:
            args.enricher_per_group = None
            paths = resolve_enricher_paths(project_path, step_override)
            if not args.input:
                args.input = paths.input_file
            if args.outdir == "results":  # default only
                args.outdir = paths.output_dir
    
    # Handle --list-libraries
    if args.list_libraries:
        list_available_libraries()
        sys.exit(0)

    per_group = getattr(args, "enricher_per_group", None)
    if not per_group and not args.input:
        print("[ERROR] Input file not specified. Use --input /path/to/file or set 'input' in --config.")
        sys.exit(1)

    # Display parameters
    print("=" * 70)
    print("MethylEnricher - Gene Enrichment Analysis")
    print("=" * 70)
    if per_group:
        print(f"Per-cancer-group: {len(per_group)} group(s) -> enricher/cancer/<group>")
        input_path = None
    else:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"[ERROR] Input file not found: {input_path}")
            sys.exit(1)
        print(f"Input file: {input_path}")
        print(f"Output directory: {args.outdir}")
    print(f"Top genes: {args.top}")
    print(f"Cutoff: q ≤ {args.cutoff}")
    print(f"Organism: {args.organism}")
    if args.gene_column:
        print(f"Gene column: {args.gene_column}")
    if args.sort_by:
        print(f"Sort by: {args.sort_by} ({'asc' if args.sort_ascending else 'desc'})")
    if args.disease_only:
        print("Filter: disease_associated = True")
    if args.disease_association_type:
        print(f"Filter: disease_association_type in {args.disease_association_type}")
    if args.min_disease_evidence_level:
        print(f"Filter: disease_evidence_level >= {args.min_disease_evidence_level}")
    if args.min_disease_publications is not None:
        print(f"Filter: disease_publications >= {args.min_disease_publications}")
    if args.min_disease_score is not None:
        print(f"Filter: disease_score >= {args.min_disease_score}")
    if args.min_dmp_count is not None:
        print(f"Filter: dmp_count >= {args.min_dmp_count}")
    if args.max_gene_q_value is not None:
        print(f"Filter: gene_q_value <= {args.max_gene_q_value}")
    if args.min_mean_effect_size is not None:
        print(f"Filter: mean_effect_size >= {args.min_mean_effect_size}")
    if args.min_gene_importance is not None:
        print(f"Filter: gene_importance >= {args.min_gene_importance}")
    if args.feature_types:
        print(f"Filter: feature_type in {args.feature_types}")
    
    if args.libraries:
        print(f"Libraries: {', '.join(args.libraries)}")
    else:
        print(f"Libraries: {len(DEFAULT_LIBRARIES)} default libraries")
    if getattr(args, "modules", False):
        print("Mode: pathway-to-module pipeline (output: modules_ranked.csv)")
        print(f"Similarity threshold: {getattr(args, 'similarity_threshold', 0.15)}")
        print(f"Cluster resolution: {getattr(args, 'cluster_resolution', 0.8)}")
        _np = getattr(args, "network_plot", None)
        effective_network_plot = "plotly" if _np is None else _np
        if effective_network_plot and effective_network_plot.lower() != "none":
            print(f"Network plot: {effective_network_plot}")
    print("=" * 70)
    
    def _run_one(in_file: Path, out_dir: str):
        if getattr(args, "modules", False):
            _np = getattr(args, "network_plot", None)
            effective_network_plot = "plotly" if _np is None else _np
            return run_module_pipeline(
                input_path=in_file,
                output_dir=Path(out_dir),
                gene_column=args.gene_column,
                top_n=args.top,
                libraries=args.libraries,
                organism=args.organism,
                cutoff=args.cutoff,
                disease_only=args.disease_only,
                disease_association_types=args.disease_association_type,
                min_disease_evidence_level=args.min_disease_evidence_level,
                min_disease_publications=args.min_disease_publications,
                min_disease_score=args.min_disease_score,
                min_dmp_count=args.min_dmp_count,
                min_unique_dmps=args.min_unique_dmps,
                max_gene_q_value=args.max_gene_q_value,
                min_mean_effect_size=args.min_mean_effect_size,
                min_gene_z=args.min_gene_z,
                min_gene_importance=args.min_gene_importance,
                feature_types=args.feature_types,
                sort_by=args.sort_by,
                sort_ascending=args.sort_ascending,
                similarity_threshold=getattr(args, "similarity_threshold", 0.15),
                cluster_resolution=getattr(args, "cluster_resolution", 0.8),
                network_plot=effective_network_plot,
            )
        return run_enrichment(
            input_file=in_file,
            output_dir=out_dir,
            libraries=args.libraries,
            top_n=args.top,
            cutoff=args.cutoff,
            organism=args.organism,
            gene_column=args.gene_column,
            disease_only=args.disease_only,
            disease_association_types=args.disease_association_type,
            min_disease_evidence_level=args.min_disease_evidence_level,
            min_disease_publications=args.min_disease_publications,
            min_disease_score=args.min_disease_score,
            min_dmp_count=args.min_dmp_count,
            min_unique_dmps=args.min_unique_dmps,
            max_gene_q_value=args.max_gene_q_value,
            min_mean_effect_size=args.min_mean_effect_size,
            min_gene_z=args.min_gene_z,
            min_gene_importance=args.min_gene_importance,
            feature_types=args.feature_types,
            sort_by=args.sort_by,
            sort_ascending=args.sort_ascending
        )

    try:
        if per_group:
            # Run enrichment once per cancer group (input from mapper/cancer/<label>, output to enricher/cancer/<label>)
            for paths, label in per_group:
                inp = Path(paths.input_file)
                if not inp.exists():
                    print(f"[WARN] Skipping group {label}: input not found: {inp}")
                    continue
                print(f"\n--- Enrichment for group: {label} -> {paths.output_dir} ---")
                try:
                    results = _run_one(inp, paths.output_dir)
                except ValueError as e:
                    if "No genes left after filters" in str(e):
                        print(f"[WARN] Skipping group {label}: {e}")
                        continue
                    raise
                if results.empty:
                    print(f"[WARN] No enrichment results for {label}.")
                else:
                    print(f"[OK] {label}: results saved to {paths.output_dir}")
            msg = "Per-cancer-group module pipeline complete!" if getattr(args, "modules", False) else "Per-cancer-group enrichment complete!"
            print(f"\n[SUCCESS] {msg}")
            sys.exit(0)
        else:
            results = _run_one(input_path, args.outdir)
            if results.empty:
                print("\n[WARN] No enrichment results found. Check your gene list and try again.")
                sys.exit(1)
            if getattr(args, "modules", False):
                print("\n[SUCCESS] Pathway-to-module pipeline complete!")
                print(f"Results saved to: {args.outdir} (including modules_ranked.csv)")
            else:
                print("\n[SUCCESS] Enrichment analysis complete!")
                print(f"Results saved to: {args.outdir}")
            sys.exit(0)

    except KeyboardInterrupt:
        print("\n\n[WARN] Analysis interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n[ERROR] Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

