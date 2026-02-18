"""
Bedtools-based DMP-to-feature mapping for MethylMapper.

This module provides comprehensive mapping of DMPs to genomic features (genes, transcripts,
exons, introns, etc.) using bedtools intersect, with support for weighting by statistical
significance (p-values, q-values) and biological importance (effect_size).
"""

import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

try:
    from methyl_utils import storey_qvalues
except ImportError:
    from methyl_utils.statistical_tests import storey_qvalues

from .gene_disease_enricher import GeneDiseaseEnricher

logger = logging.getLogger(__name__)


def calculate_biological_importance(delta_mean, std, overlap, min_delta_mean=0.1, max_overlap=0.6):
    """Calculate bounded biological importance in [0,1].

    Hybrid: abs(delta_mean) / (overlap * std), penalized for noisy positions.
    Zero overlap = 1.0 max.

    Args:
        delta_mean: Methylation difference
        std: Combined standard deviation (variance penalty)
        overlap: Distribution overlap (can be 0)
        min_delta_mean: Min threshold (default: 0.1)
        max_overlap: Max threshold (default: 0.6)

    Returns:
        importance: [0,1] bounded
    """
    # Convert to numpy
    delta_mean = np.asarray(delta_mean)
    std = np.asarray(std)
    overlap = np.asarray(overlap)

    is_scalar = delta_mean.ndim == 0

    if is_scalar:
        if overlap == 0:
            return 1.0
        r = abs(delta_mean) / (overlap * std)
        c = abs(min_delta_mean) / max_overlap
        importance = r / (r + c)
        return float(importance)

    # Array case
    zero_overlap_mask = overlap == 0

    # Avoid div0 and low variance
    eps = 1e-8
    denom = np.maximum(overlap * std, eps)
    r = np.abs(delta_mean) / denom

    c = abs(min_delta_mean) / max_overlap
    importance = r / (r + c)

    importance[zero_overlap_mask] = 1.0
    importance = np.nan_to_num(importance, nan=0.0)

    return importance


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
        enrich_source: str = "grok+opentargets",
        separate_enrichment_sources: bool = False,
        disease_term: str = "early-stage prostate cancer",
        grok_api_key: Optional[str] = None,
        disgenet_api_key: Optional[str] = None,
        enrichment_profile: Optional[str] = None,
        min_evidence_level: Optional[str] = None,
        min_publications: Optional[int] = None,
        min_disgenet_score: Optional[float] = None,
        allow_predicted: Optional[bool] = None,
        cache_enabled: bool = True,
        cache_dir: Optional[Path] = None,  # Auto: project_root/enrich_cache or ./enrich_cache
        cache_ttl_days: Optional[int] = 0,
        azure_key_vault_url: Optional[str] = None,
        azure_secret_name: Optional[str] = None,
        encrypted_file_path: Optional[Path] = None,
        optimize_dmps: bool = True,
        dmp_rank_columns: Optional[List[str]] = None,
        min_k: int = 10,
        max_k: Optional[int] = None,
        stability_threshold: int = 3,
        unrelated_growth_threshold: float = 0.10,
        extend_after_stable: bool = True,
    ):
        """
        Initialize BedtoolsMapper.

        Args:
            gene_gtf: Path to GTF/GFF annotation file
            feature_types: List of feature types to extract (e.g., ['gene', 'exon', 'intron']).
                          If None, defaults to ['gene'].
            use_p_value_weight: Whether to weight by p-value
            use_q_value_weight: Whether to weight by q-value
            use_effect_size_weight: Whether to weight by effect_size
            p_value_log_transform: If True, uses -log10(p_value) for weighting
            enrich_disease: Whether to enrich results with disease associations
            enrich_source: Source(s) for disease enrichment ("grok", "opentargets", "grok+opentargets",
                          "disgenet", "both", or "all") (default: "grok+opentargets")
            separate_enrichment_sources: If True, export separate files for each enrichment source
            disease_term: Disease term for enrichment (e.g., "early-stage prostate cancer")
            grok_api_key: Grok API key for disease enrichment (optional, uses secure storage if not provided)
            disgenet_api_key: DisGeNET API key for disease enrichment (optional, uses secure storage if not provided)
            enrichment_profile: Preset threshold profile (strict, balanced, permissive)
            min_evidence_level: Minimum evidence level to count as disease-associated
            min_publications: Minimum number of publications required
            min_disgenet_score: Minimum DisGeNET score required (0.0-1.0)
            allow_predicted: Whether to allow "predicted" associations
            cache_enabled: Whether to persist cache to disk
            cache_dir: Directory for disk cache (default: auto project_root/enrich_cache or ./enrich_cache)
            cache_ttl_days: Cache TTL in days (default: 0 = never use cache; set e.g. 7 to reuse)
            azure_key_vault_url: Azure Key Vault URL (or set AZURE_KEY_VAULT_URL env var)
            azure_secret_name: Azure Key Vault secret name (or set AZURE_SECRET_NAME env var)
            encrypted_file_path: Path to encrypted credential file (optional)
            optimize_dmps: Whether to optimize DMP count for stable gene sets (default: True)
            dmp_rank_columns: Optional list of columns to rank DMPs by importance
            min_k: Minimum number of DMPs to test (default: 10)
            max_k: Maximum number of DMPs to test (default: None, uses all available)
            stability_threshold: Number of consecutive iterations without new genes to consider stable (default: 3)
            unrelated_growth_threshold: Growth rate threshold for unrelated genes (legacy; not used in Phase 1)
            extend_after_stable: If True, after stabilization run optional extension loop when last gene is strongly disease-associated (default: True)
        """
        self.gene_gtf = Path(gene_gtf)
        if not self.gene_gtf.exists():
            raise FileNotFoundError(f"GTF file not found: {self.gene_gtf}")
        
        self.feature_types = feature_types or ['gene']
        self.use_p_value_weight = use_p_value_weight
        self.use_q_value_weight = use_q_value_weight
        self.use_effect_size_weight = use_effect_size_weight
        self.p_value_log_transform = p_value_log_transform

        # Disease enrichment
        self.enrich_disease = enrich_disease
        self.enrich_source = enrich_source
        self.separate_enrichment_sources = separate_enrichment_sources
        self.disease_enricher = None
        if enrich_disease:
            use_grok, use_open_targets, use_disgenet = self._parse_enrich_source(enrich_source)
            try:
                self.disease_enricher = GeneDiseaseEnricher(
                grok_api_key=grok_api_key if use_grok else None,
                disgenet_api_key=disgenet_api_key if use_disgenet else None,
                disease_term=disease_term,
                use_grok=use_grok,
                use_disgenet=use_disgenet,
                use_open_targets=use_open_targets,
                enrichment_profile=enrichment_profile,
                min_evidence_level=min_evidence_level,
                min_publications=min_publications,
                min_disgenet_score=min_disgenet_score,
                allow_predicted=allow_predicted,
                cache_enabled=cache_enabled,
                cache_dir=cache_dir,
                cache_ttl_days=cache_ttl_days,
                azure_key_vault_url=azure_key_vault_url,
                azure_secret_name=azure_secret_name,
                encrypted_file_path=encrypted_file_path
            )
            except Exception as e:
                logger.warning(f"Disease enricher initialization failed: {e}. Enrichment columns will not be added.")
                self.disease_enricher = None

        # DMP optimization parameters
        self.optimize_dmps = optimize_dmps
        self.dmp_rank_columns = dmp_rank_columns
        self.min_k = min_k
        self.max_k = max_k
        self.stability_threshold = stability_threshold
        self.unrelated_growth_threshold = unrelated_growth_threshold
        self.extend_after_stable = extend_after_stable

        # When optimize_dmps + enrich_disease: recommend both Grok and Open Targets for gene identification
        if optimize_dmps and enrich_disease:
            use_grok, use_ot, _ = self._parse_enrich_source(enrich_source)
            if not (use_grok and use_ot):
                logger.warning(
                    "DMP optimization with enrichment works best with both Grok and Open Targets (enrich_source grok+opentargets). "
                    "Using configured sources only."
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
        
        # Normalize chromosome for GTF compatibility (GENCODE/UCSC use chr1, chr2, ... chrX, chrY)
        def _bed_chrom(c: str) -> str:
            s = str(c).strip()
            if not s.startswith('chr'):
                return f'chr{s}' if s else s
            return s

        # Create BED format: chrom, start (0-based), end, name
        # Name includes chromosome:position:context for traceability (original chrom for join-back)
        bed_data = []
        for _, row in df.iterrows():
            chrom = str(row['chromosome'])
            pos = int(row['position'])
            start = pos - 1  # BED is 0-based
            end = pos
            chrom_bed = _bed_chrom(chrom)  # chr-prefix so bedtools matches GTF

            # Create name with key info (use original chrom so join with dmp_df works)
            name_parts = [chrom, str(pos)]
            if 'context' in df.columns:
                name_parts.append(str(row['context']))
            if 'effect_size' in df.columns:
                name_parts.append(f"eff={row['effect_size']:.3f}")
            
            name = ":".join(name_parts)

            bed_data.append({
                'chrom': chrom_bed,
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
        dmp_cols = ['chromosome', 'position']
        optional_cols = [
            'p_value', 'q_value', 'effect_size', 'delta_mean',
            'context', 'importance', 'weight', 'overlap'
        ]
        existing_cols = [c for c in optional_cols if c in dmp_df.columns]
        merged = intersect_df.merge(
            dmp_df[dmp_cols + existing_cols],
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
        
        if self.use_effect_size_weight:
            eff_col = None
            if 'effect_size' in merged.columns:
                eff_col = 'effect_size'
            elif 'importance' in merged.columns:
                eff_col = 'importance'
            elif 'delta_mean' in merged.columns and 'overlap' in merged.columns:
                # Compute combined_std from Beta params if available, else approximate
                if all(col in merged.columns for col in ['alpha1', 'beta1', 'alpha2', 'beta2']):
                    # Beta variance formula
                    tau1 = merged['alpha1'] + merged['beta1']
                    var1 = merged['alpha1'] * merged['beta1'] / (tau1**2 * (tau1 + 1))
                    tau2 = merged['alpha2'] + merged['beta2']
                    var2 = merged['alpha2'] * merged['beta2'] / (tau2**2 * (tau2 + 1))
                    combined_std = np.sqrt(var1 + var2)
                else:
                    # Approximate std for methylation (common value)
                    combined_std = 0.1  # Reasonable default for filtered DMPs

                # Calculate hybrid biological importance: |delta| / (overlap * std)
                merged['biological_importance'] = calculate_biological_importance(
                    merged['delta_mean'], combined_std, merged['overlap'],
                    min_delta_mean=0.1, max_overlap=0.6
                )
                eff_col = 'biological_importance'
            elif 'delta_mean' in merged.columns:
                eff_col = 'delta_mean'

            if eff_col is not None:
                merged['eff_weight'] = merged[eff_col].abs().fillna(1.0)
                merged['weight'] *= merged['eff_weight']
        
        # Normalize weights (optional - can be disabled)
        merged['weight'] = merged['weight'] / merged['weight'].max() if merged['weight'].max() > 0 else merged['weight']
        
        return merged

    @staticmethod
    def _parse_enrich_source(enrich_source: str) -> Tuple[bool, bool, bool]:
        """Parse enrich_source into flags for grok/open_targets/disgenet."""
        normalized = (enrich_source or "").lower().strip()

        if normalized == "all":
            return True, True, True
        if normalized == "both":
            # Backward-compatible: grok + disgenet
            return True, False, True

        tokens = [t for t in re.split(r"[+/,\\s]+", normalized) if t]
        use_grok = "grok" in tokens
        use_disgenet = "disgenet" in tokens
        use_open_targets = any(t in tokens for t in ["opentargets", "open_targets", "open-targets"])

        return use_grok, use_open_targets, use_disgenet

    def _sort_dmps_for_optimization(self, dmp_df: pd.DataFrame) -> pd.DataFrame:
        """Sort DMPs by importance for optimization."""
        df = dmp_df.copy()
        rank_cols = self.dmp_rank_columns or ['effect_size', 'importance', 'delta_mean', 'weight']
        rank_col = next((c for c in rank_cols if c in df.columns), None)

        if rank_col is None:
            logger.warning("No ranking column found for DMP optimization; using input order")
            return df

        sort_keys = []
        ascending = []

        if rank_col in ['effect_size', 'delta_mean']:
            df['_rank_key'] = df[rank_col].abs()
            sort_keys.append('_rank_key')
            ascending.append(False)
        else:
            sort_keys.append(rank_col)
            ascending.append(False)

        if 'q_value' in df.columns:
            sort_keys.append('q_value')
            ascending.append(True)
        if 'p_value' in df.columns:
            sort_keys.append('p_value')
            ascending.append(True)

        df = df.sort_values(sort_keys, ascending=ascending).reset_index(drop=True)
        if '_rank_key' in df.columns:
            df = df.drop(columns=['_rank_key'])

        logger.info(f"Sorting DMPs by {rank_col} for optimization")
        return df
    
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

        if 'importance' in intersect_df.columns:
            agg_dict['importance'] = ['sum', 'mean', 'max']
        
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
                elif col[0] == 'importance':
                    if col[1] == 'sum':
                        new_cols.append('total_importance')
                    elif col[1] == 'mean':
                        new_cols.append('mean_importance')
                    elif col[1] == 'max':
                        new_cols.append('max_importance')
                    else:
                        new_cols.append(f"{col[0]}_{col[1]}")
                else:
                    new_cols.append(f"{col[0]}_{col[1]}" if col[1] else col[0])
            grouped.columns = new_cols
        else:
            # Already flattened
            grouped.columns = [col[0] if isinstance(col, tuple) and len(col) == 2 else col for col in grouped.columns]
        
        # Add Stouffer aggregated gene p-values (weighted, signed by delta_mean)
        if 'p_value' in intersect_df.columns:
            from scipy.stats import norm

            def _compute_gene_pvalue(group: pd.DataFrame) -> pd.Series:
                pvals = group['p_value'].astype(float).to_numpy()
                weights = group['weight'].astype(float).to_numpy() if 'weight' in group.columns else np.ones_like(pvals)
                signs = np.sign(group['delta_mean'].astype(float).to_numpy()) if 'delta_mean' in group.columns else np.ones_like(pvals)

                valid = np.isfinite(pvals) & np.isfinite(weights)
                if 'delta_mean' in group.columns:
                    valid &= np.isfinite(signs)

                pvals = pvals[valid]
                weights = weights[valid]
                signs = signs[valid]

                if len(pvals) == 0:
                    return pd.Series({
                        "gene_p_value": np.nan,
                        "gene_z": np.nan,
                        "gene_direction": np.nan,
                        "gene_weight_sumsq": np.nan,
                        "gene_z_numerator": np.nan,
                    })

                pvals = np.clip(pvals, 1e-300, 1.0 - 1e-16)
                z_scores = norm.ppf(1 - pvals / 2.0)
                z_scores = np.clip(z_scores, -8.0, 8.0)
                signed_z = z_scores * signs

                weight_sumsq = float(np.sum(weights ** 2))
                if not np.isfinite(weight_sumsq) or weight_sumsq <= 0:
                    return pd.Series({
                        "gene_p_value": np.nan,
                        "gene_z": np.nan,
                        "gene_direction": np.nan,
                        "gene_weight_sumsq": np.nan,
                        "gene_z_numerator": np.nan,
                    })

                z_numerator = float(np.sum(weights * signed_z))
                combined_z = float(z_numerator / np.sqrt(weight_sumsq))
                gene_p = float(2 * (1 - norm.cdf(abs(combined_z))))
                gene_p = float(np.clip(gene_p, 0.0, 1.0))

                return pd.Series({
                    "gene_p_value": gene_p,
                    "gene_z": combined_z,
                    "gene_direction": float(np.sign(combined_z)),
                    "gene_weight_sumsq": weight_sumsq,
                    "gene_z_numerator": z_numerator,
                })

            try:
                gene_stats = intersect_df.groupby(group_by).apply(_compute_gene_pvalue, include_groups=False).reset_index()
            except TypeError:
                gene_stats = intersect_df.groupby(group_by).apply(_compute_gene_pvalue).reset_index()
            grouped = grouped.merge(gene_stats, on=group_by, how='left')

            gene_pvals = grouped["gene_p_value"].to_numpy(dtype=float)
            gene_qvals = np.full_like(gene_pvals, np.nan, dtype=float)
            finite_mask = np.isfinite(gene_pvals)
            if np.any(finite_mask):
                _qvals, _ = storey_qvalues(gene_pvals[finite_mask])
            gene_qvals[finite_mask] = _qvals
            grouped["gene_q_value"] = gene_qvals

        if 'total_importance' in grouped.columns:
            grouped['gene_importance'] = grouped['total_importance']
        elif 'total_weight' in grouped.columns:
            grouped['gene_importance'] = grouped['total_weight']

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

    def _find_stable_k_by_gene_count(
        self,
        dmp_df: pd.DataFrame,
        group_by: str,
        min_k: int,
        max_k: int,
    ) -> Tuple[int, pd.DataFrame, Dict]:
        """
        Phase 1: Find k where the total number of unique genes stabilizes (no API calls).
        Stability = no new genes for stability_threshold consecutive k values.
        Returns (k_stable, aggregated_gene_df_at_k_stable, phase1_log).
        """
        optimization_log: Dict = {
            'phase1_k_values': [],
            'phase1_gene_counts': [],
            'k_stable': None,
        }
        prev_genes: set = set()
        consecutive_stable = 0
        k_test = min_k
        aggregated_stable = pd.DataFrame()
        k_stable = max_k

        while k_test <= max_k:
            logger.info(f"Phase 1 (stabilize): testing k={k_test}")
            dmp_subset = dmp_df.head(k_test).copy()
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_csv = Path(temp_dir) / "temp.csv"
                dmp_subset.to_csv(temp_csv, index=False)
                bed_file = self.csv_to_bed(temp_csv, Path(temp_dir) / "temp.bed")
                intersect_df = self.intersect_with_features(bed_file, dmp_subset)
            if intersect_df.empty:
                logger.warning(f"No features found for k={k_test}")
                k_test += max(1, (max_k - min_k) // 20)
                continue
            aggregated = self.aggregate_by_feature(intersect_df, group_by=group_by)
            current_genes = set(aggregated[group_by].dropna().astype(str).unique())
            new_genes = current_genes - prev_genes
            optimization_log['phase1_k_values'].append(k_test)
            optimization_log['phase1_gene_counts'].append(len(current_genes))
            if len(new_genes) == 0:
                consecutive_stable += 1
                logger.info(f"  No new genes (stable for {consecutive_stable}/{self.stability_threshold})")
            else:
                consecutive_stable = 0
                logger.info(f"  {len(current_genes)} genes ({len(new_genes)} new)")
            if consecutive_stable >= self.stability_threshold:
                k_stable = k_test - (self.stability_threshold - 1)
                k_stable = max(min_k, k_stable)
                dmp_subset_stable = dmp_df.head(k_stable).copy()
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_csv = Path(temp_dir) / "temp.csv"
                    dmp_subset_stable.to_csv(temp_csv, index=False)
                    bed_file = self.csv_to_bed(temp_csv, Path(temp_dir) / "temp.bed")
                    intersect_df = self.intersect_with_features(bed_file, dmp_subset_stable)
                if not intersect_df.empty:
                    aggregated_stable = self.aggregate_by_feature(intersect_df, group_by=group_by)
                else:
                    aggregated_stable = aggregated.copy()
                optimization_log['k_stable'] = k_stable
                logger.info(f"Phase 1 complete: k_stable={k_stable}, {len(aggregated_stable)} genes")
                return k_stable, aggregated_stable, optimization_log
            prev_genes = current_genes
            step = max(1, (max_k - min_k) // 20) if consecutive_stable == 0 else max(1, (max_k - min_k) // 50)
            k_test += step

        k_stable = min(k_test - 1, max_k) if k_test > min_k else max_k
        optimization_log['k_stable'] = k_stable
        dmp_subset = dmp_df.head(k_stable).copy()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_csv = Path(temp_dir) / "temp.csv"
            dmp_subset.to_csv(temp_csv, index=False)
            bed_file = self.csv_to_bed(temp_csv, Path(temp_dir) / "temp.bed")
            intersect_df = self.intersect_with_features(bed_file, dmp_subset)
        if not intersect_df.empty:
            aggregated_stable = self.aggregate_by_feature(intersect_df, group_by=group_by)
        else:
            aggregated_stable = pd.DataFrame()
        logger.warning(f"Phase 1: no stable k found, using k={k_stable}")
        return k_stable, aggregated_stable, optimization_log

    def optimize_dmps_for_stable_genes(
        self,
        dmp_df: pd.DataFrame,
        group_by: str = 'gene_name',
        min_k: Optional[int] = None,
        max_k: Optional[int] = None
    ) -> Tuple[int, pd.DataFrame, Dict]:
        """
        Three-phase DMP optimization: (1) stabilize on gene count (no API), (2) enrich once (Grok+Open Targets),
        (3) optional extension loop adding DMPs and enriching only new genes until no new disease gene.
        """
        if group_by not in ['gene_name', 'gene_id']:
            raise ValueError(f"optimize_dmps_for_stable_genes requires group_by='gene_name' or 'gene_id', got '{group_by}'")
        min_k = min_k or self.min_k
        max_k = max_k or self.max_k or len(dmp_df)
        max_k = min(max_k, len(dmp_df))
        dmp_df = self._sort_dmps_for_optimization(dmp_df)
        if min_k >= max_k:
            logger.warning(f"min_k ({min_k}) >= max_k ({max_k}), using all DMPs")
            return max_k, pd.DataFrame(), {'optimal_k': max_k}

        # Phase 1: stabilize by gene count (no enricher)
        k_stable, aggregated_stable, phase1_log = self._find_stable_k_by_gene_count(dmp_df, group_by, min_k, max_k)
        optimization_log = dict(phase1_log)
        optimization_log['optimal_k'] = k_stable
        optimization_log['phase2_enriched'] = False
        optimization_log['phase3_extended'] = False
        optimization_log['phase3_steps'] = []
        if aggregated_stable.empty:
            return k_stable, aggregated_stable, optimization_log

        # If enrichment disabled, return stabilized set without disease columns
        if not self.enrich_disease or not self.disease_enricher:
            logger.info("Enrichment disabled; returning Phase 1 gene set without disease columns.")
            return k_stable, aggregated_stable, optimization_log

        # Phase 2: enrich once (both Grok and Open Targets via enrich_gene_dataframe)
        logger.info("Phase 2: Enriching stabilized gene set once (Grok + Open Targets)...")
        optimal_gene_df = self.disease_enricher.enrich_gene_dataframe(
            aggregated_stable.copy(),
            gene_column=group_by
        )
        optimization_log['phase2_enriched'] = True
        genes_at_k_stable = set(optimal_gene_df[group_by].dropna().astype(str).unique())

        # Phase 3: optional extension when last gene is strongly disease-associated
        def _last_gene_strongly_associated(df: pd.DataFrame) -> bool:
            if df.empty or 'disease_associated' not in df.columns:
                return False
            sort_col = 'gene_importance' if 'gene_importance' in df.columns else 'total_weight'
            if sort_col not in df.columns:
                return bool(df['disease_associated'].iloc[-1])
            last_row = df.sort_values(sort_col, ascending=True).iloc[0]
            if not last_row.get('disease_associated', False):
                return False
            ev = str(last_row.get('disease_evidence_level', '')).lower()
            return ev in ('high', 'medium', 'low')

        if self.extend_after_stable and _last_gene_strongly_associated(optimal_gene_df):
            logger.info("Phase 3: Last gene strongly disease-associated; running extension loop...")
            k_ext = k_stable
            while k_ext < len(dmp_df):
                k_ext += 1
                dmp_subset = dmp_df.head(k_ext).copy()
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_csv = Path(temp_dir) / "temp.csv"
                    dmp_subset.to_csv(temp_csv, index=False)
                    bed_file = self.csv_to_bed(temp_csv, Path(temp_dir) / "temp.bed")
                    intersect_df = self.intersect_with_features(bed_file, dmp_subset)
                if intersect_df.empty:
                    continue
                agg_k = self.aggregate_by_feature(intersect_df, group_by=group_by)
                genes_at_k = set(agg_k[group_by].dropna().astype(str).unique())
                new_genes = genes_at_k - genes_at_k_stable
                if not new_genes:
                    continue
                new_df = pd.DataFrame({group_by: list(new_genes)})
                enriched_new = self.disease_enricher.enrich_gene_dataframe(new_df, gene_column=group_by)
                disease_new = set()
                if 'disease_associated' in enriched_new.columns:
                    disease_new = set(
                        enriched_new.loc[enriched_new['disease_associated'] == True, group_by]
                        .dropna().astype(str).unique()
                    )
                optimization_log['phase3_steps'].append({
                    'k': k_ext,
                    'new_genes': len(new_genes),
                    'new_disease_genes': len(disease_new),
                })
                if not disease_new:
                    logger.info(f"Phase 3: k={k_ext}, no new disease-associated genes; stopping.")
                    break
                stats_new = agg_k[agg_k[group_by].astype(str).isin(disease_new)]
                enricher_cols = [c for c in enriched_new.columns if c != group_by]
                merged_new = stats_new.merge(
                    enriched_new[[group_by] + enricher_cols],
                    on=group_by,
                    how='left'
                )
                optimal_gene_df = pd.concat([optimal_gene_df, merged_new], ignore_index=True)
                genes_at_k_stable = genes_at_k
                k_stable = k_ext
                logger.info(f"Phase 3: k={k_ext}, added {len(disease_new)} disease genes; continuing.")
            optimization_log['phase3_extended'] = True
            optimization_log['optimal_k'] = k_stable
        else:
            if not self.extend_after_stable:
                logger.info("Phase 3: disabled (extend_after_stable=False).")
            else:
                logger.info("Phase 3: skipped (last gene not strongly disease-associated).")

        optimization_log['optimal_k'] = k_stable
        # Backward compatibility: old log shape had k_values, disease_related_counts, etc.
        optimization_log.setdefault('k_values', optimization_log.get('phase1_k_values', []))
        optimization_log.setdefault('disease_related_counts', [])
        optimization_log.setdefault('unrelated_counts', [])
        optimization_log.setdefault('disease_related_genes', [])
        optimization_log.setdefault('unrelated_growth_rates', [])
        logger.info(f"Optimization complete: optimal k={k_stable}")
        return k_stable, optimal_gene_df, optimization_log
    
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
        
        # Support path-level wildcard (e.g. /path/to/detection/cancer/*/dmps-*.csv) for per-group detection dirs
        path_wildcard = "/*/"
        if path_wildcard in csv_pattern:
            base_str, _, rest = csv_pattern.partition(path_wildcard)
            search_dir = Path(base_str)
            pattern = "*/" + rest  # e.g. "*/dmps-*.csv" so search_dir.glob finds all group subdirs
        elif csv_path.is_absolute():
            search_dir = csv_path.parent
            pattern = csv_path.name
        else:
            if csv_path.exists() and csv_path.is_dir():
                search_dir = csv_path
                pattern = "*.csv"
            else:
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
                    dmp_df_sorted = self._sort_dmps_for_optimization(dmp_df)
                    
                    # Apply DMP optimization if enabled
                    optimal_k = None
                    if self.optimize_dmps and self.enrich_disease and self.disease_enricher and group_by in ['gene_name', 'gene_id']:
                        logger.info(f"Optimizing DMP count for stable gene sets...")
                        optimal_k, optimal_gene_df, optimization_log = self.optimize_dmps_for_stable_genes(
                            dmp_df_sorted,
                            group_by=group_by
                        )
                        
                        # Export optimization log
                        import json
                        log_file = output_dir / f"{csv_file.stem}-optimization-log.json"
                        with open(log_file, 'w') as f:
                            json.dump(optimization_log, f, indent=2)
                        logger.info(f"   Optimization log saved to: {log_file}")
                        
                        # Export optimized DMP subset
                        optimized_dmp_df = dmp_df_sorted.head(optimal_k).copy()
                        optimized_dmp_csv = output_dir / f"{csv_file.stem}-optimized-k{optimal_k}.csv"
                        optimized_dmp_df.to_csv(optimized_dmp_csv, index=False)
                        logger.info(f"   Optimized DMP subset (k={optimal_k}) saved to: {optimized_dmp_csv}")
                        
                        # Use optimized gene set
                        aggregated = optimal_gene_df
                        
                        # Convert optimized DMPs to BED for detailed intersections
                        bed_file = Path(temp_dir) / f"{csv_file.stem}.bed"
                        self.csv_to_bed(optimized_dmp_csv, bed_file)
                        intersect_df = self.intersect_with_features(bed_file, optimized_dmp_df)
                    else:
                        # Original behavior: use all DMPs
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
                        if self.enrich_disease and group_by in ['gene_name', 'gene_id']:
                            if self.disease_enricher:
                                logger.info(f"Enriching {group_by} with disease associations...")
                                aggregated = self.disease_enricher.enrich_gene_dataframe(
                                    aggregated,
                                    gene_column=group_by,
                                    disease_term=self.disease_enricher.disease_term
                                )
                            else:
                                logger.warning("Disease enrichment was requested but enricher is not available (init failed). Output will not include disease columns.")
                    
                    # Save results
                    output_csv = output_dir / f"{csv_file.stem}-features-{group_by}.csv"
                    if self.optimize_dmps and self.enrich_disease and self.disease_enricher and group_by in ['gene_name', 'gene_id']:
                        # Save optimized results with k suffix
                        output_csv = output_dir / f"{csv_file.stem}-optimized-k{optimal_k}-features-{group_by}.csv"
                    aggregated.to_csv(output_csv, index=False)
                    
                    # Save detailed intersections
                    detail_csv = output_dir / f"{csv_file.stem}-intersections.csv"
                    if self.optimize_dmps and self.enrich_disease and self.disease_enricher and group_by in ['gene_name', 'gene_id']:
                        detail_csv = output_dir / f"{csv_file.stem}-optimized-k{optimal_k}-intersections.csv"
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

            # Preserve additive fields across chromosomes
            sum_cols = [
                'total_weight',
                'total_importance',
                'gene_weight_sumsq',
                'gene_z_numerator',
            ]
            for col in sum_cols:
                if col in combined.columns:
                    combined_agg[col] = 'sum'
            
            # Add mean aggregations for numeric columns (excluding grouping and metadata columns)
            numeric_cols = combined.select_dtypes(include=[np.number]).columns.tolist()
            exclude_cols = [
                group_by,
                'dmp_count',
                'unique_dmps',
                'feature_type',
                'feature_chrom',
                'feature_strand',
                'gene_id',
                'transcript_id',
                'gene_p_value',
                'gene_q_value',
                'gene_z',
                'gene_direction',
                'gene_weight_sumsq',
                'gene_z_numerator',
                'gene_importance',
            ]
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

            # Recompute combined gene-level p-values if available
            if 'gene_weight_sumsq' in combined.columns and 'gene_z_numerator' in combined.columns:
                from scipy.stats import norm
                z_num = combined['gene_z_numerator'].to_numpy(dtype=float)
                z_denom = np.sqrt(combined['gene_weight_sumsq'].to_numpy(dtype=float))
                with np.errstate(invalid='ignore', divide='ignore'):
                    combined_z = z_num / z_denom
                combined['gene_z'] = combined_z
                combined['gene_direction'] = np.sign(combined_z)
                gene_p = 2 * (1 - norm.cdf(np.abs(combined_z)))
                combined['gene_p_value'] = np.clip(gene_p, 0.0, 1.0)

                gene_pvals = combined['gene_p_value'].to_numpy(dtype=float)
                gene_qvals = np.full_like(gene_pvals, np.nan, dtype=float)
                finite_mask = np.isfinite(gene_pvals)
                if np.any(finite_mask):
                    _qvals, _ = storey_qvalues(gene_pvals[finite_mask])
                    gene_qvals[finite_mask] = _qvals
                combined['gene_q_value'] = gene_qvals

            if 'total_importance' in combined.columns:
                combined['gene_importance'] = combined['total_importance']
            elif 'total_weight' in combined.columns:
                combined['gene_importance'] = combined['total_weight']
            
            # Enrich combined results with disease associations if enabled
            if self.enrich_disease and group_by in ['gene_name', 'gene_id']:
                if self.disease_enricher:
                    logger.info(f"Enriching combined {group_by} results with disease associations...")
                    unique_genes = combined[group_by].nunique()
                    logger.info(f"Found {unique_genes} unique {group_by}s across all chromosomes")
                    disease_term = getattr(self.disease_enricher, 'disease_term', None)

                    if self.separate_enrichment_sources and self.enrich_source == 'both':
                        enriched_results = self.disease_enricher.enrich_gene_dataframe(
                            combined,
                            gene_column=group_by,
                            disease_term=disease_term,
                            separate_sources=True
                        )
                        for source_name, enriched_df in enriched_results.items():
                            source_csv = output_dir / f"all-{group_by}-combined-{source_name}.csv"
                            enriched_df.to_csv(source_csv, index=False)
                            logger.info(f"   Saved {source_name} results to: {source_csv}")
                        combined = enriched_results['merged']
                    else:
                        combined = self.disease_enricher.enrich_gene_dataframe(
                            combined,
                            gene_column=group_by,
                            disease_term=disease_term
                        )
                else:
                    logger.warning("Disease enrichment was requested but enricher is not available. Combined CSV will not include disease columns.")
            
            combined_csv = output_dir / f"all-{group_by}-combined.csv"
            combined.to_csv(combined_csv, index=False)
            logger.info(f"\n{'='*70}")
            logger.info(f"✅ Combined results from {len(results)} files:")
            logger.info(f"   Total unique {group_by}s: {len(combined)}")
            logger.info(f"   Saved to: {combined_csv}")
            logger.info(f"{'='*70}")
        
        return results
