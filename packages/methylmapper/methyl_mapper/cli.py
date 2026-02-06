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
from .bedtools_mapper import BedtoolsMapper
from .secure_credentials import SecureCredentialManager


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
  methyl_mapper --input dmps.csv --config db_config.json --sample-id 12345

  # Override output paths
  methyl_mapper --input dmps.csv --config db_config.json --sample-id 12345 \\
               --output-csv results.csv --output-json genes.json

  # Override chromosome and context
  methyl_mapper --input dmps.csv --config db_config.json --sample-id 12345 \\
               --chromosome chr1 --context CG

  # Customize stored procedure parameters
  methyl_mapper --input dmps.csv --config db_config.json --sample-id 12345 \\
               --upstream-size 10000 --w-promoter 3.0

For more information, visit: https://github.com/your-org/methyl_mapper
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


def parse_bedtools_args():
    """Parse command-line arguments for bedtools-based mapping."""
    parser = argparse.ArgumentParser(
        description="MethylMapper Bedtools - Map DMPs to genomic features using bedtools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Map optimized DMPs from all chromosomes
  methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" --gtf gencode.v44.annotation.gtf
  
  # Map with custom output directory
  methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" --gtf gencode.v44.annotation.gtf \\
                         --output-dir mapped_features
  
  # Group by transcript instead of gene
  methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" --gtf gencode.v44.annotation.gtf \\
                         --group-by transcript_id
  
  # Disable weighting by p-value
  methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" --gtf gencode.v44.annotation.gtf \\
                         --no-p-value-weight

For more information, visit: https://github.com/your-org/methyl_mapper
        """
    )
    
    # Required arguments
    required = parser.add_argument_group('Required Arguments')
    required.add_argument(
        '--csv-pattern', '-p',
        type=str,
        default=None,
        help='Glob pattern for CSV files (or set csv_pattern in --config)'
    )
    required.add_argument(
        '--gtf', '-g',
        type=str,
        default=None,
        help='Path to GTF/GFF annotation file (default: from --config, or GENE_GTF env)'
    )
    
    # Output options
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument(
        '--output-dir', '-o',
        type=str,
        default=None,
        help='Output directory for results (default: creates "mapped_features" in CSV directory)'
    )
    output_group.add_argument(
        '--group-by',
        type=str,
        default='gene_name',
        choices=['gene_name', 'gene_id', 'transcript_id', 'transcript_name', 'feature_type'],
        help='Feature to group by for aggregation (default: gene_name)'
    )
    
    # Weighting options
    weight_group = parser.add_argument_group('Weighting Options')
    weight_group.add_argument(
        '--no-p-value-weight',
        action='store_true',
        help='Disable weighting by p-value'
    )
    weight_group.add_argument(
        '--no-q-value-weight',
        action='store_true',
        help='Disable weighting by q-value'
    )
    weight_group.add_argument(
        '--no-effect-size-weight',
        action='store_true',
        help='Disable weighting by effect_size'
    )
    weight_group.add_argument(
        '--no-log-transform',
        action='store_true',
        help='Disable log10 transformation for p-values (use 1/p instead)'
    )
    
    # Feature filtering
    feature_group = parser.add_argument_group('Feature Filtering')
    feature_group.add_argument(
        '--feature-types',
        type=str,
        nargs='+',
        default=None,
        help='Feature types to include (e.g., gene exon intron). If not specified, defaults to gene only.'
    )
    
    # Disease enrichment options
    disease_group = parser.add_argument_group('Disease Enrichment Options')
    disease_group.add_argument(
        '--enrich-disease',
        action='store_true',
        help='Enable disease association enrichment'
    )
    disease_group.add_argument(
        '--enrich-source',
        type=str,
        choices=['grok', 'disgenet', 'both', 'opentargets', 'grok+opentargets', 'grok+disgenet', 'all'],
        default='grok+opentargets',
        help='Source(s) for disease enrichment (default: grok+opentargets)'
    )
    disease_group.add_argument(
        '--separate-enrichment-sources',
        action='store_true',
        help='Export separate CSV files for each enrichment source when using --enrich-source both'
    )
    disease_group.add_argument(
        '--disease-term',
        type=str,
        default=None,
        help='Disease term for enrichment (e.g. "Prostate Cancer"). Default: METHYL_MAPPER_DISEASE_TERM env, or "early-stage prostate cancer")'
    )
    disease_group.add_argument(
        '--grok-api-key',
        type=str,
        default=None,
        help='Grok API key (optional, uses secure storage if not provided)'
    )
    disease_group.add_argument(
        '--disgenet-api-key',
        type=str,
        default=None,
        help='DisGeNET API key (optional, uses secure storage if not provided)'
    )
    disease_group.add_argument(
        '--azure-key-vault-url',
        type=str,
        default=None,
        help='Azure Key Vault URL (or set AZURE_KEY_VAULT_URL env var)'
    )
    disease_group.add_argument(
        '--azure-secret-name',
        type=str,
        default=None,
        help='Azure Key Vault secret name (or set AZURE_SECRET_NAME env var, default: grok_api_key for Grok, disgenet_api_key for DisGeNET)'
    )
    disease_group.add_argument(
        '--encrypted-file-path',
        type=str,
        default=None,
        help='Path to encrypted credential file (default: ~/.methyl_mapper/credentials/{source}_api_key.encrypted)'
    )
    disease_group.add_argument(
        '--enrich-profile',
        type=str,
        choices=['strict', 'balanced', 'permissive'],
        default='balanced',
        help='Preset enrichment threshold profile (default: balanced)'
    )
    disease_group.add_argument(
        '--min-evidence-level',
        type=str,
        choices=['none', 'low', 'medium', 'high'],
        default=None,
        help='Minimum evidence level to count as disease-associated (overrides --enrich-profile)'
    )
    disease_group.add_argument(
        '--min-publications',
        type=int,
        default=None,
        help='Minimum number of publications required (overrides --enrich-profile)'
    )
    disease_group.add_argument(
        '--min-disgenet-score',
        type=float,
        default=None,
        help='Minimum DisGeNET score required (overrides --enrich-profile)'
    )
    disease_group.add_argument(
        '--allow-predicted',
        action='store_true',
        default=None,
        help='Allow predicted associations (overrides --enrich-profile)'
    )
    disease_group.add_argument(
        '--no-cache',
        action='store_true',
        help='Disable disk cache for enrichment queries'
    )
    disease_group.add_argument(
        '--cache-dir',
        type=str,
        default=None,
        help='Cache directory for enrichment queries (default: ~/.methyl_mapper/cache)'
    )
    disease_group.add_argument(
        '--cache-ttl-days',
        type=int,
        default=7,
        help='Cache TTL in days (default: 7, 0 disables TTL)'
    )
    
    # DMP optimization options
    optimization_group = parser.add_argument_group('DMP Optimization Options')
    optimization_group.add_argument(
        '--no-optimize-dmps',
        action='store_true',
        help='Disable DMP optimization (use all DMPs)'
    )
    optimization_group.add_argument(
        '--dmp-rank-columns',
        type=str,
        nargs='+',
        default=None,
        help='Columns to rank DMPs by importance (default: importance effect_size delta_mean weight)'
    )
    optimization_group.add_argument(
        '--min-k',
        type=int,
        default=10,
        help='Minimum number of DMPs to test (default: 10)'
    )
    optimization_group.add_argument(
        '--max-k',
        type=int,
        default=None,
        help='Maximum number of DMPs to test (default: all available)'
    )
    optimization_group.add_argument(
        '--stability-threshold',
        type=int,
        default=3,
        help='Number of consecutive iterations without new disease genes to consider stable (default: 3)'
    )
    optimization_group.add_argument(
        '--unrelated-growth-threshold',
        type=float,
        default=0.10,
        help='Growth rate threshold for unrelated genes (default: 0.10 = 10%%)'
    )
    
    # Other options
    parser.add_argument(
        '--config', '-c',
        type=str,
        default=None,
        help='Optional JSON config file. May set csv_pattern, gtf, output_dir, feature_types, disease_term, enrich_disease, enrich_source, enrich_profile (overridden by CLI args)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--version',
        action='version',
        version='MethylMapper Bedtools 0.1.0'
    )
    
    args = parser.parse_args()

    # Apply optional config file (CLI args take precedence)
    if args.config:
        config_path = Path(args.config)
        if config_path.exists():
            with open(config_path) as f:
                cfg = json.load(f)
            if cfg.get('csv_pattern') is not None and args.csv_pattern is None:
                args.csv_pattern = cfg['csv_pattern']
            if cfg.get('disease_term') is not None and args.disease_term is None:
                args.disease_term = cfg['disease_term']
            if cfg.get('gtf') is not None and args.gtf is None:
                args.gtf = cfg['gtf']
            if cfg.get('output_dir') is not None and args.output_dir is None:
                args.output_dir = cfg['output_dir']
            if cfg.get('enrich_disease') is True and not args.enrich_disease:
                args.enrich_disease = True
            if cfg.get('enrich_source') is not None:
                args.enrich_source = cfg['enrich_source']
            if cfg.get('enrich_profile') is not None:
                args.enrich_profile = cfg['enrich_profile']
            if cfg.get('grok_api_key') is not None and args.grok_api_key is None:
                args.grok_api_key = cfg['grok_api_key']
            # optimize_dmps: false in config => no_optimize_dmps
            if cfg.get('optimize_dmps') is False and not args.no_optimize_dmps:
                args.no_optimize_dmps = True
            if cfg.get('feature_types') is not None and args.feature_types is None:
                args.feature_types = cfg['feature_types']

    return args


def main_bedtools():
    """Main entry point for bedtools-based mapping CLI."""
    import os
    
    args = parse_bedtools_args()
    
    # Setup logging
    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)
    
    if not args.csv_pattern:
        logger.error("CSV pattern not specified. Use --csv-pattern or set csv_pattern in --config.")
        sys.exit(1)
    
    try:
        # Get GTF file path (must be a file, not a directory or placeholder)
        gtf_path = args.gtf
        if not gtf_path or str(gtf_path).strip() in ('', '.'):
            gtf_path = None
        if gtf_path is None:
            gtf_path = os.environ.get('GENE_GTF')
            if gtf_path:
                gtf_path = str(gtf_path).strip()
                if gtf_path in ('', '.'):
                    gtf_path = None
        if gtf_path is None:
            logger.error("GTF file not specified. Use --gtf /path/to/file.gtf or set GENE_GTF to the GTF file path.")
            sys.exit(1)
        gtf_path = Path(gtf_path)
        if not gtf_path.exists():
            logger.error(f"GTF file not found: {gtf_path}")
            sys.exit(1)
        if gtf_path.is_dir():
            logger.error(f"GTF path is a directory, not a file: {gtf_path}. Point --gtf or GENE_GTF to a .gtf file.")
            sys.exit(1)
        
        logger.info("="*70)
        logger.info("MethylMapper Bedtools - DMP to Feature Mapping")
        logger.info("="*70)
        # Resolve disease term: CLI > config > env > literal default
        had_explicit_disease_term = bool(args.disease_term or os.environ.get('METHYL_MAPPER_DISEASE_TERM'))
        disease_term = args.disease_term or os.environ.get('METHYL_MAPPER_DISEASE_TERM') or 'early-stage prostate cancer'
        args.disease_term = disease_term

        # If user set a disease term but did not pass --enrich-disease, enable enrichment so Grok/Open Targets columns are added
        if had_explicit_disease_term and not args.enrich_disease:
            args.enrich_disease = True
            logger.info("Disease term set; enabling disease enrichment (Grok/Open Targets) to add gene-disease columns.")

        logger.info(f"CSV pattern: {args.csv_pattern}")
        logger.info(f"GTF file: {gtf_path}")
        logger.info(f"Group by: {args.group_by}")
        if args.enrich_disease:
            logger.info(f"Disease enrichment: Enabled ({disease_term})")
        if not args.no_optimize_dmps and args.enrich_disease:
            logger.info(f"DMP optimization: Enabled (min_k={args.min_k}, stability_threshold={args.stability_threshold})")
        logger.info("="*70)
        
        # Create mapper
        mapper = BedtoolsMapper(
            gene_gtf=gtf_path,
            feature_types=args.feature_types,
            use_p_value_weight=not args.no_p_value_weight,
            use_q_value_weight=not args.no_q_value_weight,
            use_effect_size_weight=not args.no_effect_size_weight,
            p_value_log_transform=not args.no_log_transform,
            enrich_disease=args.enrich_disease,
            enrich_source=args.enrich_source,
            separate_enrichment_sources=args.separate_enrichment_sources,
            disease_term=args.disease_term,
            grok_api_key=args.grok_api_key,
            disgenet_api_key=args.disgenet_api_key,
            enrichment_profile=args.enrich_profile,
            min_evidence_level=args.min_evidence_level,
            min_publications=args.min_publications,
            min_disgenet_score=args.min_disgenet_score,
            allow_predicted=args.allow_predicted,
            cache_enabled=not args.no_cache,
            cache_dir=Path(args.cache_dir) if args.cache_dir else None,
            cache_ttl_days=args.cache_ttl_days,
            azure_key_vault_url=args.azure_key_vault_url or os.environ.get('AZURE_KEY_VAULT_URL'),
            azure_secret_name=args.azure_secret_name or os.environ.get('AZURE_SECRET_NAME'),
            encrypted_file_path=Path(args.encrypted_file_path) if args.encrypted_file_path else None,
            optimize_dmps=not args.no_optimize_dmps,
            dmp_rank_columns=args.dmp_rank_columns,
            min_k=args.min_k,
            max_k=args.max_k,
            stability_threshold=args.stability_threshold,
            unrelated_growth_threshold=args.unrelated_growth_threshold
        )
        
        # Determine output directory
        output_dir = Path(args.output_dir) if args.output_dir else None
        
        # Map CSV files
        results = mapper.map_csv_files(
            csv_pattern=args.csv_pattern,
            output_dir=output_dir,
            group_by=args.group_by
        )
        
        logger.info("\n" + "="*70)
        logger.info("✅ Bedtools mapping complete!")
        logger.info("="*70)
        logger.info(f"Processed {len(results)} CSV files")
        if results:
            total_genes = sum(len(df) for df in results.values())
            logger.info(f"Found {total_genes} unique {args.group_by}s across all files")
        logger.info("="*70)
        
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



def parse_credentials_args():
    """Parse command-line arguments for credential management."""
    parser = argparse.ArgumentParser(
        description="MethylMapper Credentials - Manage API keys securely",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Save Grok API key to encrypted local file
  methyl_mapper_credentials save --credential-type grok --api-key "your-grok-api-key"
  
  # Save DisGeNET API key
  methyl_mapper_credentials save --credential-type disgenet --api-key "your-disgenet-api-key"
  
  # Save Azure SQL password
  methyl_mapper_credentials save --credential-type azure_sql --api-key "your-db-password"
  
  # Save Grok API key to Azure Key Vault
  methyl_mapper_credentials save --credential-type grok --api-key "your-key" \\
                                  --azure-key-vault-url "https://vault.vault.azure.net/" \\
                                  --use-azure
  
  # Test credential retrieval
  methyl_mapper_credentials test --credential-type grok
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Save command
    save_parser = subparsers.add_parser('save', help='Save API key securely')
    save_parser.add_argument(
        '--credential-type',
        type=str,
        choices=['grok', 'disgenet', 'azure_sql'],
        default='grok',
        help='Type of credential to save (default: grok)'
    )
    save_parser.add_argument('--api-key', type=str, required=True, help='API key/credential value to save')
    save_parser.add_argument('--azure-key-vault-url', type=str, default=None, help='Azure Key Vault URL (or set AZURE_KEY_VAULT_URL env var)')
    save_parser.add_argument('--azure-secret-name', type=str, default=None, help='Azure Key Vault secret name (overrides default based on credential type)')
    save_parser.add_argument('--encrypted-file-path', type=str, default=None, help='Path to encrypted credential file (overrides default based on credential type)')
    save_parser.add_argument('--use-azure', action='store_true', help='Save to Azure Key Vault')
    save_parser.add_argument('--use-encrypted-file', action='store_true', default=True, help='Save to encrypted local file (default: True)')
    save_parser.add_argument('--password', type=str, default=None, help='Password for encryption (or set METHYL_MAPPER_CREDENTIAL_PASSWORD env var)')
    
    # Test command
    test_parser = subparsers.add_parser('test', help='Test credential retrieval')
    test_parser.add_argument(
        '--credential-type',
        type=str,
        choices=['grok', 'disgenet', 'azure_sql'],
        default='grok',
        help='Type of credential to test (default: grok)'
    )
    test_parser.add_argument('--azure-key-vault-url', type=str, default=None, help='Azure Key Vault URL (or set AZURE_KEY_VAULT_URL env var)')
    test_parser.add_argument('--azure-secret-name', type=str, default=None, help='Azure Key Vault secret name (overrides default based on credential type)')
    test_parser.add_argument('--encrypted-file-path', type=str, default=None, help='Path to encrypted credential file (overrides default based on credential type)')
    
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    return parser.parse_args()


def main_credentials():
    """Main entry point for credential management CLI."""
    import os
    
    args = parse_credentials_args()
    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)
    
    if not args.command:
        logger.error("Please specify a command: 'save' or 'test'")
        sys.exit(1)
    
    # Map credential types to configuration
    credential_configs = {
        'grok': {
            'name': 'grok_api_key',
            'env_var': 'GROK_API_KEY',
            'display_name': 'Grok API Key'
        },
        'disgenet': {
            'name': 'disgenet_api_key',
            'env_var': 'DISGENET_API_KEY',
            'display_name': 'DisGeNET API Key'
        },
        'azure_sql': {
            'name': 'azure_sql_password',
            'env_var': 'AZURE_SQL_PASSWORD',
            'display_name': 'Azure SQL Password'
        }
    }
    
    cred_type = args.credential_type
    config = credential_configs[cred_type]
    
    # Determine Azure secret name (default to credential name if not provided)
    azure_secret_name = args.azure_secret_name or config['name']
    
    # Determine encrypted file path (default based on credential type if not provided)
    encrypted_file_path = None
    if args.encrypted_file_path:
        encrypted_file_path = Path(args.encrypted_file_path)
    else:
        # Use default path based on credential type
        encrypted_file_path = None  # Will use SecureCredentialManager default
    
    try:
        credential_manager = SecureCredentialManager(
            credential_name=config['name'],
            azure_key_vault_url=args.azure_key_vault_url or os.environ.get('AZURE_KEY_VAULT_URL'),
            azure_secret_name=azure_secret_name,
            encrypted_file_path=encrypted_file_path,
            env_var_name=config['env_var']
        )
        
        if args.command == 'save':
            logger.info("="*70)
            logger.info(f"Saving {config['display_name']} Securely")
            logger.info("="*70)
            
            success = credential_manager.save_credential(
                value=args.api_key,
                use_azure=args.use_azure,
                use_encrypted_file=args.use_encrypted_file,
                password=args.password or os.environ.get('METHYL_MAPPER_CREDENTIAL_PASSWORD')
            )
            
            if success:
                logger.info(f"✅ {config['display_name']} saved successfully!")
                logger.info(f"   Encrypted file: {credential_manager.encrypted_file_path}")
                if args.use_azure:
                    logger.info(f"   Azure Key Vault: {credential_manager.azure_key_vault_url}")
                    logger.info(f"   Secret name: {azure_secret_name}")
            else:
                logger.error(f"❌ Failed to save {config['display_name']}")
                sys.exit(1)
        
        elif args.command == 'test':
            logger.info("="*70)
            logger.info(f"Testing {config['display_name']} Retrieval")
            logger.info("="*70)
            
            api_key = credential_manager.get_credential()
            
            if api_key:
                logger.info(f"✅ {config['display_name']} retrieved successfully!")
                logger.info(f"   Key preview: {api_key[:20]}...{api_key[-10:]}")
                logger.info(f"   Length: {len(api_key)} characters")
                source_info = "Encrypted file" if (credential_manager.encrypted_file_path and credential_manager.encrypted_file_path.exists()) else "Environment variable or Azure Key Vault"
                logger.info(f"   Source: {source_info}")
            else:
                logger.warning(f"⚠️  No {config['display_name']} found in any configured location")
                logger.info(f"   Try saving it first with: methyl_mapper_credentials save --credential-type {cred_type} --api-key <key>")
                sys.exit(1)
        
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
