"""
Command-line interface for MethylMapper
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import MethylMapperConfig, AzureSQLConfig, StoredProcedureConfig
from .mapper import DMPMapper


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='[%(levelname)s] %(message)s'
    )


def load_config_from_json(config_path: Path) -> MethylMapperConfig:
    """Load configuration from JSON file."""
    with open(config_path) as f:
        config_dict = json.load(f)
    
    return MethylMapperConfig(**config_dict)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="MethylMapper - Map DMPs to genes using Azure SQL Database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with config file
  methylmapper --input dmps.csv --config db_config.json --sample-id 12345

  # Override output paths
  methylmapper --input dmps.csv --config db_config.json --sample-id 12345 \\
               --output-csv results.csv --output-json genes.json

  # Override chromosome and context
  methylmapper --input dmps.csv --config db_config.json --sample-id 12345 \\
               --chromosome chr1 --context CG

  # Customize stored procedure parameters
  methylmapper --input dmps.csv --config db_config.json --sample-id 12345 \\
               --upstream-size 10000 --w-promoter 3.0

For more information, visit: https://github.com/your-org/methylmapper
        """
    )
    
    # Required arguments
    required = parser.add_argument_group('Required Arguments')
    required.add_argument(
        '--input', '-i',
        type=str,
        required=True,
        help='Input DMP CSV file path'
    )
    required.add_argument(
        '--config', '-c',
        type=str,
        required=True,
        help='JSON configuration file with database connection details'
    )
    required.add_argument(
        '--sample-id', '-s',
        type=int,
        required=True,
        help='Sample ID for database tracking'
    )
    
    # Output options
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument(
        '--output-csv',
        type=str,
        default='mapped_genes.csv',
        help='Output CSV file path for full results (default: mapped_genes.csv)'
    )
    output_group.add_argument(
        '--output-json',
        type=str,
        default='mapped_genes.json',
        help='Output JSON file path for gene names (default: mapped_genes.json)'
    )
    
    # Data options
    data_group = parser.add_argument_group('Data Options')
    data_group.add_argument(
        '--chromosome',
        type=str,
        default=None,
        help='Override chromosome from CSV'
    )
    data_group.add_argument(
        '--context',
        type=str,
        default=None,
        help='Override methylation context from CSV'
    )
    
    # Stored procedure parameters
    sp_group = parser.add_argument_group('Stored Procedure Parameters')
    sp_group.add_argument(
        '--upstream-size',
        type=int,
        default=None,
        help='Upstream region size for promoter mapping (default: 5000 bp)'
    )
    sp_group.add_argument(
        '--downstream-size',
        type=int,
        default=None,
        help='Downstream region size for terminator mapping (default: 2000 bp)'
    )
    sp_group.add_argument(
        '--min-intron-size',
        type=int,
        default=None,
        help='Minimum intron size to consider (default: 0 bp)'
    )
    sp_group.add_argument(
        '--w-promoter',
        type=float,
        default=None,
        help='Weight for promoter region DMPs (default: 2.0)'
    )
    sp_group.add_argument(
        '--w-terminator',
        type=float,
        default=None,
        help='Weight for terminator region DMPs (default: 0.5)'
    )
    sp_group.add_argument(
        '--w-gene-body',
        type=float,
        default=None,
        help='Weight for gene body DMPs (default: 1.0)'
    )
    sp_group.add_argument(
        '--w-exon',
        type=float,
        default=None,
        help='Weight for exon DMPs (default: 1.5)'
    )
    sp_group.add_argument(
        '--w-intron',
        type=float,
        default=None,
        help='Weight for intron DMPs (default: 0.7)'
    )
    sp_group.add_argument(
        '--w-unknown',
        type=float,
        default=None,
        help='Weight for unknown region DMPs (default: 1.0)'
    )
    
    # Other options
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--version',
        action='version',
        version='MethylMapper 0.1.0'
    )
    
    return parser.parse_args()


def main():
    """Main entry point for MethylMapper CLI."""
    args = parse_args()
    
    # Setup logging
    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)
    
    try:
        # Load configuration from JSON
        config_path = Path(args.config)
        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_path}")
            sys.exit(1)
        
        config = load_config_from_json(config_path)
        
        # Override stored procedure parameters from CLI if specified
        sp_config = config.stored_procedure
        if args.upstream_size is not None:
            sp_config.upstream_size = args.upstream_size
        if args.downstream_size is not None:
            sp_config.downstream_size = args.downstream_size
        if args.min_intron_size is not None:
            sp_config.min_intron_size = args.min_intron_size
        if args.w_promoter is not None:
            sp_config.w_promoter = args.w_promoter
        if args.w_terminator is not None:
            sp_config.w_terminator = args.w_terminator
        if args.w_gene_body is not None:
            sp_config.w_gene_body = args.w_gene_body
        if args.w_exon is not None:
            sp_config.w_exon = args.w_exon
        if args.w_intron is not None:
            sp_config.w_intron = args.w_intron
        if args.w_unknown is not None:
            sp_config.w_unknown = args.w_unknown
        
        # Create mapper
        mapper = DMPMapper(config)
        
        # Run pipeline
        results = mapper.run(
            input_csv=Path(args.input),
            output_csv=Path(args.output_csv),
            output_json=Path(args.output_json),
            sample_id=args.sample_id,
            chromosome=args.chromosome,
            context=args.context,
            sp_config=sp_config
        )
        
        logger.info("\n🎉 SUCCESS! DMP-to-gene mapping complete.")
        sys.exit(0)
        
    except KeyboardInterrupt:
        logger.warning("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\n❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

