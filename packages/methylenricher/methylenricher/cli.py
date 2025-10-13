"""
Command-line interface for MethylEnricher
"""

import argparse
import sys
from pathlib import Path

from .enricher import run_enrichment, DEFAULT_LIBRARIES


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="MethylEnricher - Gene enrichment analysis for methylation DMPs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic enrichment analysis
  methylenricher --input genes.txt --outdir results

  # Analyze top 100 genes with custom libraries
  methylenricher --input genes.txt --outdir results --top 100 \\
                 --libraries KEGG_2021_Human GO_Biological_Process_2023

  # Use stricter cutoff
  methylenricher --input genes.txt --outdir results --cutoff 0.01

For more information, visit: https://github.com/your-org/methylenricher
        """
    )
    
    # Input/Output arguments
    io_group = parser.add_argument_group('Input/Output')
    io_group.add_argument(
        '--input', '-i',
        type=str,
        required=True,
        help='Input file with gene symbols (one per line)'
    )
    io_group.add_argument(
        '--outdir', '-o',
        type=str,
        default='results',
        help='Output directory for results (default: results)'
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
    
    return parser.parse_args()


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
    
    # Handle --list-libraries
    if args.list_libraries:
        list_available_libraries()
        sys.exit(0)
    
    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERROR] Input file not found: {input_path}")
        sys.exit(1)
    
    # Display parameters
    print("=" * 70)
    print("MethylEnricher - Gene Enrichment Analysis")
    print("=" * 70)
    print(f"Input file: {input_path}")
    print(f"Output directory: {args.outdir}")
    print(f"Top genes: {args.top}")
    print(f"Cutoff: q ≤ {args.cutoff}")
    print(f"Organism: {args.organism}")
    
    if args.libraries:
        print(f"Libraries: {', '.join(args.libraries)}")
    else:
        print(f"Libraries: {len(DEFAULT_LIBRARIES)} default libraries")
    print("=" * 70)
    
    try:
        # Run enrichment analysis
        results = run_enrichment(
            input_file=input_path,
            output_dir=args.outdir,
            libraries=args.libraries,
            top_n=args.top,
            cutoff=args.cutoff,
            organism=args.organism
        )
        
        if results.empty:
            print("\n[WARN] No enrichment results found. Check your gene list and try again.")
            sys.exit(1)
        
        print(f"\n[SUCCESS] Enrichment analysis complete!")
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

