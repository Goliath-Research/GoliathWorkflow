"""
Bedtools-based DMP-to-feature mapping for MethylMapper.

This module provides comprehensive mapping of DMPs to genomic features (genes, transcripts,
exons, introns, etc.) using bedtools intersect, with support for weighting by statistical
significance (p-values, q-values) and biological importance (effect_size).
"""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from .gene_disease_enricher import GeneDiseaseEnricher

logger = logging.getLogger(__name__)


class BedtoolsMapper:
    """
    Map DMPs to genomic features using bedtools intersect.
    
    Features:
    - Maps to all GTF features (genes, transcripts, exons, introns, etc.)
    - Weighting by p-value, q-value, and effect_size
    - DMP counts per feature
    - Comprehensive summary statistics
    """
    
    def __init__(
        self,
        gene_gtf: Path,
        feature_types: Optional[List[str]] = None,
        use_p_value_weight: bool = True,
        use_q_value_weight: bool = True,
        use_effect_size_weight: bool = True,
        p_value_log_transform: bool = True,
        enrich_disease: bool = False,
        disease_term: str = "early-stage prostate cancer",
        grok_api_key: Optional[str] = None,
        azure_key_vault_url: Optional[str] = None,
        azure_secret_name: Optional[str] = None,
        encrypted_file_path: Optional[Path] = None
    ):
        """
        Initialize BedtoolsMapper.
        
        Args:
            gene_gtf: Path to GTF/GFF annotation file
            feature_types: List of feature types to extract (e.g., ['gene', 'exon', 'intron']).
                          If None, extracts all features.
            use_p_value_weight: Whether to weight by p-value
            use_q_value_weight: Whether to weight by q-value
            use_effect_size_weight: Whether to weight by effect_size
            p_value_log_transform: If True, uses -log10(p_value) for weighting
            enrich_disease: Whether to enrich results with disease associations
            disease_term: Disease term for enrichment (e.g., "early-stage prostate cancer")
            grok_api_key: Grok API key for disease enrichment (optional, uses secure storage if not provided)
            azure_key_vault_url: Azure Key Vault URL (or set AZURE_KEY_VAULT_URL env var)
            azure_secret_name: Azure Key Vault secret name (or set AZURE_SECRET_NAME env var)
            encrypted_file_path: Path to encrypted credential file (optional)
        """
        self.gene_gtf = Path(gene_gtf)
        if not self.gene_gtf.exists():
            raise FileNotFoundError(f"GTF file not found: {self.gene_gtf}")
        
        self.feature_types = feature_types or ['gene', 'transcript', 'exon', 'intron', 
                                                 'CDS', 'UTR', 'five_prime_utr', 'three_prime_utr']
        self.use_p_value_weight = use_p_value_weight
        self.use_q_value_weight = use_q_value_weight
        self.use_effect_size_weight = use_effect_size_weight
        self.p_value_log_transform = p_value_log_transform
        
        # Disease enrichment
        self.enrich_disease = enrich_disease
        self.disease_enricher = None
        if enrich_disease:
            self.disease_enricher = GeneDiseaseEnricher(
                grok_api_key=grok_api_key,
                disease_term=disease_term,
                azure_key_vault_url=azure_key_vault_url,
                azure_secret_name=azure_secret_name,
                encrypted_file_path=encrypted_file_path
            )
        
        # Check bedtools availability
        try:
            subprocess.run(['bedtools', '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("bedtools not found. Please install bedtools: conda install -c bioconda bedtools")
    
    def csv_to_bed(self, csv_path: Path, output_bed: Optional[Path] = None) -> Path:
        """
        Convert MethylModeler CSV to BED format.
        
        Args:
            csv_path: Path to DMP CSV file
            output_bed: Optional output BED file path. If None, creates temp file.
            
        Returns:
            Path to BED file
        """
        csv_path = Path(csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        
        if output_bed is None:
            output_bed = Path(tempfile.mkdtemp()) / f"{csv_path.stem}.bed"
        
        logger.debug(f"Converting {csv_path} to BED format...")
        
        # Read CSV
        df = pd.read_csv(csv_path)
        
        # Check required columns
        required_cols = ['chromosome', 'position']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        
        # Create BED format: chrom, start (0-based), end, name
        # Name includes chromosome:position:context for traceability
        bed_data = []
        for _, row in df.iterrows():
            chrom = str(row['chromosome'])
            pos = int(row['position'])
            start = pos - 1  # BED is 0-based
            end = pos
            
            # Create name with key info
            name_parts = [chrom, str(pos)]
            if 'context' in df.columns:
                name_parts.append(str(row['context']))
            if 'effect_size' in df.columns:
                name_parts.append(f"eff={row['effect_size']:.3f}")
            
            name = ":".join(name_parts)
            
            bed_data.append({
                'chrom': chrom,
                'start': start,
                'end': end,
                'name': name
            })
        
        bed_df = pd.DataFrame(bed_data)
        
        # Write BED file (sorted for bedtools)
        bed_df = bed_df.sort_values(['chrom', 'start'])
        bed_df.to_csv(output_bed, sep='\t', header=False, index=False)
        
        logger.debug(f"Created BED file: {output_bed} ({len(bed_df)} entries)")
        return output_bed
    
    def intersect_with_features(
        self,
        bed_path: Path,
        dmp_df: pd.DataFrame,
        output_file: Optional[Path] = None
    ) -> pd.DataFrame:
        """
        Intersect DMP BED file with GTF features using bedtools.
        
        Args:
            bed_path: Path to DMP BED file
            dmp_df: Original DMP DataFrame (for joining weights)
            output_file: Optional output file path
            
        Returns:
            DataFrame with DMP-feature intersections
        """
        logger.info(f"Intersecting DMPs with features from {self.gene_gtf}...")
        
        # Run bedtools intersect
        cmd = [
            'bedtools', 'intersect',
            '-a', str(bed_path),
            '-b', str(self.gene_gtf),
            '-wa', '-wb'  # Write both A and B entries
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"bedtools intersect failed: {e.stderr}")
            raise
        
        # Parse bedtools output
        # Format: chromA startA endA nameA | chromB startB endB nameB score strand frame attributes
        lines = result.stdout.strip().split('\n')
        if not lines or lines == ['']:
            logger.warning("No intersections found!")
            return pd.DataFrame()
        
        intersections = []
        for line in lines:
            parts = line.split('\t')
            if len(parts) < 13:
                continue
            
            # Extract DMP info (first 4 columns)
            dmp_name = parts[3]
            
            # Extract feature info (GTF columns)
            feature_chrom = parts[4]
            feature_source = parts[5]
            feature_type = parts[6]
            feature_start = int(parts[7])
            feature_end = int(parts[8])
            feature_score = parts[9]
            feature_strand = parts[10]
            feature_frame = parts[11]
            feature_attrs = parts[12]
            
            # Parse attributes
            attrs = self._parse_gtf_attributes(feature_attrs)
            
            intersections.append({
                'dmp_name': dmp_name,
                'feature_chrom': feature_chrom,
                'feature_source': feature_source,
                'feature_type': feature_type,
                'feature_start': feature_start,
                'feature_end': feature_end,
                'feature_strand': feature_strand,
                'feature_frame': feature_frame,
                'gene_id': attrs.get('gene_id', ''),
                'gene_name': attrs.get('gene_name', attrs.get('gene_id', '')),
                'transcript_id': attrs.get('transcript_id', ''),
                'transcript_name': attrs.get('transcript_name', attrs.get('transcript_id', '')),
                'exon_id': attrs.get('exon_id', ''),
                'exon_number': attrs.get('exon_number', ''),
                'attributes': feature_attrs
            })
        
        intersect_df = pd.DataFrame(intersections)
        
        # Filter by feature types if specified
        if self.feature_types:
            intersect_df = intersect_df[intersect_df['feature_type'].isin(self.feature_types)]
        
        logger.info(f"Found {len(intersect_df)} DMP-feature intersections")
        
        # Join with original DMP data for weights
        intersect_df = self._join_with_dmp_weights(intersect_df, dmp_df)
        
        if output_file:
            intersect_df.to_csv(output_file, index=False)
            logger.info(f"Saved intersections to {output_file}")
        
        return intersect_df
    
    def _parse_gtf_attributes(self, attr_string: str) -> Dict[str, str]:
        """Parse GTF attributes string into dictionary."""
        attrs = {}
        for item in attr_string.split(';'):
            item = item.strip()
            if not item:
                continue
            if ' ' in item:
                key, value = item.split(' ', 1)
                key = key.strip()
                value = value.strip().strip('"')
                attrs[key] = value
        return attrs
    
    def _join_with_dmp_weights(self, intersect_df: pd.DataFrame, dmp_df: pd.DataFrame) -> pd.DataFrame:
        """Join intersection DataFrame with DMP weights."""
        # Parse DMP name to extract chromosome and position
        dmp_info = []
        for name in intersect_df['dmp_name']:
            parts = name.split(':')
            if len(parts) >= 2:
                chrom = parts[0]
                try:
                    pos = int(parts[1])
                except ValueError:
                    pos = None
                dmp_info.append({'chromosome': chrom, 'position': pos})
            else:
                dmp_info.append({'chromosome': '', 'position': None})
        
        dmp_info_df = pd.DataFrame(dmp_info)
        intersect_df = pd.concat([intersect_df.reset_index(drop=True), dmp_info_df], axis=1)
        
        # Ensure consistent types for merging
        # Convert chromosome and position to same types as in dmp_df
        if 'chromosome' in dmp_df.columns:
            dmp_df['chromosome'] = dmp_df['chromosome'].astype(str)
        if 'position' in dmp_df.columns:
            dmp_df['position'] = dmp_df['position'].astype('Int64')  # Nullable integer
        
        intersect_df['chromosome'] = intersect_df['chromosome'].astype(str)
        intersect_df['position'] = pd.to_numeric(intersect_df['position'], errors='coerce').astype('Int64')
        
        # Merge with original DMP DataFrame
        merged = intersect_df.merge(
            dmp_df[['chromosome', 'position', 'p_value', 'q_value', 'effect_size', 'delta_mean', 'context']],
            on=['chromosome', 'position'],
            how='left'
        )
        
        # Compute weighted scores
        merged['weight'] = 1.0
        
        if self.use_p_value_weight and 'p_value' in merged.columns:
            if self.p_value_log_transform:
                merged['p_weight'] = -np.log10(merged['p_value'].clip(lower=1e-300))
            else:
                merged['p_weight'] = 1.0 / (merged['p_value'].clip(lower=1e-300))
            merged['weight'] *= merged['p_weight']
        
        if self.use_q_value_weight and 'q_value' in merged.columns:
            merged['q_weight'] = -np.log10(merged['q_value'].clip(lower=1e-300))
            merged['weight'] *= merged['q_weight']
        
        if self.use_effect_size_weight and 'effect_size' in merged.columns:
            merged['eff_weight'] = merged['effect_size'].clip(lower=0)
            merged['weight'] *= merged['eff_weight']
        
        # Normalize weights (optional - can be disabled)
        merged['weight'] = merged['weight'] / merged['weight'].max() if merged['weight'].max() > 0 else merged['weight']
        
        return merged
    
    def aggregate_by_feature(
        self,
        intersect_df: pd.DataFrame,
        group_by: str = 'gene_name'
    ) -> pd.DataFrame:
        """
        Aggregate DMPs by genomic feature.
        
        Args:
            intersect_df: DataFrame with DMP-feature intersections
            group_by: Column to group by ('gene_name', 'transcript_id', 'feature_type', etc.)
            
        Returns:
            Aggregated DataFrame with statistics per feature
        """
        if group_by not in intersect_df.columns:
            raise ValueError(f"Column '{group_by}' not found in intersection DataFrame")
        
        logger.info(f"Aggregating by {group_by}...")
        
        # Build aggregation dictionary using column names as keys
        agg_dict = {}
        
        if 'dmp_name' in intersect_df.columns:
            agg_dict['dmp_name'] = ['count', 'nunique']
        
        if 'weight' in intersect_df.columns:
            agg_dict['weight'] = ['sum', 'mean', 'max']
        
        if 'p_value' in intersect_df.columns:
            agg_dict['p_value'] = ['min', 'mean']
        
        if 'q_value' in intersect_df.columns:
            agg_dict['q_value'] = ['min', 'mean']
        
        if 'effect_size' in intersect_df.columns:
            agg_dict['effect_size'] = ['mean', 'max']
        
        if 'delta_mean' in intersect_df.columns:
            agg_dict['delta_mean'] = ['mean', 'max']
        
        # Perform aggregation
        grouped = intersect_df.groupby(group_by).agg(agg_dict).reset_index()
        
        # Flatten MultiIndex columns
        if isinstance(grouped.columns, pd.MultiIndex):
            new_cols = []
            for col in grouped.columns:
                if col[0] == group_by:
                    new_cols.append(col[0])
                elif col[0] == 'dmp_name':
                    if col[1] == 'count':
                        new_cols.append('dmp_count')
                    elif col[1] == 'nunique':
                        new_cols.append('unique_dmps')
                    else:
                        new_cols.append(f"{col[0]}_{col[1]}")
                elif col[0] == 'weight':
                    if col[1] == 'sum':
                        new_cols.append('total_weight')
                    elif col[1] == 'mean':
                        new_cols.append('mean_weight')
                    elif col[1] == 'max':
                        new_cols.append('max_weight')
                    else:
                        new_cols.append(f"{col[0]}_{col[1]}")
                elif col[0] in ['p_value', 'q_value']:
                    if col[1] == 'min':
                        new_cols.append(f"min_{col[0]}")
                    elif col[1] == 'mean':
                        new_cols.append(f"mean_{col[0]}")
                    else:
                        new_cols.append(f"{col[0]}_{col[1]}")
                elif col[0] in ['effect_size', 'delta_mean']:
                    if col[1] == 'mean':
                        new_cols.append(f"mean_{col[0]}")
                    elif col[1] == 'max':
                        new_cols.append(f"max_{col[0]}")
                    else:
                        new_cols.append(f"{col[0]}_{col[1]}")
                else:
                    new_cols.append(f"{col[0]}_{col[1]}" if col[1] else col[0])
            grouped.columns = new_cols
        else:
            # Already flattened
            grouped.columns = [col[0] if isinstance(col, tuple) and len(col) == 2 else col for col in grouped.columns]
        
        # Add feature metadata (take first occurrence)
        metadata_cols = ['feature_type', 'feature_chrom', 'feature_strand', 'gene_id', 'transcript_id']
        available_metadata = [c for c in metadata_cols if c in intersect_df.columns]
        if available_metadata:
            metadata = intersect_df.groupby(group_by)[available_metadata].first().reset_index()
            grouped = grouped.merge(metadata, on=group_by, how='left')
        
        # Sort by DMP count (descending), then by weight
        sort_cols = ['dmp_count']
        if 'total_weight' in grouped.columns:
            sort_cols.append('total_weight')
        grouped = grouped.sort_values(sort_cols, ascending=False).reset_index(drop=True)
        
        logger.info(f"Aggregated into {len(grouped)} {group_by}s")
        return grouped
    
    def map_csv_files(
        self,
        csv_pattern: str,
        output_dir: Optional[Path] = None,
        group_by: str = 'gene_name'
    ) -> Dict[str, pd.DataFrame]:
        """
        Map multiple CSV files matching a pattern.
        
        Args:
            csv_pattern: Glob pattern for CSV files (e.g., "dmps-*-3-optimized.csv")
                        Can be absolute path or relative to current directory
            output_dir: Output directory for results. If None, uses CSV directory.
            group_by: Feature to group by ('gene_name', 'transcript_id', etc.)
            
        Returns:
            Dictionary mapping CSV file paths to aggregated results DataFrames
        """
        csv_path = Path(csv_pattern)
        
        # Determine search directory
        if csv_path.is_absolute():
            # Absolute path: use parent directory
            search_dir = csv_path.parent
            pattern = csv_path.name
        else:
            # Relative path: check if it's a directory or pattern
            if csv_path.exists() and csv_path.is_dir():
                search_dir = csv_path
                pattern = "*.csv"
            else:
                # Assume pattern in current directory
                search_dir = Path.cwd()
                pattern = csv_pattern
        
        # Find matching CSV files
        csv_files = sorted(search_dir.glob(pattern))
        
        if not csv_files:
            raise FileNotFoundError(f"No CSV files found matching pattern: {csv_pattern} (searched in {search_dir})")
        
        logger.info(f"Found {len(csv_files)} CSV files matching pattern: {csv_pattern}")
        
        if output_dir is None:
            output_dir = search_dir / "mapped_features"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = {}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            for csv_file in csv_files:
                logger.info(f"\n{'='*70}")
                logger.info(f"Processing: {csv_file.name}")
                logger.info(f"{'='*70}")
                
                try:
                    # Load DMPs
                    dmp_df = pd.read_csv(csv_file)
                    
                    # Convert to BED
                    bed_file = Path(temp_dir) / f"{csv_file.stem}.bed"
                    self.csv_to_bed(csv_file, bed_file)
                    
                    # Intersect with features
                    intersect_df = self.intersect_with_features(bed_file, dmp_df)
                    
                    if intersect_df.empty:
                        logger.warning(f"No features found for {csv_file.name}")
                        continue
                    
                    # Aggregate by feature
                    aggregated = self.aggregate_by_feature(intersect_df, group_by=group_by)
                    
                    # Enrich with disease associations if enabled
                    if self.enrich_disease and self.disease_enricher and group_by in ['gene_name', 'gene_id']:
                        logger.info(f"Enriching {group_by} with disease associations...")
                        aggregated = self.disease_enricher.enrich_gene_dataframe(
                            aggregated,
                            gene_column=group_by
                        )
                    
                    # Save results
                    output_csv = output_dir / f"{csv_file.stem}-features-{group_by}.csv"
                    aggregated.to_csv(output_csv, index=False)
                    
                    # Save detailed intersections
                    detail_csv = output_dir / f"{csv_file.stem}-intersections.csv"
                    intersect_df.to_csv(detail_csv, index=False)
                    
                    results[str(csv_file)] = aggregated
                    
                    logger.info(f"✅ Mapped {len(intersect_df)} DMP-feature pairs")
                    logger.info(f"   Found {len(aggregated)} unique {group_by}s")
                    logger.info(f"   Results saved to: {output_csv}")
                    logger.info(f"   Detailed intersections: {detail_csv}")
                    
                except Exception as e:
                    logger.error(f"Failed to process {csv_file.name}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
        
        # Combine all results if multiple files
        if len(results) > 1:
            logger.info(f"\n{'='*70}")
            logger.info(f"Combining results from {len(results)} files...")
            logger.info(f"{'='*70}")
            
            combined = pd.concat(results.values(), ignore_index=True)
            
            # Aggregate combined results
            combined_agg = {
                'dmp_count': 'sum',
                'unique_dmps': 'sum',
            }
            
            # Add mean aggregations for numeric columns (excluding grouping and metadata columns)
            numeric_cols = combined.select_dtypes(include=[np.number]).columns.tolist()
            exclude_cols = [group_by, 'dmp_count', 'unique_dmps', 'feature_type', 'feature_chrom', 'feature_strand', 'gene_id', 'transcript_id']
            for col in numeric_cols:
                if col not in exclude_cols:
                    combined_agg[col] = 'mean'
            
            # Handle non-numeric columns
            # For metadata columns, take the first occurrence
            metadata_cols = ['feature_type', 'feature_chrom', 'feature_strand', 'gene_id', 'transcript_id']
            for col in metadata_cols:
                if col in combined.columns:
                    combined_agg[col] = 'first'
            
            # For disease enrichment columns, take the first non-null value (or first if all null)
            disease_cols = [c for c in combined.columns if c.startswith('disease_')]
            for col in disease_cols:
                if col not in combined_agg:
                    # For boolean columns, use 'any' (if any chromosome has association, mark as associated)
                    if col in combined.columns and combined[col].dtype == bool:
                        combined_agg[col] = 'any'
                    else:
                        # For other types, take first non-null value
                        combined_agg[col] = 'first'
            
            # Group and aggregate
            combined = combined.groupby(group_by).agg(combined_agg).reset_index()
            
            # Enrich combined results with disease associations if enabled
            if self.enrich_disease and self.disease_enricher and group_by in ['gene_name', 'gene_id']:
                logger.info(f"Enriching combined {group_by} results with disease associations...")
                unique_genes = combined[group_by].nunique()
                logger.info(f"Found {unique_genes} unique {group_by}s across all chromosomes")
                combined = self.disease_enricher.enrich_gene_dataframe(
                    combined,
                    gene_column=group_by
                )
            
            combined_csv = output_dir / f"all-{group_by}-combined.csv"
            combined.to_csv(combined_csv, index=False)
            logger.info(f"\n{'='*70}")
            logger.info(f"✅ Combined results from {len(results)} files:")
            logger.info(f"   Total unique {group_by}s: {len(combined)}")
            logger.info(f"   Saved to: {combined_csv}")
            logger.info(f"{'='*70}")
        
        return results

