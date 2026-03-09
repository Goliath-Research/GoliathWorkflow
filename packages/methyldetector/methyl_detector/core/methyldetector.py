"""Core MethylDetector pipeline for DMP detection, filtering, and selection."""

import itertools
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

# Import statistical functions from MethylUtils (required)
from methyl_utils import (
    MethylBetaMixtureCentroid,
    cleanup_gpu_memory
)
from methyl_utils.logging_utils import setup_module_logging

# Import sample handler for proper SRP compliance
from methyl_utils.core.methyl_frame import MethylSample

# Import MethylCentroidPair from MethylUtils for mathematical operations
from methyl_utils import MethylCentroidPair

# Import BetaClassifier and BetaBinomialClassifier from MethylUtils
from methyl_utils import BetaClassifier, BetaBinomialClassifier

# Import EAT transformation (optional - may not be available in all environments)
try:
    from methyl_utils import compute_eat_T
    EAT_AVAILABLE = True
except ImportError:
    EAT_AVAILABLE = False
    compute_eat_T = None

# Handle relative imports - try module import first, fall back to direct execution setup
try:
    from ..models.config import MethylModelerConfig
    from ..models.results import (
        ComparisonStats,
        MethylModelerResult,
        MethylModelerSummary,
    )
    from ..utils.core import GPUConfig, save_csv, save_json, save_summary_txt
    from ..utils.file_utils import get_chromosome_context_from_filename
except ImportError:
    # For direct execution, these will be set up in __main__
    MethylModelerConfig = None
    ComparisonStats = None
    MethylModelerResult = None
    GPUConfig = None
    save_csv = None
    save_json = None
    save_summary_txt = None
    CentroidPairHandler = None
    create_centroid_from_arrays = None
    get_chromosome_context_from_filename = None
logger = setup_module_logging(__name__)

def _apply_biological_filters(
    df: pd.DataFrame,
    min_delta_mean: Optional[float],
    max_overlap: Optional[float],
    min_effect_size: Optional[float] = None,
) -> pd.DataFrame:
    """
    Apply biological filters (ECDF-based). Used by _filter_biological_dmps and filter-funnel sweep.
    - min_delta_mean: keep |delta_mean| >= value
    - max_overlap: keep overlap <= value (continuous ECDF overlap)
    - min_effect_size: keep effect_size >= value (effect size in [0, 1])
    Pass None for any filter to skip it. Returns a copy of df with filters applied.
    """
    out = df.copy()
    if min_delta_mean is not None and "delta_mean" in out.columns:
        out = out[np.abs(out["delta_mean"].astype(float)) >= min_delta_mean]
    if max_overlap is not None and "overlap" in out.columns:
        out = out[out["overlap"].astype(float) <= max_overlap]
    if min_effect_size is not None and "effect_size" in out.columns:
        out = out[out["effect_size"].astype(float) >= min_effect_size]
    return out


class MethylDetector:
    """Main class for MethylDetector DMP detection and filtering."""

    def __init__(self, config: MethylModelerConfig):
        """Initialize with configuration."""
        self.config = config
        np.random.seed(config.random_state)
        self.gpu_config = GPUConfig()  # From MethylUtils for memory management
        self.df = None  # Current working dataframe
        self._exported_csv_path = None  # Path to exported CSV file
        self._current_chromosome = None  # Current chromosome being processed (for multi-chromosome mode)
        logger.debug("Initialized MethylDetector")
    
    @property
    def chromosome(self) -> str:
        """Get the current chromosome being processed."""
        if self._current_chromosome is not None:
            return self._current_chromosome
        # Fallback: if config.chromosome is a list, return first; otherwise return as-is
        if isinstance(self.config.chromosome, list):
            return self.config.chromosome[0]
        return self.config.chromosome
    
    def run(self) -> Union[MethylModelerResult, List[MethylModelerResult]]:
        """
        Run the complete DMP detection and filtering pipeline.
        
        Returns:
            MethylModelerResult if processing a single chromosome,
            List[MethylModelerResult] if processing multiple chromosomes
        """
        logger.debug("Starting MethylDetector analysis pipeline...")
        
        # Check if we're processing multiple chromosomes
        chromosomes = self.config.chromosome
        if isinstance(chromosomes, str):
            chromosomes = [chromosomes]  # Normalize to list
        
        if len(chromosomes) == 1:
            # Single chromosome: process normally
            self._current_chromosome = chromosomes[0]
            return self._run_multi_context()
        else:
            # Multiple chromosomes: require binned_stats once before any work (fail fast)
            self._current_chromosome = chromosomes[0]
            self._require_binned_stats_available()
            logger.info(f"🧬 Processing {len(chromosomes)} chromosomes: {', '.join(chromosomes)}")
            results = []
            failed_chromosomes = []
            
            for i, chrom in enumerate(chromosomes, 1):
                logger.info(f"\n{'='*80}")
                logger.info(f"Processing chromosome {chrom} ({i}/{len(chromosomes)})")
                logger.info(f"{'='*80}")
                
                try:
                    self._current_chromosome = chrom
                    result = self._run_multi_context()
                    results.append(result)
                    logger.info(f"✅ Successfully completed chromosome {chrom}")
                except Exception as e:
                    logger.error(f"❌ Failed to process chromosome {chrom}: {e}")
                    import traceback
                    traceback.print_exc()
                    failed_chromosomes.append((chrom, str(e)))
            
            # Summary
            logger.info(f"\n{'='*80}")
            logger.info("Multi-chromosome processing complete:")
            logger.info(f"  ✅ Successful: {len(results)}/{len(chromosomes)}")
            if failed_chromosomes:
                logger.warning(f"  ❌ Failed: {len(failed_chromosomes)}")
                for chrom, error in failed_chromosomes:
                    logger.warning(f"    - {chrom}: {error}")
            logger.info(f"{'='*80}\n")
            
            return results
    
    def _run_multi_context(self) -> MethylModelerResult:
        """Run multi-context analysis (new unified approach)."""
        logger.info(f"🧬 Starting multi-context analysis for chromosome {self.chromosome}")
        logger.info(f"📍 Contexts: {', '.join(self.config.contexts)}")

        # Require binned_stats on centroids (ECDF-based metrics); fail fast before any context
        self._require_binned_stats_available()

        # Validate centroid parameters before analysis
        self._validate_centroid_parameters()

        all_dmps = []  # List to collect DataFrames from each context
        
        # Loop over all contexts
        for context in self.config.contexts:
            logger.info(f"🔬 Processing context: {context}")
            
            # Build paths to centroid files
            c1_path = Path(self.config.centroid1_dir) / f"{self.chromosome}-{context}.h5"
            c2_path = Path(self.config.centroid2_dir) / f"{self.chromosome}-{context}.h5"
            
            # Check if files exist
            if not c1_path.exists():
                logger.warning(f"Centroid1 file not found: {c1_path}, skipping context {context}")
                continue
            if not c2_path.exists():
                logger.warning(f"Centroid2 file not found: {c2_path}, skipping context {context}")
                continue
            
            # Detect DMPs for this context
            try:
                dmp_df = self._detect_statistical_dmps_for_context(c1_path, c2_path, context)
                logger.info(f"✅ Context {context}: {len(dmp_df):,} statistical DMPs detected")
                all_dmps.append(dmp_df)
            except Exception as e:
                logger.error(f"❌ Context {context} failed: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        if not all_dmps:
            raise ValueError("No DMPs detected in any context")
        
        # Combine all contexts into single DataFrame
        logger.info("📊 Combining all contexts into unified DataFrame...")
        dmps_df = pd.concat(all_dmps, ignore_index=True)
        logger.info(f"✅ Combined DataFrame: {len(dmps_df):,} total DMPs across {len(all_dmps)} contexts")
        
        # Compute context weights and add to DataFrame
        if self.config.use_context_weights:
            logger.info("⚖️  Computing context weights using trimmed-mean normalization...")
            dmps_df = self._compute_context_weights(dmps_df)
            
            # Log weights
            weight_summary = dmps_df.groupby('context')['context_weight'].first().to_dict()
            for ctx, w in sorted(weight_summary.items()):
                logger.info(f"  Context {ctx}: weight = {w:.4f}")
        else:
            # Equal weights
            dmps_df['context_weight'] = 1.0 / len(self.config.contexts)
            logger.info("Using equal context weights")

        # Optional: filter funnel sweep (range/step per biological filter → filter_funnel.csv)
        self._run_filter_funnel_sweep(dmps_df)
        
        # Filter biological DMPs (apply biological filters)
        logger.info("🔬 Filtering biologically significant DMPs...")
        bio_dmps_df = self._filter_biological_dmps(dmps_df)
        n_bio, n_stat = len(bio_dmps_df), len(dmps_df)
        pct = f"{n_bio / n_stat * 100:.1f}%" if n_stat and n_stat > 0 else "N/A"
        logger.info(f"✅ Biological DMPs: {n_bio:,} (retention: {pct})")

        bio_dmps_df = bio_dmps_df.sort_values("effect_size", ascending=False).reset_index(drop=True)
        logger.info("📊 Biological DMPs sorted by effect_size")

        # Optional: BMM refinement stage (detector-level)
        if self.config.bmm_refine_enabled:
            logger.info("🧪 Running BMM refinement stage (detector-level)...")
            bio_dmps_df = self._refine_dmps_with_bmm(bio_dmps_df)
            logger.info(f"✅ BMM refinement complete: {len(bio_dmps_df):,} DMPs retained")

            # Save BMM centroid for downstream use (per chromosome/context)
            if self.config.output_dir:
                self._save_bmm_centroids(Path(self.config.output_dir))
            if self.config.bmm_refine_use_gpu and self.gpu_config.GPU_AVAILABLE:
                cleanup_gpu_memory()
                logger.debug("Cleaned GPU memory after BMM refinement")
        
        # Compute biological importance and sort
        logger.info("📋 Sorting DMPs by biological importance...")
        sorted_by_importance_df = self._compute_biological_importance(bio_dmps_df)
        
        # Export pre-optimization DMPs (biological-sorted)
        if self.config.output_dir:
            logger.info("💾 Exporting DMPs sorted by importance (pre-optimization)...")
            self._export_unified_csv(sorted_by_importance_df, suffix="-biological-sorted")
        
        # DMP selection with validation and optional optimization (featurecuts / bayesian / binary_search)
        selected_dmps_df = self._select_dmps_multicontext(bio_dmps_df, sorted_df=sorted_by_importance_df)
        
        # Export final selected DMPs and save classifier when output_dir is set
        if self.config.output_dir:
            logger.info("💾 Exporting final selected DMPs...")
            self._export_unified_csv(selected_dmps_df, suffix="")
            self._save_unified_model(None, selected_dmps_df)
            self._save_validation_results(
                n_dmps_exported=len(selected_dmps_df),
                total_statistical_dmps=len(dmps_df),
                total_biological_dmps=len(bio_dmps_df),
            )
        
        # Create result (use selected DMPs for result stats)
        result = self._create_multi_context_result(dmps_df, selected_dmps_df)
        logger.info(f"✅ Multi-context analysis complete for chromosome {self.chromosome}!")
        
        return result
   
    def timer(func):
        """Decorator to time and log function execution."""
        import time
        import functools
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            logger.info(f"⏱️ Entering {func.__name__} at {start_time:.2f}")
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                logger.info(f"⏱️ Exiting {func.__name__} after {duration:.2f}s")
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.error(f"⏱️ {func.__name__} failed after {duration:.2f}s: {e}")
                raise
        return wrapper

    def _require_binned_stats_available(self) -> None:
        """Require that centroids have binned_stats (ECDF-based metrics). Raise at start of run if missing."""
        context0 = self.config.contexts[0] if self.config.contexts else "CG"
        c1_path = Path(self.config.centroid1_dir) / f"{self.chromosome}-{context0}.h5"
        c2_path = Path(self.config.centroid2_dir) / f"{self.chromosome}-{context0}.h5"
        if not c1_path.exists():
            raise FileNotFoundError(
                f"Centroid1 file not found: {c1_path}. "
                "MethylDetector requires centroids with binned_stats; build them first (methyl-centroid with binned_stats_bins, default 20)."
            )
        if not c2_path.exists():
            raise FileNotFoundError(
                f"Centroid2 file not found: {c2_path}. "
                "MethylDetector requires centroids with binned_stats; build them first (methyl-centroid with binned_stats_bins, default 20)."
            )
        centroid = MethylSample.load_from_h5(str(c1_path))
        binned = getattr(centroid, "binned_stats", None)
        if not binned or "bin_edges" not in binned or "bin_counts" not in binned:
            raise ValueError(
                "Centroids must have binned_stats for MethylDetector (continuous ECDF overlap and effect_size). "
                "Re-run methyl-centroid with binned_stats_bins (e.g. base_config.binned_stats_bins=20, or use default 20). "
                "If you already did, check that the H5 files at "
                "centroid1_dir/centroid2_dir are the ones just built (e.g. Python: MethylSample.load_from_h5(path).binned_stats)."
            )

    def _detect_statistical_dmps_for_context(
        self, 
        centroid1_path: Path, 
        centroid2_path: Path, 
        context: str
    ) -> pd.DataFrame:
        """
        Detect statistical DMPs for a specific context.
        
        Args:
            centroid1_path: Path to centroid1 H5 file
            centroid2_path: Path to centroid2 H5 file
            context: Context string (e.g., "CG", "CHG", "CHH")
            
        Returns:
            DataFrame with DMPs including chromosome and context columns
        """
        logger.debug(f"Processing centroids for context {context}...")
        
        # Load and align centroids
        min_coverage = self.config.effective_min_N(10)  # Fallback cohort size
        centroid1, centroid2, common_positions = MethylCentroidPair.load_and_align(
            centroid1_path, 
            centroid2_path, 
            min_coverage=min_coverage
        )
        
        # Determine cohort size
        max_coverage = max(centroid1.N.max() if centroid1.N is not None else 0,
                          centroid2.N.max() if centroid2.N is not None else 0)
        cohort_size = max(max_coverage, 10)
        effective_min_coverage = self.config.effective_min_N(cohort_size)
        
        # Pre-filter positions by delta_mean before the expensive statistical comparison.
        # This uses only the centroid means (N, Sx), which are cheap to evaluate, to
        # reduce the tested set from millions of positions down to those that could ever
        # survive the biological filter.  Any position with |delta_mean| < gate would be
        # discarded by the biological filter anyway, so testing it first is wasted work.
        delta_gate = getattr(self.config, "delta_mean_reduction", None)
        if delta_gate is None:
            delta_gate = self.config.min_delta_mean

        import time
        pre_filter_position_subset = None
        if delta_gate is not None:
            pos1 = np.asarray(centroid1.pos.values, dtype=np.uint32)
            pos2 = np.asarray(centroid2.pos.values, dtype=np.uint32)
            common_pre = np.intersect1d(pos1, pos2)
            idx1_pre = np.searchsorted(pos1, common_pre, side="left")
            idx2_pre = np.searchsorted(pos2, common_pre, side="left")
            m1 = np.asarray(centroid1.mean)[idx1_pre]
            m2 = np.asarray(centroid2.mean)[idx2_pre]
            dm_mask = np.abs(m1 - m2) >= float(delta_gate)
            pre_filter_position_subset = common_pre[dm_mask]
            n_pre = int(dm_mask.sum())
            logger.info(
                "Context %s: pre-filter |delta_mean| >= %.3f reduces %s → %s positions "
                "before statistical test",
                context,
                delta_gate,
                f"{len(common_pre):,}",
                f"{n_pre:,}",
            )

        # Create centroid pair for comparison
        centroid_pair = MethylCentroidPair(
            min_coverage=effective_min_coverage,
            delta_mean_mode=self.config.delta_mean_mode,
            overlap_mode=self.config.overlap_mode,
            distribution=self.config.distribution,
            max_N_for_ecdf=getattr(self.config, "max_N_for_ecdf", 30),
        )

        # Compare centroids (only at pre-filtered positions when the gate is active)
        start_time = time.time()
        comparison_results = centroid_pair.compare_centroids(
            centroid1, centroid2, position_subset=pre_filter_position_subset
        )
        processing_time = time.time() - start_time

        logger.info(f"Context {context}: Compared {len(comparison_results):,} positions in {processing_time:.2f}s")

        # Apply EAT transformation if enabled
        logger.debug(f"EAT debug: enable_eat_transform={self.config.enable_eat_transform}, EAT_AVAILABLE={EAT_AVAILABLE}")
        if self.config.enable_eat_transform:
            logger.info("🧬 EAT transformation is ENABLED in config")
            if not EAT_AVAILABLE:
                logger.warning("EAT transformation enabled but compute_eat_T not available, skipping")
                logger.warning(f"EAT_AVAILABLE={EAT_AVAILABLE}, compute_eat_T={compute_eat_T}")
            else:
                logger.info("🧬 Applying EAT transformation to enhance DMP detection...")
                logger.info(f"   EAT parameters: gamma={self.config.eat_gamma}, clip_T={self.config.eat_clip_t}, norm={self.config.eat_normalization}")
                try:
                    comparison_results = self._apply_eat_transformation(comparison_results, centroid1, centroid2, context)
                    logger.info("✅ EAT transformation applied successfully")
                except Exception as e:
                    logger.error(f"❌ EAT transformation failed: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    logger.warning("Continuing without EAT transformation")
                    # Continue with original comparison_results

        # Apply statistical filtering
        total_positions = len(comparison_results)
        filtered_results = comparison_results[comparison_results['q_value'] <= self.config.alpha].copy()
        statistical_dmps_count = len(filtered_results)

        logger.info(
            f"Context {context}: {statistical_dmps_count:,} significant DMPs (q≤{self.config.alpha}) "
            f"out of {total_positions:,} ({(statistical_dmps_count / total_positions) * 100:.1f}% pass rate)"
            if total_positions > 0 else
            f"Context {context}: 0 significant DMPs (no positions tested)"
        )

        # The delta_mean gate was already applied before compare_centroids, so every
        # position in filtered_results already satisfies |delta_mean| >= gate.  The
        # post-filter below is kept as a safety guard for the case where the gate was
        # not active (e.g. delta_mean_reduction and min_delta_mean are both None).
        _gate = getattr(self.config, "delta_mean_reduction", None) or self.config.min_delta_mean
        dmp_df = filtered_results.copy()
        if _gate is not None and "delta_mean" in dmp_df.columns:
            dmp_df = dmp_df[np.abs(dmp_df["delta_mean"].astype(float)) >= float(_gate)].copy()
        logger.info(
            "Context %s: %s positions after statistical + delta_mean filter%s",
            context,
            f"{len(dmp_df):,}",
            "" if _gate is None else f" (|delta_mean| >= {_gate})",
        )

        # Build ECDFViews lazily: only for the DMP positions that survived the statistical
        # and delta_mean filters.  This avoids building millions of PchipInterpolator objects
        # for the full centroid (which would be 68M for CHH) when only tens to hundreds of
        # positions are actually needed.
        #
        # Correct per-centroid index lookup: the index into centroid2's bin_counts array is
        # *not* the same as the index into centroid1's array unless both centroids happen to
        # have identical position orderings.  Using centroid1 indices for centroid2 is the
        # root cause of the silent ECDF mismatch bug.  Here we derive independent indices for
        # each centroid so the sliced ECDFViews are always positionally aligned.
        if len(dmp_df) > 0:
            dmp_positions = np.asarray(dmp_df["position"].values, dtype=np.uint32)
            pos1 = np.asarray(centroid1.pos.values, dtype=np.uint32)
            pos2 = np.asarray(centroid2.pos.values, dtype=np.uint32)
            idx_in_c1 = np.searchsorted(pos1, dmp_positions, side="left")
            idx_in_c2 = np.searchsorted(pos2, dmp_positions, side="left")
            bs1 = centroid1.binned_stats
            bs2 = centroid2.binned_stats
            bin_edges_arr = np.asarray(bs1["bin_edges"], dtype=np.float64)
            from methyl_utils.core.distribution_views import ECDFView
            ecdf_view1 = ECDFView(
                bin_edges_arr,
                np.asarray(bs1["bin_counts"], dtype=np.float64)[idx_in_c1],
                np.asarray(centroid1.Sx.values, dtype=np.float64)[idx_in_c1],
                np.asarray(centroid1.N.values, dtype=np.float64)[idx_in_c1],
                np.asarray(centroid1.Sx2.values, dtype=np.float64)[idx_in_c1],
            )
            ecdf_view2 = ECDFView(
                bin_edges_arr,
                np.asarray(bs2["bin_counts"], dtype=np.float64)[idx_in_c2],
                np.asarray(centroid2.Sx.values, dtype=np.float64)[idx_in_c2],
                np.asarray(centroid2.N.values, dtype=np.float64)[idx_in_c2],
                np.asarray(centroid2.Sx2.values, dtype=np.float64)[idx_in_c2],
            )
            logger.info(
                "Context %s: built ECDFViews for %s DMP positions (lazy, not full centroid)",
                context, f"{len(dmp_positions):,}",
            )
        else:
            ecdf_view1 = ecdf_view2 = None

        # Sequential 0-based row indices match the sliced ECDFViews row-for-row.
        dmp_df = self._compute_missing_metrics_df(
            dmp_df,
            ecdf_view1=ecdf_view1,
            ecdf_view2=ecdf_view2,
        )
        if "effect_size" in dmp_df.columns and len(dmp_df) > 0:
            from scipy.stats import rankdata
            bes = dmp_df["effect_size"].values.astype(np.float64)
            ranks = rankdata(bes)
            dmp_df["effect_size_ecdf"] = (ranks - 0.5) / len(ranks)

        # Add chromosome and context columns
        dmp_df['chromosome'] = self.chromosome
        dmp_df['context'] = context

        return dmp_df

    def _apply_eat_transformation(self, comparison_results: pd.DataFrame,
                                centroid1: MethylSample, centroid2: MethylSample,
                                context: str) -> pd.DataFrame:
        """
        Apply Entropy-weighted Asymmetry Transformation (EAT) to enhance DMP detection.

        EAT reweights loci based on Beta distribution shape differences to emphasize
        biologically meaningful methylation differences and de-emphasize loci with
        high/indistinguishable entropy.

        Args:
            comparison_results: DataFrame with statistical comparison results
            centroid1, centroid2: MethylSample centroids
            context: Methylation context (for logging)

        Returns:
            Modified comparison_results with EAT-enhanced statistics
        """
        if not EAT_AVAILABLE or compute_eat_T is None:
            logger.warning("EAT transformation requested but compute_eat_T not available, skipping")
            return comparison_results

        # Extract Beta parameters from comparison results
        alpha_H = comparison_results['alpha1'].values  # Healthy centroid
        beta_H = comparison_results['beta1'].values
        alpha_C = comparison_results['alpha2'].values  # Cancer centroid
        beta_C = comparison_results['beta2'].values

        # Compute EAT distortion vector
        T = compute_eat_T(
            alpha_H=alpha_H, beta_H=beta_H,
            alpha_C=alpha_C, beta_C=beta_C,
            gamma=self.config.eat_gamma,
            clip_T=self.config.eat_clip_t,
            eps=1e-12,
            low_tau_threshold=self.config.eat_low_tau_threshold,
            use_loggamma=True,
            use_gpu=self.config.use_gpu
        )

        # Apply EAT transformation to enhance biological significance
        modified_results = comparison_results.copy()

        # Store original values for comparison
        modified_results['delta_mean_raw'] = modified_results['delta_mean'].copy()
        modified_results['p_value_raw'] = modified_results['p_value'].copy()

        # EAT Strategy: Focus on biological relevance rather than statistical significance
        # 1. Amplify delta_mean for biologically important positions (T > 1)
        # 2. Use T to modulate statistical thresholds rather than p-values directly

        # Conservative EAT application: only amplify positions with high biological importance
        # Use absolute T as importance score - amplify positions with |T| > 1.0
        importance_weight = np.abs(T)
        high_importance_mask = importance_weight > 1.0

        # For high importance positions, amplify their delta_mean by the importance weight
        if np.any(high_importance_mask):
            amplification_factor = np.clip(importance_weight[high_importance_mask], 1.0, 3.0)  # Limit to 3x amplification
            modified_results.loc[high_importance_mask, 'delta_mean'] = (
                modified_results.loc[high_importance_mask, 'delta_mean'] * amplification_factor
            )

        # For positions with high EAT score (|T| > 1.5), make them more statistically significant
        # by slightly reducing p-values (making them pass statistical filters more easily)
        high_importance_mask = np.abs(T) > 1.5
        if np.any(high_importance_mask):
            # Reduce p-values for high-importance positions (more significant)
            boost_factor = 1.3  # 30% decrease in p-values
            modified_results.loc[high_importance_mask, 'p_value'] = (
                modified_results.loc[high_importance_mask, 'p_value'] / boost_factor
            )

        # For positions with low EAT score (|T| < 0.5), make them less statistically significant
        # by slightly increasing p-values (less likely to pass filters)
        low_importance_mask = np.abs(T) < 0.5
        if np.any(low_importance_mask):
            # Increase p-values for low-importance positions (less significant)
            # Use a small penalty factor to avoid divide by zero
            penalty_factor = 1.2  # 20% increase in p-values
            modified_results.loc[low_importance_mask, 'p_value'] = (
                modified_results.loc[low_importance_mask, 'p_value'] * penalty_factor
            )

        # Recompute q-values after p-value modifications
        from statsmodels.stats.multitest import multipletests
        reject, q_values, _, _ = multipletests(
            modified_results['p_value'].values,
            alpha=self.config.alpha,
            method='fdr_bh'
        )
        modified_results['q_value'] = q_values

        # Add EAT metadata
        modified_results['eat_T'] = T
        modified_results['eat_applied'] = True

        eat_stats = {
            'mean_T': float(np.mean(T)),
            'std_T': float(np.std(T)),
            'min_T': float(np.min(T)),
            'max_T': float(np.max(T)),
            'positions_modified': len(T)
        }

        logger.info(f"🧬 EAT applied to {len(comparison_results)} positions in context {context}")
        logger.info(f"   T stats: mean={eat_stats['mean_T']:.3f}, std={eat_stats['std_T']:.3f}, "
                   f"range=[{eat_stats['min_T']:.3f}, {eat_stats['max_T']:.3f}]")

        # Check if T values are meaningful
        t_range = eat_stats['max_T'] - eat_stats['min_T']
        if t_range < 0.1:
            logger.warning(f"⚠️  EAT T values have very small range ({t_range:.3f}), transformation may have minimal effect")
        elif eat_stats['std_T'] < 0.05:
            logger.warning(f"⚠️  EAT T values have low variance (std={eat_stats['std_T']:.3f}), transformation may have minimal effect")

        # Debug: Check modifications
        delta_raw = modified_results['delta_mean_raw'].abs()
        delta_new = modified_results['delta_mean'].abs()
        delta_change_pct = ((delta_new - delta_raw) / (delta_raw + 1e-12)).mean() * 100

        p_raw = modified_results['p_value_raw']
        p_new = modified_results['p_value']
        p_change_pct = ((p_new - p_raw) / (p_raw + 1e-12)).mean() * 100

        # Count positions that changed significance
        sig_before = (modified_results['p_value_raw'] <= self.config.alpha).sum()
        sig_after = (modified_results['p_value'] <= self.config.alpha).sum()
        sig_change = sig_after - sig_before

        logger.info(f"   Delta_mean change: {delta_change_pct:+.1f}% average")
        logger.info(f"   P-value change: {p_change_pct:+.1f}% average")
        logger.info(f"   Significance change: {sig_change:+d} positions (before: {sig_before}, after: {sig_after})")

        return modified_results

    def _compute_context_weights(self, dmps_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute trimmed-mean context weights and add to DataFrame.
        
        Uses trimmed mean (removing top and bottom percentiles) to compute
        robust average effect size per context, then normalizes to sum=1.
        
        Args:
            dmps_df: DataFrame with 'context' and 'effect_size' columns
            
        Returns:
            DataFrame with added 'context_weight' column
        """
        if 'effect_size' not in dmps_df.columns:
            raise ValueError("DataFrame must have 'effect_size' column for context weighting")
        weight_map = {}

        # Compute trimmed mean per context using effect_size
        for context, group in dmps_df.groupby('context'):
            S = group['effect_size'].values
            
            # Calculate asymmetric trimmed percentiles
            # Remove more from bottom (low effect sizes) and less from top (high effect sizes are important)
            qlo = self.config.trimmed_percentile_low
            qhi = 1.0 - self.config.trimmed_percentile_high
            q_low, q_high = np.quantile(S, [qlo, qhi])
            
            # Keep only trimmed values
            S_trimmed = S[(S >= q_low) & (S <= q_high)]
            
            # Compute mean (fallback to full mean if trimmed is empty)
            if len(S_trimmed) > 0:
                w_c = S_trimmed.mean()
            else:
                w_c = S.mean() if len(S) > 0 else 0.0
            
            weight_map[context] = w_c
        
        # Normalize weights to sum=1
        total_weight = sum(weight_map.values())
        if total_weight > 0:
            # Compute raw (unnormalized) weights for logging
            raw_weights = weight_map.copy()
            weight_map = {k: v / total_weight for k, v in weight_map.items()}
        else:
            # Fallback to equal weights if all zeros
            n_contexts = len(weight_map)
            weight_map = {k: 1.0 / n_contexts for k in weight_map.keys()}
            logger.warning("All context weights are zero, using equal weights")
            raw_weights = weight_map.copy()
        
        # Log summary table showing why weights differ
        logger.info("")
        logger.info("="*60)
        logger.info("Context Weighting Summary (Trimmed-Mean Normalization):")
        logger.info("="*60)
        logger.info(f"{'Context':<10} {'N_DMPs':>10} {'Mean_EffectSize':>16} {'Weight':>10}")
        logger.info("-" * 50)
        for ctx in sorted(weight_map.keys()):
            n_dmps = len(dmps_df[dmps_df['context'] == ctx])
            logger.info(f"{ctx:<10} {n_dmps:>10,} {raw_weights[ctx]:>16.4f} {weight_map[ctx]:>10.4f}")
        logger.info("-" * 50)
        logger.info("Note: Weights are based on average effect_size after trimming, not raw delta_mean.")
        logger.info("      effect_size combines |delta_mean|, continuous overlap, and the lambda_var variance penalty.")
        logger.info("      Trimmed: bottom %.0f%%, top %.0f%%. Higher weight = stronger separation.", self.config.trimmed_percentile_low * 100, self.config.trimmed_percentile_high * 100)
        logger.info("="*60)
        logger.info("")
        
        # Map weights to DataFrame
        dmps_df['context_weight'] = dmps_df['context'].map(weight_map)
        
        return dmps_df
    
    def _filter_biological_dmps(self, dmps_df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter DMPs by biological significance (ECDF-based). All set filters are applied (AND):
        - min_delta_mean: keep |delta_mean| >= value
        - max_overlap: keep overlap <= value (continuous ECDF overlap)
        - min_effect_size: keep effect_size >= value (or effect_size_quantile: keep >= empirical quantile)
        """
        initial_count = len(dmps_df)
        min_eff = self.config.min_effect_size
        if getattr(self.config, "effect_size_quantile", None) is not None:
            if "effect_size" in dmps_df.columns and len(dmps_df) > 0:
                threshold = float(np.percentile(dmps_df["effect_size"].astype(float), 100.0 * self.config.effect_size_quantile))
                min_eff = threshold if min_eff is None else max(min_eff, threshold)
                logger.info(
                    "Effect size quantile cut: %.2f → threshold = %.4f (effect_size >= threshold)",
                    self.config.effect_size_quantile,
                    threshold,
                )
        bio_df = _apply_biological_filters(
            dmps_df,
            self.config.min_delta_mean,
            self.config.max_overlap,
            min_effect_size=min_eff,
        )
        # Log per-filter retention (intermediate counts for messages)
        prev_count = initial_count
        _pct = lambda n, d: f"{n / d * 100:.1f}%" if d and d > 0 else "N/A"
        if self.config.min_delta_mean is not None and "delta_mean" in dmps_df.columns:
            step_df = _apply_biological_filters(dmps_df, self.config.min_delta_mean, None, None)
            n = len(step_df)
            logger.info(
                f"After min_delta_mean filter (|delta_mean| ≥ {self.config.min_delta_mean}): "
                f"{n:,} DMPs ({_pct(n, prev_count)} retained)"
            )
            prev_count = n
        if self.config.max_overlap is not None and "overlap" in dmps_df.columns:
            step_df = _apply_biological_filters(dmps_df, self.config.min_delta_mean, self.config.max_overlap, None)
            n = len(step_df)
            logger.info(
                f"After max_overlap filter (overlap ≤ {self.config.max_overlap}): "
                f"{n:,} DMPs ({_pct(n, prev_count)} retained)"
            )
            prev_count = n
        if min_eff is not None and "effect_size" in dmps_df.columns:
            n = len(bio_df)
            logger.info(
                f"After min_effect_size filter (effect_size ≥ {min_eff}): "
                f"{n:,} DMPs ({_pct(n, prev_count)} retained)"
            )
        if initial_count != len(bio_df):
            logger.info(
                f"Biological filter total: {len(bio_df):,} DMPs ({_pct(len(bio_df), initial_count)} of initial)"
            )

        # Log and store value ranges of delta_mean, overlap, effect_size for retained DMPs
        thresholds_used = {}
        if self.config.min_delta_mean is not None:
            thresholds_used["min_delta_mean"] = self.config.min_delta_mean
        if self.config.max_overlap is not None:
            thresholds_used["max_overlap"] = self.config.max_overlap
        if min_eff is not None:
            thresholds_used["min_effect_size"] = min_eff
        if getattr(self.config, "effect_size_quantile", None) is not None:
            thresholds_used["effect_size_quantile"] = self.config.effect_size_quantile

        value_ranges = {}
        for col, label in [("delta_mean", "delta_mean"), ("overlap", "overlap"), ("effect_size", "effect_size")]:
            if col in bio_df.columns and len(bio_df) > 0:
                ser = bio_df[col].astype(float)
                value_ranges[label] = {"min": float(ser.min()), "max": float(ser.max())}
                logger.info(
                    f"  Retained DMPs {label}: min = {value_ranges[label]['min']:.4f}, max = {value_ranges[label]['max']:.4f}"
                )

        self._biological_filter_summary = {
            "thresholds": thresholds_used,
            "value_ranges": value_ranges,
        }
        return bio_df

    def _range_step_values(self, spec) -> List[float]:
        """Build [min, min+step, ...] up to max from a FilterFunnelRangeSpec (inclusive max)."""
        vals: List[float] = []
        x = spec.min
        while x <= spec.max + 1e-12:
            vals.append(round(x, 10))
            x += spec.step
        return vals

    def _run_filter_funnel_sweep(self, dmps_df: pd.DataFrame) -> None:
        """
        If filter_funnel_explore is set, sweep biological filter values and write filter_funnel.csv.
        CSV columns: n_statistical_dmps, min_delta_mean, max_overlap, min_effect_size, n_biological_dmps.
        Uses statistical DMPs already in memory; one run, no large DMP CSV.
        """
        explore = self.config.filter_funnel_explore
        if explore is None or self.config.output_dir is None:
            return
        # At least one filter must have a range spec
        has_any = (
            explore.min_delta_mean is not None
            or explore.max_overlap is not None
            or explore.min_effect_size is not None
        )
        if not has_any:
            return

        n_statistical = len(dmps_df)
        run_min_delta = self.config.min_delta_mean
        run_max_overlap = self.config.max_overlap
        run_min_effect_size = self.config.min_effect_size

        csv_rows: List[Dict[str, Any]] = []
        mode = explore.mode
        csv_columns = ["n_statistical_dmps", "min_delta_mean", "max_overlap", "min_effect_size", "n_biological_dmps"]

        if mode == "one_at_a_time":
            if explore.min_delta_mean is not None:
                for v in self._range_step_values(explore.min_delta_mean):
                    n = len(
                        _apply_biological_filters(dmps_df, v, run_max_overlap, run_min_effect_size)
                    )
                    csv_rows.append({
                        "n_statistical_dmps": n_statistical,
                        "min_delta_mean": v,
                        "max_overlap": run_max_overlap,
                        "min_effect_size": run_min_effect_size,
                        "n_biological_dmps": n,
                    })
            if explore.max_overlap is not None:
                for v in self._range_step_values(explore.max_overlap):
                    n = len(
                        _apply_biological_filters(dmps_df, run_min_delta, v, run_min_effect_size)
                    )
                    csv_rows.append({
                        "n_statistical_dmps": n_statistical,
                        "min_delta_mean": run_min_delta,
                        "max_overlap": v,
                        "min_effect_size": run_min_effect_size,
                        "n_biological_dmps": n,
                    })
            if explore.min_effect_size is not None:
                for v in self._range_step_values(explore.min_effect_size):
                    n = len(
                        _apply_biological_filters(dmps_df, run_min_delta, run_max_overlap, v)
                    )
                    csv_rows.append({
                        "n_statistical_dmps": n_statistical,
                        "min_delta_mean": run_min_delta,
                        "max_overlap": run_max_overlap,
                        "min_effect_size": v,
                        "n_biological_dmps": n,
                    })
        else:
            vals_delta = (
                self._range_step_values(explore.min_delta_mean)
                if explore.min_delta_mean is not None
                else ([run_min_delta] if run_min_delta is not None else [None])
            )
            vals_overlap = (
                self._range_step_values(explore.max_overlap)
                if explore.max_overlap is not None
                else ([run_max_overlap] if run_max_overlap is not None else [None])
            )
            vals_effect_size = (
                self._range_step_values(explore.min_effect_size)
                if explore.min_effect_size is not None
                else ([run_min_effect_size] if run_min_effect_size is not None else [None])
            )
            for md, mo, me in itertools.product(vals_delta, vals_overlap, vals_effect_size):
                n = len(_apply_biological_filters(dmps_df, md, mo, me))
                csv_rows.append({
                    "n_statistical_dmps": n_statistical,
                    "min_delta_mean": md,
                    "max_overlap": mo,
                    "min_effect_size": me,
                    "n_biological_dmps": n,
                })

        out_path = Path(self.config.output_dir) / "filter_funnel.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        save_csv(csv_rows, out_path, csv_columns)
        logger.info(f"📊 Filter funnel: wrote {len(csv_rows)} rows to {out_path}")

    def _load_binned_counts_from_centroids(
        self,
        dmps_df: pd.DataFrame
    ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """
        Load per-position bin counts from centroid H5 files for given DMPs.

        Returns:
            (bin_edges, counts1, counts2) or None if not available.
        """
        from methyl_utils import MethylCentroidPair
        return MethylCentroidPair.load_binned_counts_from_centroids(
            dmps_df,
            self.config.centroid1_dir,
            self.config.centroid2_dir,
            self.chromosome,
        )

    def _refine_dmps_with_bmm(self, dmps_df: pd.DataFrame) -> pd.DataFrame:
        """
        Refine DMPs using per-position Beta Mixture Models (BMMs).

        Delegates to MethylCentroidPair for centroid-centric refinement logic.
        """
        if dmps_df is None or dmps_df.empty:
            return dmps_df

        from methyl_utils import MethylCentroidPair

        # Resolve sample paths
        class1_paths = self.config.centroid1_validation_samples
        class2_paths = self.config.centroid2_validation_samples
        if class1_paths is None and self.config.bmm_refine_use_metadata_samples:
            class1_paths = "use_metadata"
        if class2_paths is None and self.config.bmm_refine_use_metadata_samples:
            class2_paths = "use_metadata"

        class1_paths = self._get_validation_samples(class1_paths, self.config.centroid1_dir, "centroid1")
        class2_paths = self._get_validation_samples(class2_paths, self.config.centroid2_dir, "centroid2")

        bmm_config = {
            "bmm_refine_max_dmps": self.config.bmm_refine_max_dmps,
            "bmm_refine_max_fraction": self.config.bmm_refine_max_fraction,
            "bmm_refine_use_binned_stats": self.config.bmm_refine_use_binned_stats,
            "bmm_refine_bin_count": self.config.bmm_refine_bin_count,
            "bmm_refine_min_samples_per_group": self.config.bmm_refine_min_samples_per_group,
            "bmm_refine_max_samples_per_group": self.config.bmm_refine_max_samples_per_group,
            "bmm_refine_max_components": self.config.bmm_refine_max_components,
            "bmm_refine_use_gpu": self.config.bmm_refine_use_gpu,
            "bmm_refine_js_threshold": self.config.bmm_refine_js_threshold,
            "bmm_refine_skip_delta_mean": self.config.bmm_refine_skip_delta_mean,
            "bmm_refine_skip_overlap": self.config.bmm_refine_skip_overlap,
            "bmm_refine_mc_samples": self.config.bmm_refine_mc_samples,
            "bmm_refine_use_metadata_samples": self.config.bmm_refine_use_metadata_samples,
            "bmm_refine_replace_p_value": self.config.bmm_refine_replace_p_value,
            "bmm_refine_recompute_q": self.config.bmm_refine_recompute_q,
            "bmm_refine_mode": self.config.bmm_refine_mode,
            "bmm_refine_filter_metric": self.config.bmm_refine_filter_metric,
            "bmm_refine_pvalue_threshold": self.config.bmm_refine_pvalue_threshold,
            "random_state": self.config.random_state,
        }

        extraction_min = self.config.validation_min_coverage
        pair = MethylCentroidPair(min_coverage=extraction_min)
        contexts = self.config.contexts
        merged, bmm_c1, bmm_c2, records_map, bmm_summary = pair.refine_dmps_with_bmm(
            dmps_df=dmps_df,
            centroid1_dir=self.config.centroid1_dir,
            centroid2_dir=self.config.centroid2_dir,
            chromosome=self.chromosome,
            class1_paths=class1_paths,
            class2_paths=class2_paths,
            contexts=contexts,
            bmm_config=bmm_config,
            load_validation_samples_fn=self._load_validation_samples_multicontext_impl,
        )

        self._bmm_centroid_c1 = bmm_c1
        self._bmm_centroid_c2 = bmm_c2
        if bmm_c1 is not None:
            self._bmm_centroid = bmm_c1
        self._bmm_records_map = records_map
        self._bmm_summary = bmm_summary

        return merged

    def _save_bmm_centroids(self, output_dir: Path) -> None:
        """Save BMM centroids per context for downstream use."""
        centroids = []
        if getattr(self, "_bmm_centroid_c1", None) is not None:
            centroids.append(("centroid1", self._bmm_centroid_c1))
        if getattr(self, "_bmm_centroid_c2", None) is not None:
            centroids.append(("centroid2", self._bmm_centroid_c2))
        if not centroids and self._bmm_centroid is not None:
            centroids.append(("centroid1", self._bmm_centroid))

        if not centroids:
            return

        out_dir = output_dir / "bmm_centroids"
        out_dir.mkdir(parents=True, exist_ok=True)
        saved_files = []

        for label, centroid_obj in centroids:
            bmm_df = centroid_obj.df
            mask_df = centroid_obj.mask

            contexts = set()
            if bmm_df is not None and not bmm_df.empty and "context" in bmm_df.columns:
                contexts.update(bmm_df["context"].dropna().unique().tolist())
            if mask_df is not None and not mask_df.empty and "context" in mask_df.columns:
                contexts.update(mask_df["context"].dropna().unique().tolist())

            if not contexts:
                continue

            for ctx in sorted(contexts):
                ctx_df = bmm_df[bmm_df["context"] == ctx].copy() if bmm_df is not None else pd.DataFrame()
                ctx_mask = mask_df[mask_df["context"] == ctx].copy() if mask_df is not None else None

                metadata = dict(centroid_obj.metadata or {})
                metadata.update({
                    "chromosome": self.chromosome,
                    "context": ctx,
                    "record_count": int(len(ctx_df)),
                    "mask_count": int(len(ctx_mask)) if ctx_mask is not None else 0,
                    "group": label,
                    "source": metadata.get("source", "detector_bmm_refine"),
                })

                centroid = MethylBetaMixtureCentroid.from_dataframe(
                    ctx_df,
                    metadata=metadata,
                    mask=ctx_mask,
                )

                if label == "centroid1":
                    out_path = out_dir / f"bmm-centroid-{self.chromosome}-{ctx}.json"
                else:
                    out_path = out_dir / f"bmm-centroid-{self.chromosome}-{ctx}-{label}.json"
                centroid.to_json(out_path)
                saved_files.append(str(out_path))

        if saved_files:
            logger.info(f"Saved BMM centroids to {out_dir}")
            self._bmm_centroid_files = saved_files

    def _build_bmm_mixture_arrays(self, dmps_df: pd.DataFrame) -> Optional[Dict[str, List[Optional[List[float]]]]]:
        """Build per-position BMM mixture arrays aligned to DMP DataFrame."""
        record_map = getattr(self, "_bmm_records_map", None)
        if not record_map:
            return None

        mix = {
            "mix_weights1": [],
            "mix_alphas1": [],
            "mix_betas1": [],
            "mix_weights2": [],
            "mix_alphas2": [],
            "mix_betas2": [],
        }

        for _, row in dmps_df.iterrows():
            pos = int(row["position"])
            ctx = row.get("context", "CG")
            key = (pos, ctx)
            rec = record_map.get(key)

            if rec and rec.get("status") == "fit" and rec.get("weights1") and rec.get("weights2"):
                mix["mix_weights1"].append(rec.get("weights1"))
                mix["mix_alphas1"].append(rec.get("alphas1"))
                mix["mix_betas1"].append(rec.get("betas1"))
                mix["mix_weights2"].append(rec.get("weights2"))
                mix["mix_alphas2"].append(rec.get("alphas2"))
                mix["mix_betas2"].append(rec.get("betas2"))
            else:
                mix["mix_weights1"].append(None)
                mix["mix_alphas1"].append(None)
                mix["mix_betas1"].append(None)
                mix["mix_weights2"].append(None)
                mix["mix_alphas2"].append(None)
                mix["mix_betas2"].append(None)

        if not any(v is not None for v in mix["mix_weights1"]):
            return None

        return mix

    def _attach_bmm_mixtures(self, classifier, dmps_df: pd.DataFrame) -> bool:
        """Attach BMM mixture parameters to a classifier if available."""
        mix = self._build_bmm_mixture_arrays(dmps_df)
        if not mix:
            return False

        for key, value in mix.items():
            setattr(classifier, key, value)
            try:
                classifier.data[key] = value
            except Exception:
                pass

        return True
    
    def _compute_biological_importance(self, dmps_df: pd.DataFrame) -> pd.DataFrame:
        """
        Sort DMPs by effect_size (single biological importance measure).
        No separate importance column; effect_size is used everywhere downstream.
        """
        df = dmps_df.copy()
        if "effect_size" not in df.columns:
            raise ValueError("DMPs DataFrame must have 'effect_size'")
        df = df.sort_values("effect_size", ascending=False).reset_index(drop=True)
        return df

    def _get_validation_samples(
        self,
        config_samples: Optional[Union[str, List[str]]],
        centroid_dir: Optional[str],
        centroid_name: str
    ) -> List[str]:
        """
        Get validation sample paths from config or centroid metadata.
        
        Args:
            config_samples: Config value - can be "use_metadata", a list of paths, or None
            centroid_dir: Directory containing centroids
            centroid_name: Name of centroid for logging (e.g., "centroid1")
            
        Returns:
            List of validation sample paths
        """
        from methyl_utils import MethylCentroidPair
        contexts = self.config.contexts if hasattr(self.config, 'contexts') else None
        return MethylCentroidPair.resolve_validation_samples(
            config_samples,
            centroid_dir,
            self.chromosome,
            contexts=contexts,
            centroid_name=centroid_name,
        )
    
    def _generate_synthetic_validation_samples(
        self,
        dmps_df: pd.DataFrame
    ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
        """
        Generate synthetic validation samples from Beta distributions.
        
        Args:
            dmps_df: DataFrame with DMPs including alpha1, beta1, alpha2, beta2
            
        Returns:
            Tuple of (X_calib, y_calib, X_test, y_test, positions, contexts)
        """
        try:
            from scipy.stats import beta as beta_dist
            
            n_samples_per_class = self.config.n_validation_samples
            
            # Extract DMP parameters
            positions = dmps_df['position'].values
            contexts = dmps_df['context'].values
            alpha1 = dmps_df['alpha1'].values
            beta1 = dmps_df['beta1'].values
            alpha2 = dmps_df['alpha2'].values
            beta2 = dmps_df['beta2'].values
            
            n_positions = len(positions)
            
            logger.info(f"Generating {n_samples_per_class} synthetic samples per class from {n_positions:,} DMPs...")
            
            # Generate class 1 (healthy) samples with realistic biological variation
            X_class1 = np.zeros((n_samples_per_class, n_positions))
            for i in range(n_positions):
                # Use the centroid parameters directly, but add measurement noise
                # Biological variation should be simulated by sampling from the centroid distribution
                # but with some additional noise to account for technical variation
                base_samples = beta_dist.rvs(alpha1[i], beta1[i], size=n_samples_per_class, random_state=self.config.random_state + i)
                # Add small amount of technical noise (SD ~ 0.01)
                technical_noise = np.random.normal(0, 0.01, size=n_samples_per_class)
                X_class1[:, i] = np.clip(base_samples + technical_noise, 0, 1)

            # Generate class 2 (cancer) samples with realistic biological variation
            X_class2 = np.zeros((n_samples_per_class, n_positions))
            for i in range(n_positions):
                # Use the centroid parameters directly, but add measurement noise
                base_samples = beta_dist.rvs(alpha2[i], beta2[i], size=n_samples_per_class, random_state=self.config.random_state + n_positions + i)
                # Add small amount of technical noise (SD ~ 0.01)
                technical_noise = np.random.normal(0, 0.01, size=n_samples_per_class)
                X_class2[:, i] = np.clip(base_samples + technical_noise, 0, 1)
            
            # Combine classes
            X_all = np.vstack([X_class1, X_class2])
            y_all = np.concatenate([np.zeros(n_samples_per_class, dtype=int), np.ones(n_samples_per_class, dtype=int)])

            # Debug: Check synthetic data statistics
            mean_class1 = np.mean(X_class1, axis=0)
            mean_class2 = np.mean(X_class2, axis=0)
            logger.info(f"✅ Generated {len(X_all)} synthetic samples")
            logger.info(f"Synthetic data stats: Class1 mean={np.mean(mean_class1):.4f}, Class2 mean={np.mean(mean_class2):.4f}")
            logger.info(f"Sample methylation ranges: Class1 [{np.min(X_class1):.4f}, {np.max(X_class1):.4f}], Class2 [{np.min(X_class2):.4f}, {np.max(X_class2):.4f}]")
            
            # Return unsplit data - splitting is handled by the caller
            return X_all, y_all, positions, contexts
            
        except Exception as e:
            logger.error(f"Failed to generate synthetic samples: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _load_validation_samples_multicontext(
        self,
        dmps_df: pd.DataFrame
    ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
        """
        Load validation samples for multi-context optimization.
        
        Requires samples from BOTH centroid1 and centroid2 so that Balanced Accuracy
        (classifying between the two groups) can be computed. If only one group has
        samples, returns None and the caller falls back to synthetic validation.
        
        Returns:
            Tuple of (X, y, positions, contexts) or None if loading fails
            - X: methylation matrix (n_samples x n_positions)
            - y: labels (0 for class1, 1 for class2)
            - positions: genomic positions
            - contexts: methylation contexts
        """
        try:
            # Resolve validation sample paths: explicit config, else centroid metadata (samples_used), else none
            # When validation_mode is "real" (default), use centroid metadata if config does not specify paths.
            use_metadata_by_default = (self.config.validation_mode != 'synthetic')
            class1_config = self.config.centroid1_validation_samples
            if class1_config is None and use_metadata_by_default:
                class1_config = "use_metadata"
            class2_config = self.config.centroid2_validation_samples
            if class2_config is None and use_metadata_by_default:
                class2_config = "use_metadata"

            class1_paths = self._get_validation_samples(
                class1_config,
                self.config.centroid1_dir,
                "centroid1"
            )
            class2_paths = self._get_validation_samples(
                class2_config,
                self.config.centroid2_dir,
                "centroid2"
            )
            
            if not class1_paths and not class2_paths:
                logger.warning(
                    "No real validation samples (config and centroid metadata). "
                    "Falling back to synthetic validation samples."
                )
                return None

            # Balanced Accuracy requires both groups; we cannot classify between groups with only one.
            if not class1_paths or not class2_paths:
                logger.warning(
                    "Validation requires samples from BOTH centroid1 and centroid2 to compute Balanced Accuracy. "
                    "Got centroid1=%s, centroid2=%s. Falling back to synthetic validation samples."
                    % (len(class1_paths), len(class2_paths))
                )
                return None
            
            logger.info(f"Loading {len(class1_paths)} healthy + {len(class2_paths)} cancer validation samples...")
            
            # Use common implementation
            val_data = self._load_validation_samples_multicontext_impl(dmps_df, class1_paths, class2_paths)
            return val_data
            
        except Exception as e:
            logger.error(f"Failed to load validation samples: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _check_centroid_self_classification(self, dmps_df: pd.DataFrame) -> None:
        """
        Sanity check: classify each centroid's methylation profile at the DMP positions.
        Each centroid should get probability ~1.0 for its own class. If not, positions
        or sample↔DMP alignment may be wrong.
        """
        if dmps_df is None or len(dmps_df) == 0:
            return
        try:
            if 'mean1' not in dmps_df.columns or 'mean2' not in dmps_df.columns:
                logger.debug("Skipping centroid self-check (no mean1/mean2 in DMP table)")
                return
            # Bounded weights (same as in _validate_classifier_subset)
            if 'effect_size' in dmps_df.columns:
                weights = dmps_df['effect_size'].values.copy()
            elif 'importance' in dmps_df.columns:
                weights = dmps_df['importance'].values.copy()
            else:
                weights = np.ones(len(dmps_df))
            if np.any(~np.isfinite(weights)) or np.any(weights <= 0):
                weights = np.where(np.isfinite(weights) & (weights > 0), weights, 1.0)
            w_max = float(np.max(weights))
            if w_max > 1e-6:
                weights = np.clip(weights / w_max, 1e-6, 1.0).astype(np.float64)
            dmpDF = pd.DataFrame({
                'pos': dmps_df['position'].values.astype(np.int64),
                'alpha1': dmps_df['alpha1'].values.astype(np.float64),
                'beta1': dmps_df['beta1'].values.astype(np.float64),
                'alpha2': dmps_df['alpha2'].values.astype(np.float64),
                'beta2': dmps_df['beta2'].values.astype(np.float64),
                'weight': weights
            })
            clf = BetaClassifier.from_dataframe(
                dmpDF,
                min_sample_coverage=self.config.min_sample_coverage,
                coverage_weighting=self.config.classifier_coverage_weighting
            )
            if self._attach_bmm_mixtures(clf, dmps_df):
                pass  # optional
            # Centroid1 profile = mean1 at each DMP (class 0); centroid2 = mean2 (class 1)
            profile_c1 = dmps_df['mean1'].values.astype(np.float64).reshape(1, -1)
            profile_c2 = dmps_df['mean2'].values.astype(np.float64).reshape(1, -1)
            profile_c1 = np.clip(profile_c1, 1e-6, 1.0 - 1e-6)
            profile_c2 = np.clip(profile_c2, 1e-6, 1.0 - 1e-6)
            avail = np.ones((1, len(dmps_df)), dtype=bool)
            debug = getattr(self.config, "debug", False)
            proba_c1 = clf.predict_proba(profile_c1, avail, debug=debug)[0]
            proba_c2 = clf.predict_proba(profile_c2, avail, debug=debug)[0]
            # P(class1): usually column 1; if classifier returns inverted (centroid1→high, centroid2→low), use column 0
            if proba_c1[1] > 0.5 and proba_c2[1] < 0.5:
                p_c1, p_c2 = proba_c1[0], proba_c2[0]
            else:
                p_c1, p_c2 = proba_c1[1], proba_c2[1]
            logger.info(
                "Centroid self-check (DMP positions): centroid1 → P(class1)=%.4f, centroid2 → P(class1)=%.4f "
                "(expect ~0 and ~1)",
                p_c1, p_c2
            )
            if p_c1 > 0.2 or p_c2 < 0.8:
                if p_c1 > 0.8 and p_c2 > 0.8:
                    logger.warning(
                        "Centroid self-check FAILED: both centroids classify as class1 (centroid1→%.2f, centroid2→%.2f). "
                        "Often due to poor centroid separation on this chromosome (see earlier 'Poor separation' / small delta_mean). "
                        "Validation BA may be low or meaningless.",
                        p_c1, p_c2
                    )
                elif p_c1 <= 0.2 and p_c2 <= 0.2:
                    logger.warning(
                        "Centroid self-check FAILED: both centroids classify as class0 (centroid1→P(class1)=%.2f, centroid2→%.2f). "
                        "Context/position merging matches the DMP list; this often happens when most positions use the Normal "
                        "approximation and class0 has smaller variance than class1, so the sum of log-normalizers favors class0. "
                        "Check centroid separation (delta_mean) or use a subset of well-separated DMPs. Validation BA may be low.",
                        p_c1, p_c2
                    )
                else:
                    logger.warning(
                        "Centroid self-check FAILED: centroid1 → P(class1)=%.2f, centroid2 → P(class1)=%.2f (expect ~0 and ~1). "
                        "Possible position/order mismatch between samples and DMP list. Validation BA may be meaningless.",
                        p_c1, p_c2
                    )
        except Exception as e:
            logger.warning("Centroid self-check failed: %s", e)

    def _validate_classifier_subset(
        self,
        dmps_subset: pd.DataFrame,
        X_calib: np.ndarray,
        y_calib: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray,
        all_positions: np.ndarray,
        all_contexts: np.ndarray
    ) -> dict:
        """
        Validate a DMP subset using BetaClassifier with proper train/test split.
        
        Args:
            dmps_subset: Subset of DMPs to validate
            X_calib: Calibration methylation matrix (for Platt fitting)
            y_calib: Calibration labels
            X_test: Test methylation matrix (for evaluation)
            y_test: Test labels
            all_positions: All validation positions
            all_contexts: All validation contexts
            
        Returns:
            Dictionary with balanced accuracy and metrics
        """
        try:
            # Get positions for this subset
            subset_positions = dmps_subset['position'].values
            subset_contexts = dmps_subset['context'].values
            
            # Find indices in validation data - VECTORIZED
            subset_indices = []
            for pos, ctx in zip(subset_positions, subset_contexts):
                matches = np.where((all_positions == pos) & (all_contexts == ctx))[0]
                if len(matches) > 0:
                    subset_indices.append(matches[0])
            
            subset_indices = np.array(subset_indices)
            
            if len(subset_indices) == 0:
                logger.warning("No matching positions found in validation data")
                return {
                    'balanced_accuracy': 0.5,
                    'confusion_matrix': {'tp': 0, 'tn': 0, 'fp': 0, 'fn': 0},
                    'metrics': {'sensitivity': 0.0, 'specificity': 0.0, 'accuracy': 0.0, 'precision': 0.0},
                    'counts': {'n_positive': 0, 'n_negative': 0, 'n_total': 0}
                }
            
            # Extract subset of positions
            X_calib_subset = X_calib[:, subset_indices]
            X_test_subset = X_test[:, subset_indices]
            
            # Get the actual positions/contexts that matched (in order)
            matched_positions = all_positions[subset_indices]
            matched_contexts = all_contexts[subset_indices]
            
            # Create temporary classifier using ONLY the matched DMPs
            matched_mask = np.isin(
                [f"{p}_{c}" for p, c in zip(subset_positions, subset_contexts)],
                [f"{p}_{c}" for p, c in zip(matched_positions, matched_contexts)]
            )
            dmps_for_classifier = dmps_subset[matched_mask].reset_index(drop=True)
            
            # Create dmpDF for BetaClassifier
            # Use effect_size (single biological importance measure from MethylCentroidPair)
            if 'effect_size' in dmps_for_classifier.columns:
                weights = dmps_for_classifier['effect_size'].values.copy()
                logger.debug("Using 'effect_size' for classifier weights")
            elif 'importance' in dmps_for_classifier.columns:
                weights = dmps_for_classifier['importance'].values.copy()
                logger.debug("Using 'importance' for weights (fallback); will bound to [1e-6, 1]")
            else:
                weights = np.ones(len(dmps_for_classifier))
                logger.warning("No weight column found, using ones")

            # Check for invalid weights
            if np.any(~np.isfinite(weights)) or np.any(weights <= 0):
                logger.warning(f"Invalid weights found: min={weights.min():.6f}, max={weights.max():.6f}, "
                              f"has_nan={np.any(np.isnan(weights))}, has_inf={np.any(np.isinf(weights))}")
                weights = np.where(np.isfinite(weights) & (weights > 0), weights, 1.0)

            # Always bound weights to [1e-6, 1] so no single DMP dominates
            w_max = float(np.max(weights))
            if w_max > 1e-6:
                weights = np.clip(weights / w_max, 1e-6, 1.0)

            # Low variability: skip for k=1 (single weight has no variance by definition). Otherwise error only if clearly wrong.
            w_std = weights.std()
            if np.all(weights == 0):
                logger.error(f"CRITICAL: All weights are zero for k={len(dmps_for_classifier)}!")
            elif len(dmps_for_classifier) >= 2 and w_std < 1e-6 and 'effect_size' not in dmps_for_classifier.columns:
                logger.error(f"CRITICAL: All weights nearly identical for k={len(dmps_for_classifier)}!")
            elif len(dmps_for_classifier) >= 2 and w_std < 1e-6:
                logger.debug("Weights from effect_size have very low std (expected when subset is similar); classifier may still be valid.")
            logger.debug(
                f"Classifier weights for k={len(dmps_for_classifier)}: min={weights.min():.6f}, max={weights.max():.6f}"
            )

            dmpDF = pd.DataFrame({
                'pos': dmps_for_classifier['position'].values.astype(np.int64),
                'alpha1': dmps_for_classifier['alpha1'].values.astype(np.float64),
                'beta1': dmps_for_classifier['beta1'].values.astype(np.float64),
                'alpha2': dmps_for_classifier['alpha2'].values.astype(np.float64),
                'beta2': dmps_for_classifier['beta2'].values.astype(np.float64),
                'weight': weights.astype(np.float64)
            })
            
            temp_classifier = BetaClassifier.from_dataframe(
                dmpDF,
                min_sample_coverage=self.config.min_sample_coverage,
                coverage_weighting=self.config.classifier_coverage_weighting
            )
            if self._attach_bmm_mixtures(temp_classifier, dmps_for_classifier):
                logger.debug("Attached BMM mixtures to validation classifier")

            # PHASE 1: Fit Platt calibration using calibration set (if supported)
            # BetaClassifier uses calibrate_platt method with methylation levels
            X_calib_subset_clean = X_calib_subset.copy()
            X_calib_subset_clean = np.nan_to_num(X_calib_subset_clean, nan=0.5)
            X_calib_subset_clean = np.clip(X_calib_subset_clean, 1e-6, 1-1e-6)

            # Create availability mask
            calib_availability = ~np.isnan(X_calib_subset)

            # Fit Platt calibration only if we have a proper train/test split
            # If validation_split_ratio=0, skip calibration to avoid overfitting
            use_calibration = False
            if hasattr(temp_classifier, 'calibrate_platt') and self.config.validation_split_ratio > 0:
                try:
                    temp_classifier.calibrate_platt(X_calib_subset_clean, y_calib, calib_availability)
                    use_calibration = True
                except Exception as e:
                    logger.warning(f"Platt calibration failed: {e}, using uncalibrated predictions")
            
            # PHASE 2: Evaluate on held-out test set
            X_test_subset_clean = X_test_subset.copy()
            X_test_subset_clean = np.nan_to_num(X_test_subset_clean, nan=0.5)
            X_test_subset_clean = np.clip(X_test_subset_clean, 1e-6, 1-1e-6)
            test_availability = ~np.isnan(X_test_subset)

            # Detect no per-sample variation (causes degenerate probabilities and BA=0.5)
            n_test, n_feat = X_test_subset.shape
            frac_valid = np.sum(~np.isnan(X_test_subset)) / max(1, X_test_subset.size)
            # Rows identical after NaN->0.5 fill => classifier gets same input => same probability for all
            row_var_clean = np.var(X_test_subset_clean, axis=1)
            all_rows_same = n_feat > 0 and n_test > 1 and np.all(row_var_clean < 1e-9)
            if frac_valid < 0.05 and not getattr(self, '_low_overlap_warned_once', False):
                self._low_overlap_warned_once = True
                logger.warning(
                    "Validation data has very low overlap with DMP positions: %.1f%% non-NaN. "
                    "Samples may not share positions with the DMP list (wrong chromosome/assay?). "
                    "Filled NaNs with 0.5 -> no discrimination -> BA≈0.5.",
                    frac_valid * 100
                )
            if all_rows_same and n_test > 1 and not getattr(self, '_no_variation_warned_once', False):
                self._no_variation_warned_once = True
                logger.warning(
                    "Validation test matrix has no per-sample variation (all rows nearly identical). "
                    "Classifier will output the same probability for every sample -> BA≈0.5. "
                    "Check that validation sample files contain the DMP positions for this chromosome/context."
                )

            logger.debug(
                f"Testing classifier with {len(dmps_for_classifier)} DMPs on {X_test_subset_clean.shape[0]} samples"
            )
            if use_calibration and hasattr(temp_classifier, 'predict_proba_calibrated') and temp_classifier.calibrator is not None:
                test_probas = temp_classifier.predict_proba_calibrated(X_test_subset_clean, test_availability)
            else:
                test_probas = temp_classifier.predict_proba(X_test_subset_clean, test_availability, debug=False)

            # Check if all probabilities are exactly 0.5
            all_class0_05 = np.allclose(test_probas[:, 0], 0.5, atol=1e-10)
            all_class1_05 = np.allclose(test_probas[:, 1], 0.5, atol=1e-10)
            if all_class0_05 and all_class1_05:
                logger.error("CRITICAL: All probabilities are exactly 0.500000 - classifier is not working!")
                # Try to get intermediate values from classifier
                try:
                    # Try to access internal state if possible
                    logger.error(f"Classifier temperature: {getattr(temp_classifier, 'temperature', 'unknown')}")
                    logger.error(f"Classifier has calibrator: {temp_classifier.calibrator is not None}")
                except Exception:
                    pass
            
            # Debug: Log prediction statistics for first few k values
            if len(dmps_subset) <= 100:
                mean_prob = test_probas[:, 1].mean()
                std_prob = test_probas[:, 1].std()
                prob_range = test_probas[:, 1].max() - test_probas[:, 1].min()
                logger.debug(f"    k={len(dmps_subset):,}: probs mean={mean_prob:.4f}, std={std_prob:.4f}, range={prob_range:.4f}")
                
            # Warn if probabilities are completely degenerate (once per run)
            prob_range = test_probas[:, 1].max() - test_probas[:, 1].min()
            if prob_range < 0.01 and not getattr(self, '_degenerate_probs_warned_once', False):
                self._degenerate_probs_warned_once = True
                logger.warning(
                    "Degenerate probabilities (range=%.6f, mean=%.6f) -> BA≈0.5. See 'low overlap' / 'no per-sample variation' above.",
                    prob_range, test_probas[:, 1].mean()
                )
            
            # Extract probabilities for class 1 (centroid2/cancer)
            probabilities = test_probas[:, 1].tolist()
            y_pred = np.argmax(test_probas, axis=1)
            
            # Compute metrics on TEST set only
            probabilities = np.array(probabilities)
            
            # Compute confusion matrix on TEST set
            tp = np.sum((y_pred == 1) & (y_test == 1))
            tn = np.sum((y_pred == 0) & (y_test == 0))
            fp = np.sum((y_pred == 1) & (y_test == 0))
            fn = np.sum((y_pred == 0) & (y_test == 1))
            
            # Compute balanced accuracy
            n_pos = tp + fn
            n_neg = tn + fp
            
            sensitivity = tp / n_pos if n_pos > 0 else 0.0
            specificity = tn / n_neg if n_neg > 0 else 0.0
            
            balanced_accuracy = (sensitivity + specificity) / 2.0

            # Diagnose BA≈0.5 (coin toss): usually means classifier predicts one class only
            n_pred_0 = int(np.sum(y_pred == 0))
            n_pred_1 = int(np.sum(y_pred == 1))
            if 0.48 <= balanced_accuracy <= 0.52 and (n_pos > 0 and n_neg > 0):
                if not getattr(self, '_ba_05_warned_once', False):
                    self._ba_05_warned_once = True
                    logger.warning(
                        "BA≈0.5 (coin toss): classifier is predicting only one class. "
                        "Predicted: %s class0, %s class1 | True: %s class0, %s class1. "
                        "Possible causes: (1) validation data has no overlap with DMP positions (all NaN -> 0.5), "
                        "(2) validation columns vs DMP order mismatch, "
                        "(3) one dominant weight or invalid alpha/beta. See earlier 'no per-sample variation' / 'low overlap' warnings.",
                        n_pred_0, n_pred_1, n_neg, n_pos
                    )
                else:
                    logger.debug("BA≈0.5 again: pred %s/%s, true %s/%s", n_pred_0, n_pred_1, n_neg, n_pos)
            
            # Return both balanced accuracy and confusion matrix details
            result = {
                'balanced_accuracy': balanced_accuracy,
                'confusion_matrix': {
                    'tp': int(tp), 'tn': int(tn), 'fp': int(fp), 'fn': int(fn)
                },
                'metrics': {
                    'sensitivity': sensitivity,
                    'specificity': specificity,
                    'accuracy': (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0.0,
                    'precision': tp / (tp + fp) if (tp + fp) > 0 else 0.0
                },
                'counts': {
                    'n_positive': int(n_pos),
                    'n_negative': int(n_neg),
                    'n_total': int(n_pos + n_neg)
                }
            }
            # Include fitted Platt calibrator for export when enabled (so MethylClassifier can use it)
            if use_calibration and self.config.enable_platt_calibration and temp_classifier.calibrator is not None:
                import pickle
                result['platt_calibrator'] = pickle.dumps(temp_classifier.calibrator)
                if getattr(temp_classifier, 'calibrator_scaler', None) is not None:
                    result['platt_calibrator_scaler'] = pickle.dumps(temp_classifier.calibrator_scaler)
            return result
            
        except Exception as e:
            logger.error(f"❌ Validation failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                'balanced_accuracy': 0.5,
                'confusion_matrix': {'tp': 0, 'tn': 0, 'fp': 0, 'fn': 0},
                'metrics': {'sensitivity': 0.0, 'specificity': 0.0, 'accuracy': 0.0, 'precision': 0.0},
                'counts': {'n_positive': 0, 'n_negative': 0, 'n_total': 0}
            }
    
    def _validate_centroid_parameters(self) -> None:
        """
        Log centroid summary: mean, variance, ECDF availability, and KS between ECDFs (sampled).
        Correct group classification is checked by the centroid self-check when building the classifier.
        """
        from pathlib import Path

        logger.info("🔍 Centroid summary (CG context)...")

        try:
            context = "CG"
            centroid1_path = Path(self.config.centroid1_dir) / f"{self.chromosome}-{context}.h5"
            centroid2_path = Path(self.config.centroid2_dir) / f"{self.chromosome}-{context}.h5"

            if not centroid1_path.exists() or not centroid2_path.exists():
                logger.debug("Skipping centroid summary: CG files not found")
                return

            centroid1 = MethylSample.load_from_h5(str(centroid1_path))
            centroid2 = MethylSample.load_from_h5(str(centroid2_path))
            results = MethylCentroidPair.validate_centroid_parameters(centroid1, centroid2)

            if "error" in results:
                logger.warning(f"Centroid summary failed: {results['error']}")
                return

            c1, c2 = results["centroid1"], results["centroid2"]
            logger.info("Centroid1: %s positions, N = %.1f ± %.1f", c1["n_positions"], c1["sample_stats"]["mean_N"], c1["sample_stats"]["std_N"])
            logger.info("  mean (median) = %.4f, variance (median) = %.6f, ECDF = %s", c1["mean_median"], c1["variance_median"], "yes" if c1["has_ecdf"] else "no")
            logger.info("Centroid2: %s positions, N = %.1f ± %.1f", c2["n_positions"], c2["sample_stats"]["mean_N"], c2["sample_stats"]["std_N"])
            logger.info("  mean (median) = %.4f, variance (median) = %.6f, ECDF = %s", c2["mean_median"], c2["variance_median"], "yes" if c2["has_ecdf"] else "no")
            logger.info("Trimmed mean |Δβ| (group separation) = %.4f", results["group_separation"])

            # KS between ECDFs on a sample of positions (low performance hit); use aligned centroids
            if c1["has_ecdf"] and c2["has_ecdf"]:
                try:
                    from methyl_utils.core.distribution_views import get_distribution_view
                    from methyl_utils.statistical_tests import ecdf_ks_statistic
                    cent1, cent2, _ = MethylCentroidPair.load_and_align(str(centroid1_path), str(centroid2_path), min_coverage=1)
                    n_pos = len(cent1)
                    sample_size = min(500, max(100, n_pos // 1000))
                    rng = np.random.default_rng(42)
                    position_indices = rng.choice(n_pos, size=sample_size, replace=False).astype(np.intp)
                    ecdf1 = get_distribution_view(cent1, "ecdf")
                    ecdf2 = get_distribution_view(cent2, "ecdf")
                    ks_sample = ecdf_ks_statistic(ecdf1, ecdf2, position_indices, grid_size=128)
                    logger.info("ECDF KS (sample of %s positions): median = %.4f, mean = %.4f", sample_size, float(np.median(ks_sample)), float(np.mean(ks_sample)))
                except Exception as e:
                    logger.debug("ECDF KS summary skipped: %s", e)

        except Exception as e:
            logger.debug("Centroid summary failed: %s", e)

    def _validate_selected_dmps(self, selected_dmps_df: pd.DataFrame, sorted_df: Optional[pd.DataFrame] = None) -> Optional[dict]:
        """
        Validate selected DMPs without optimization.
        
        This method performs validation even when optimize_dmps=False to report
        classifier performance on the selected DMP set.
        
        Args:
            selected_dmps_df: DataFrame with selected DMPs to validate
            sorted_df: Optional sorted DataFrame (for consistency, not used here)
            
        Returns:
            Validation results dict or None if validation fails
        """
        try:
            n_dmps = len(selected_dmps_df)
            if n_dmps == 0:
                logger.warning("Cannot validate: no DMPs selected")
                return None
            
            # Load or generate validation samples
            validation_data = None
            if self.config.validation_mode == "real":
                logger.info("📊 Loading validation samples...")
                validation_data = self._load_validation_samples_multicontext(selected_dmps_df)
                if validation_data is None:
                    logger.warning("Failed to load validation samples")
                    return None
                    
                X_val, y_val, val_positions, val_contexts = validation_data
                logger.info(f"✅ Loaded {len(X_val)} validation samples with {len(val_positions)} positions")
                
                # Split validation set based on config
                if self.config.validation_split_ratio > 0:
                    n_samples = len(X_val)
                    test_ratio = self.config.validation_split_ratio
                    
                    # Stratified split to maintain class balance
                    idx_class0 = np.where(y_val == 0)[0]
                    idx_class1 = np.where(y_val == 1)[0]
                    
                    n_test_class0 = int(len(idx_class0) * test_ratio)
                    n_test_class1 = int(len(idx_class1) * test_ratio)
                    
                    np.random.seed(self.config.random_state)
                    test_idx_class0 = np.random.choice(idx_class0, n_test_class0, replace=False)
                    test_idx_class1 = np.random.choice(idx_class1, n_test_class1, replace=False)
                    
                    test_indices = np.concatenate([test_idx_class0, test_idx_class1])
                    calib_indices = np.array([i for i in range(n_samples) if i not in test_indices])
                    
                    X_calib, y_calib = X_val[calib_indices], y_val[calib_indices]
                    X_test, y_test = X_val[test_indices], y_val[test_indices]
                    
                    logger.info(f"   Split: {len(calib_indices)} calibration, {len(test_indices)} test (split_ratio={test_ratio})")
                else:
                    # No split: use all samples for both calibration and evaluation
                    X_calib, y_calib = X_val, y_val
                    X_test, y_test = X_val, y_val
                    logger.info(f"   Using all {len(X_val)} samples for BA (no holdout, validation_split_ratio=0)")
                
                validation_data = (X_calib, y_calib, X_test, y_test, val_positions, val_contexts)
            else:
                # Synthetic validation mode
                logger.info("📊 Generating synthetic validation samples from Beta distributions...")
                validation_data = self._generate_synthetic_validation_samples(selected_dmps_df)
                if validation_data is None:
                    logger.warning("Failed to generate synthetic samples")
                    return None
            
            # Unpack validation data
            X_calib, y_calib, X_test, y_test, val_positions, val_contexts = validation_data
            
            # Validate the selected DMPs
            result = self._validate_classifier_subset(
                selected_dmps_df,
                X_calib, y_calib,
                X_test, y_test,
                val_positions, val_contexts
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _select_dmps_multicontext(self, bio_dmps_df: pd.DataFrame, sorted_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """
        Prepare DMPs for validation and optimization in multi-context mode.

        Loads validation data and sorts DMPs by biological importance.
        Returns all DMPs for subsequent optimization if enabled.

        Args:
            bio_dmps_df: DataFrame of biologically filtered DMPs
            sorted_df: Optional pre-computed sorted DataFrame (to avoid recomputation)

        Returns:
            DataFrame with sorted DMPs ready for optimization
        """
        n_dmps = len(bio_dmps_df)
        self._ba_05_warned_once = False
        self._low_overlap_warned_once = False
        self._no_variation_warned_once = False
        self._degenerate_probs_warned_once = False
        self._platt_calibrator_bytes = None
        self._platt_calibrator_scaler_bytes = None
        logger.info(f"🔍 Preparing DMPs for validation: {n_dmps:,} candidates")
        
        if n_dmps == 0:
            return bio_dmps_df
        
        # Compute importance scores and sort if not provided
        if sorted_df is None:
            logger.debug("Computing biological importance scores...")
            sorted_df = self._compute_biological_importance(bio_dmps_df)
        else:
            logger.debug("Using provided sorted DMPs (biological importance already computed)")

        # When optimization is disabled, return all biological DMPs (no coverage filter)
        if not self.config.optimize_dmps:
            logger.info("📋 optimize_dmps=False: using all %s biological DMPs (no validation coverage filter)", len(sorted_df))
            self._check_centroid_self_classification(sorted_df)
            return sorted_df

        # Load validation samples - try real first, then synthetic
        validation_data = None

        # First try real validation samples
        logger.info("📊 Loading real validation samples for optimization...")
        validation_data = self._load_validation_samples_multicontext(sorted_df)

        # Check if validation data has any valid methylation values
        if validation_data is not None:
            X_val, y_val, val_positions, val_contexts = validation_data
            n_valid_values = np.sum(~np.isnan(X_val))
            total_values = X_val.size
            valid_percentage = (n_valid_values / total_values) * 100

            logger.info(f"Validation data validity: {n_valid_values:,}/{total_values:,} values valid ({valid_percentage:.1f}%)")

            # Only fall back to synthetic if NO samples were loaded successfully
            # It's normal for validation samples to have NaN values at positions they don't cover
            if len(X_val) == 0:
                logger.warning("No validation samples loaded, falling back to synthetic data")
                validation_data = None

        if validation_data is None:
            # Fall back to synthetic validation samples
            logger.info("📊 Generating synthetic validation samples from centroids...")
            validation_data = self._generate_synthetic_validation_samples(sorted_df)

        if validation_data is not None:
            X_val, y_val, val_positions, val_contexts = validation_data
            logger.info(f"✅ Loaded {len(X_val)} validation samples with {len(val_positions)} positions")

            # Split validation set based on config
            if self.config.validation_split_ratio > 0:
                n_samples = len(X_val)
                test_ratio = self.config.validation_split_ratio
                idx_class0 = np.where(y_val == 0)[0]
                idx_class1 = np.where(y_val == 1)[0]
                n0, n1 = len(idx_class0), len(idx_class1)

                # BA requires both classes in BOTH calib and test; ensure at least 1 per class in test and in calib
                if n0 < 2 or n1 < 2:
                    logger.warning(
                        "Stratified split skipped: need at least 2 samples per class (got %s and %s). Using all samples for both calibration and evaluation.",
                        n0, n1
                    )
                    X_calib, y_calib = X_val, y_val
                    X_test, y_test = X_val, y_val
                else:
                    # Use ~test_ratio of total samples for test, with test set class-balanced
                    # (both classes represented in equal measure in the holdout)
                    target_test_size = max(2, int(round((n0 + n1) * test_ratio)))
                    half = target_test_size // 2
                    n_test_class0 = min(max(1, half), n0 - 1)
                    n_test_class1 = min(max(1, target_test_size - n_test_class0), n1 - 1)
                    np.random.seed(self.config.random_state)
                    test_idx_class0 = np.random.choice(idx_class0, n_test_class0, replace=False)
                    test_idx_class1 = np.random.choice(idx_class1, n_test_class1, replace=False)
                    test_indices = np.concatenate([test_idx_class0, test_idx_class1])
                    calib_indices = np.array([i for i in range(n_samples) if i not in test_indices])
                    X_calib, y_calib = X_val[calib_indices], y_val[calib_indices]
                    X_test, y_test = X_val[test_indices], y_val[test_indices]
                    logger.info(
                        f"   Split: {len(calib_indices)} calibration, {len(test_indices)} test "
                        f"(~{100*(1-test_ratio):.0f}% / ~{100*test_ratio:.0f}%), test set balanced "
                        f"(class0: {n_test_class0}, class1: {n_test_class1})"
                    )
            else:
                # No split: use all samples for both calibration and evaluation
                # User has separate independent test set
                X_calib, y_calib = X_val, y_val
                X_test, y_test = X_val, y_val
                logger.info(f"   Using all {len(X_val)} samples for BA (no holdout, validation_split_ratio=0)")

            # Store both sets for downstream optimization
            validation_data = (X_calib, y_calib, X_test, y_test, val_positions, val_contexts)
        else:
            logger.warning("Failed to load or generate validation samples, falling back to all DMPs")
            return sorted_df

        # Unpack validation data (now includes calibration split)
        X_calib, y_calib, X_test, y_test, val_positions, val_contexts = validation_data

        # Restrict to DMPs that have enough coverage in the TEST set so BA has signal (not all NaN -> 0.5)
        coverage_in_test = np.sum(~np.isnan(X_test), axis=0)
        n_test = X_test.shape[0]
        # Require at least 10% of test samples per position (or config min), so subset has usable non-NaN fraction
        min_by_fraction = max(1, int(np.ceil(0.1 * n_test)))
        min_coverage = max(min_by_fraction, self.config.min_validation_coverage_per_position)
        keep_mask = coverage_in_test >= min_coverage
        n_keep = int(np.sum(keep_mask))
        n_dropped = len(keep_mask) - n_keep
        if n_dropped > 0 and n_keep > 0:
            sorted_df = sorted_df.loc[keep_mask].reset_index(drop=True)
            X_calib = X_calib[:, keep_mask]
            X_test = X_test[:, keep_mask]
            val_positions = val_positions[keep_mask]
            val_contexts = val_contexts[keep_mask]
            logger.info(
                "Restricted to %s DMPs with ≥%s test-sample(s) per position (dropped %s with no test coverage) so BA can be computed.",
                n_keep, min_coverage, n_dropped
            )
        elif n_keep == 0:
            logger.warning(
                "No DMP positions have validation coverage in any sample; BA will be 0.5. "
                "Ensure validation samples cover the same chromosome/assay as the centroids."
            )
        n_dmps = len(sorted_df)

        # Sanity check: centroid profiles at DMP positions should classify as their own class (prob ~1)
        self._check_centroid_self_classification(sorted_df)

        selected_dmps_df = sorted_df
        final_result = None

        if self.config.optimize_dmps:
            logger.info("")
            logger.info(f"🎯 Starting DMP optimization with method={self.config.optimization_method}")

            max_k = n_dmps
            initial_k = None
            if max_k > 0:
                heuristic_k = max(10, n_dmps // 10)
                initial_k = max(1, min(max_k, heuristic_k))

            if self.config.optimization_method == "featurecuts":
                logger.info("🧬 FeatureCuts: maximizing balanced accuracy across candidate top-k subsets")

                optimized_k, optimized_result = self._optimize_dmps_featurecuts(
                    sorted_df,
                    max_k=max_k,
                    initial_k=initial_k,
                    X_calib=X_calib, y_calib=y_calib,
                    X_test=X_test, y_test=y_test,
                    val_positions=val_positions, val_contexts=val_contexts
                )

                optimized_k = int(max(1, min(optimized_k, max_k))) if max_k > 0 else 0
                selected_dmps_df = sorted_df.iloc[:optimized_k].copy()
                final_result = optimized_result
                self._final_validation_results = final_result

                cm = final_result['confusion_matrix']
                logger.info(
                    f"✅ FeatureCuts result: k={optimized_k:,}, BA={final_result['balanced_accuracy']:.4f}, "
                    f"TP={cm['tp']}, TN={cm['tn']}, FP={cm['fp']}, FN={cm['fn']}"
                )

            elif self.config.optimization_method == "bayesian_optimization":
                logger.info("🧬 Bayesian Optimization: maximizing balanced accuracy with GP surrogate model")

                optimized_k = self._optimize_dmps_bayesian(
                    sorted_df,
                    initial_k=initial_k,
                    max_k=max_k,
                    X_calib=X_calib, y_calib=y_calib,
                    X_test=X_test, y_test=y_test,
                    val_positions=val_positions, val_contexts=val_contexts
                )

                optimized_k = int(max(1, min(optimized_k, max_k))) if max_k > 0 else 0
                selected_dmps_df = sorted_df.iloc[:optimized_k].copy()

                final_result = self._validate_classifier_subset(
                    selected_dmps_df,
                    X_calib, y_calib,
                    X_test, y_test,
                    val_positions, val_contexts
                )
                self._final_validation_results = final_result

                cm = final_result['confusion_matrix']
                logger.info(
                    f"✅ Bayesian optimization result: k={optimized_k:,}, BA={final_result['balanced_accuracy']:.4f}, "
                    f"TP={cm['tp']}, TN={cm['tn']}, FP={cm['fp']}, FN={cm['fn']}"
                )

            elif self.config.optimization_method == "binary_search":
                logger.info("🔍 Binary Search: finding minimal k achieving target BA (monotonic assumption)")

                target_ba = self.config.target_balanced_accuracy
                logger.info(f"Target BA: {target_ba:.3f}")

                optimized_k = self._optimize_dmps_binary_search(
                    sorted_df,
                    target_ba=target_ba,
                    max_k=max_k,
                    X_calib=X_calib, y_calib=y_calib,
                    X_test=X_test, y_test=y_test,
                    val_positions=val_positions, val_contexts=val_contexts
                )

                optimized_k = int(max(1, min(optimized_k, max_k))) if max_k > 0 else 0
                selected_dmps_df = sorted_df.iloc[:optimized_k].copy()

                final_result = self._validate_classifier_subset(
                    selected_dmps_df,
                    X_calib, y_calib,
                    X_test, y_test,
                    val_positions, val_contexts
                )
                self._final_validation_results = final_result

                cm = final_result['confusion_matrix']
                logger.info(
                    f"✅ Binary search result: k={optimized_k:,}, BA={final_result['balanced_accuracy']:.4f}, "
                    f"TP={cm['tp']}, TN={cm['tn']}, FP={cm['fp']}, FN={cm['fn']}"
                )

            else:
                logger.warning(
                    f"Unknown optimization_method '{self.config.optimization_method}', skipping optimization step."
                )

            # When target BA is not achieved, export all DMPs to improve matching with future samples
            if final_result is not None:
                target_ba = self.config.target_balanced_accuracy
                if target_ba is not None and final_result.get('balanced_accuracy', 0) < target_ba:
                    selected_dmps_df = sorted_df.copy()
                    logger.info(
                        "Target BA %.3f not achieved; exporting all %s DMPs to improve matching with future samples.",
                        target_ba, len(sorted_df)
                    )
                # Store Platt calibrator from validation for inclusion in saved model (when enable_platt_calibration)
                if 'platt_calibrator' in final_result:
                    self._platt_calibrator_bytes = final_result['platt_calibrator']
                    self._platt_calibrator_scaler_bytes = final_result.get('platt_calibrator_scaler')
                else:
                    self._platt_calibrator_bytes = None
                    self._platt_calibrator_scaler_bytes = None

        # If we used synthetic validation, verify on real samples from centroid metadata
        if self.config.validation_mode == "synthetic":
            logger.info("")
            logger.info("🔬 Verifying model on real samples from centroid metadata...")
            real_validation = self._validate_on_real_samples(selected_dmps_df)
            if real_validation is not None:
                logger.info(f"✅ Real validation: BA={real_validation['balanced_accuracy']:.4f}")
                logger.info(f"   TP={real_validation['confusion_matrix']['tp']}, "
                          f"TN={real_validation['confusion_matrix']['tn']}, "
                          f"FP={real_validation['confusion_matrix']['fp']}, "
                          f"FN={real_validation['confusion_matrix']['fn']}")
                # Store real validation results alongside synthetic
                self._real_validation_results = real_validation
        
        return selected_dmps_df
    
    def _validate_on_real_samples(self, selected_dmps_df: pd.DataFrame) -> Optional[dict]:
        """
        Validate final model on real samples from centroid metadata.
        Used after synthetic optimization to verify real-world performance.
        
        Args:
            selected_dmps_df: Final selected DMPs
            
        Returns:
            Validation results dict or None if real samples not available
        """
        try:
            # Resolve real sample paths: config, else centroid metadata (samples_used)
            use_metadata_by_default = (self.config.validation_mode != 'synthetic')
            c1 = self.config.centroid1_validation_samples
            if c1 is None and use_metadata_by_default:
                c1 = "use_metadata"
            c2 = self.config.centroid2_validation_samples
            if c2 is None and use_metadata_by_default:
                c2 = "use_metadata"
            real_class1_paths = self._get_validation_samples(c1, self.config.centroid1_dir, "centroid1")
            real_class2_paths = self._get_validation_samples(c2, self.config.centroid2_dir, "centroid2")
            
            if not real_class1_paths and not real_class2_paths:
                logger.warning("No real samples available (config or centroid metadata) for verification")
                return None
            if not real_class1_paths or not real_class2_paths:
                logger.warning(
                    "Verification requires samples from both groups (got %s healthy, %s cancer). Skipping real verification.",
                    len(real_class1_paths), len(real_class2_paths)
                )
                return None
            
            logger.info(f"   Loading {len(real_class1_paths)} healthy + {len(real_class2_paths)} cancer samples for verification...")
            
            # Load real samples
            real_val_data = self._load_validation_samples_multicontext_impl(
                selected_dmps_df,
                real_class1_paths,
                real_class2_paths
            )
            
            if real_val_data is None:
                return None
            
            X_val, y_val, val_positions, val_contexts = real_val_data
            
            # Use all samples for validation (no need to split since we already optimized)
            X_calib = X_val[:int(len(X_val) * 0.7)]
            y_calib = y_val[:int(len(y_val) * 0.7)]
            X_test = X_val[int(len(X_val) * 0.7):]
            y_test = y_val[int(len(y_val) * 0.7):]
            
            # Validate
            result = self._validate_classifier_subset(
                selected_dmps_df,
                X_calib, y_calib,
                X_test, y_test,
                val_positions, val_contexts
            )
            
            return result
            
        except Exception as e:
            logger.warning(f"Failed to validate on real samples: {e}")
            return None
    
    def _load_validation_samples_multicontext_impl(
        self,
        dmps_df: pd.DataFrame,
        class1_paths: List[str],
        class2_paths: List[str],
        allow_mock: bool = True
    ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
        """
        Implementation of validation sample loading (extracted for reuse).

        Uses MethylCentroidPair to properly align validation samples to centroid positions.
        """
        from methyl_utils import MethylCentroidPair

        if not class1_paths and not class2_paths:
            return None

        # Balanced Accuracy requires both groups; reject single-class validation
        if not class1_paths or not class2_paths:
            logger.warning(
                "Validation data must include samples from both centroid1 and centroid2 (got %s and %s). Skipping.",
                len(class1_paths), len(class2_paths)
            )
            return None

        # Extract positions and contexts from DMPs
        dmp_positions = dmps_df['position'].values
        dmp_contexts = dmps_df['context'].values

        # Create methylation matrix
        all_sample_paths = [(p, 0) for p in class1_paths] + [(p, 1) for p in class2_paths]
        n_samples = len(all_sample_paths)
        n_positions = len(dmp_positions)
        logger.info(f"Loading validation data for {n_positions} DMP positions across {len(np.unique(dmp_contexts))} contexts")
        X = np.full((n_samples, n_positions), np.nan)  # Initialize with NaN
        y = np.zeros(n_samples, dtype=int)
        
        # Group DMP positions by context for efficient processing
        reference_positions = {}
        context_groups = {}
        for ctx in np.unique(dmp_contexts):
            ctx_mask = dmp_contexts == ctx
            ctx_positions = dmp_positions[ctx_mask]
            reference_positions[ctx] = ctx_positions.astype(np.uint32)
            context_groups[ctx] = {
                'indices': np.where(ctx_mask)[0],
                'positions': ctx_positions
            }

        # Use MethylCentroidPair to efficiently extract methylation fractions
        # Use validation_min_coverage (e.g. 4) so we get values at more positions when centroids were built with higher min_coverage (e.g. 10)
        extraction_min = self.config.validation_min_coverage
        logger.info("Extracting methylation fractions using MethylCentroidPair (min_coverage=%s)...", extraction_min)
        sample_paths_list = [p for p, _ in all_sample_paths]
        X_extracted, all_positions_extracted, all_contexts_extracted, context_indices_dict = MethylCentroidPair.extract_methylation_fractions(
            sample_paths=sample_paths_list,
            reference_positions=reference_positions,
            chromosome=self.chromosome,
            min_coverage=extraction_min
        )
        
        # Map extracted (position, context) back to DMP column index so X columns match DMP row order.
        # Extraction uses the same context order as reference_positions (→ config/DMP list order);
        # this (pos, ctx) key mapping guarantees alignment with the classifier's feature order.
        dmp_key_to_idx = {
            (int(dmp_positions[i]), str(dmp_contexts[i])): i
            for i in range(n_positions)
        }
        for i in range(X_extracted.shape[0]):
            for j in range(X_extracted.shape[1]):
                pos = all_positions_extracted[j]
                ctx = all_contexts_extracted[j]
                key = (int(pos), str(ctx))
                if key in dmp_key_to_idx:
                    dmp_idx = dmp_key_to_idx[key]
                    if not np.isnan(X_extracted[i, j]):
                        X[i, dmp_idx] = X_extracted[i, j]
        
        # Set labels
        for i, (_, label) in enumerate(all_sample_paths):
            y[i] = label
        
        successful_samples = np.sum(~np.isnan(X).all(axis=1))
        logger.info(f"Successfully loaded {successful_samples} out of {len(all_sample_paths)} validation samples")
        
        # If no samples loaded successfully, create mock validation data for testing alignment
        if successful_samples == 0 and allow_mock:
            logger.warning("No validation samples found, creating mock data to test alignment")
            # Create 10 mock samples (5 healthy, 5 cancer) with different methylation distributions
            mock_n_samples = 10
            np.random.seed(42)  # For reproducible results

            # Initialize with NaN (same as original approach) - n_positions should be the total DMP count
            logger.info(f"Creating mock data for {n_positions} total DMP positions")
            X = np.full((mock_n_samples, n_positions), np.nan)
            y = np.zeros(mock_n_samples, dtype=int)

            # Set labels: first 5 healthy (0), last 5 cancer (1)
            y[5:] = 1

            # Generate mock methylation data for each context
            for ctx in np.unique(dmp_contexts):
                ctx_mask = dmp_contexts == ctx
                ctx_indices = np.where(ctx_mask)[0]  # These are the indices in the full DMP array
                n_ctx_positions = len(ctx_indices)

                if n_ctx_positions > 0:
                    # Debug: check indices are in valid range
                    logger.debug(f"Context {ctx}: {n_ctx_positions} positions, indices {ctx_indices.min()}-{ctx_indices.max()}")

                    # Healthy samples: lower methylation for this context
                    X_healthy_ctx = np.random.beta(3, 1, (5, n_ctx_positions)).astype(np.float32)
                    # Cancer samples: higher methylation for this context
                    X_cancer_ctx = np.random.beta(1, 3, (5, n_ctx_positions)).astype(np.float32)

                    # Assign to the appropriate positions in the full matrix
                    X[:5, ctx_indices] = X_healthy_ctx  # Healthy samples
                    X[5:, ctx_indices] = X_cancer_ctx   # Cancer samples
                    logger.debug(f"Assigned mock data for context {ctx}")

            n_samples = mock_n_samples
            successful_samples = mock_n_samples
            logger.info(f"Created mock validation data: {mock_n_samples} samples with {n_positions} positions each")

        if successful_samples == 0:
            logger.error("No validation samples could be loaded and mock data creation failed")
            return None

        # Debug: Check how many positions have valid data
        n_valid_positions = np.sum(~np.isnan(X), axis=0)  # Count non-NaN per position
        positions_with_data = np.sum(n_valid_positions > 0)
        logger.info(f"Loaded validation data: X shape={X.shape}, y shape={y.shape}")
        logger.info(f"Position coverage: {positions_with_data}/{n_positions} positions have data in ≥1 sample")

        # Check per-sample coverage
        samples_with_data = []
        for i in range(n_samples):
            valid_positions = np.sum(~np.isnan(X[i, :]))
            samples_with_data.append(valid_positions)
            if i < 3:  # Log first few samples
                logger.debug(f"Sample {i}: {valid_positions}/{n_positions} positions with data")

        logger.debug(f"Sample coverage summary: min={min(samples_with_data)}, max={max(samples_with_data)}, mean={np.mean(samples_with_data):.1f}")

        # Confirm alignment: X column j corresponds to DMP row j (position=dmp_positions[j], context=dmp_contexts[j])
        if n_positions > 0:
            logger.info(
                "Validation columns aligned to DMP (position, context) order (join by position+context). "
                "First column: (pos, ctx)=(%s, %s), last: (%s, %s).",
                int(dmp_positions[0]), str(dmp_contexts[0]), int(dmp_positions[-1]), str(dmp_contexts[-1])
            )
        logger.info(f"Returning validation data: X.shape={X.shape}, y.shape={y.shape}, successful_samples={successful_samples}")
        return X, y, dmp_positions, dmp_contexts
    
    def _optimize_dmps_featurecuts(
        self,
        sorted_df: pd.DataFrame,
        max_k: int,
        X_calib: np.ndarray,
        y_calib: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray,
        val_positions: np.ndarray,
        val_contexts: np.ndarray,
        initial_k: Optional[int] = None
    ) -> Tuple[int, dict]:
        """
        Maximize balanced accuracy across candidate top-k cutoffs.

        When exhaustive_search=True, performs a comprehensive search:
        1. Coarse phase: Evaluates diverse k values across the range
        2. Refinement phase: Densely samples around top performers
        
        When exhaustive_search=False, uses fast logarithmic sampling (~20 candidates).

        Args:
            sorted_df: DMPs sorted by biological importance.
            max_k: Maximum number of DMPs available.
            X_calib, y_calib, X_test, y_test: Validation matrices and labels.
            val_positions, val_contexts: Position/context arrays for mapping.
            initial_k: Optional heuristic starting point for exploration.

        Returns:
            Tuple of (best_k, validation_result).
        """
        if max_k <= 0:
            logger.warning("FeatureCuts received empty candidate set; returning k=0")
            empty_result = self._validate_classifier_subset(
                sorted_df.iloc[:0],
                X_calib, y_calib,
                X_test, y_test,
                val_positions, val_contexts
            )
            return 0, empty_result

        min_k = 1 if max_k > 0 else 0
        exhaustive = self.config.featurecuts_exhaustive_search
        max_candidates = self.config.featurecuts_max_candidates

        logger.info(f"  FeatureCuts search range: k ∈ [{min_k:,}, {max_k:,}]")
        logger.info(f"  Exhaustive search: {exhaustive}")

        # Determine search strategy
        if exhaustive:
            # Exhaustive search: evaluate more candidates
            if max_candidates is None:
                # Auto-determine: use linear sampling for small ranges, capped for large
                if max_k <= 1000:
                    # For small ranges, evaluate all or nearly all
                    max_candidates = min(500, max_k - min_k + 1)
                else:
                    # For large ranges, use more aggressive sampling
                    max_candidates = min(500, int(max_k * 0.1))
            else:
                max_candidates = min(max_candidates, max_k - min_k + 1)
            
            logger.info(f"  Exhaustive mode: evaluating up to {max_candidates} candidates")
        else:
            # Fast mode: logarithmic sampling (~20 candidates)
            max_candidates = min(20, max_k - min_k + 1)
            logger.info(f"  Fast mode: evaluating {max_candidates} candidates")

        # Phase 1: Coarse search
        if max_k <= 50:
            # Small range: evaluate all
            candidate_k = np.arange(min_k, max_k + 1, dtype=np.int64)
        elif not exhaustive:
            # Fast mode: logarithmic sampling
            candidate_k = np.array([min_k, max_k], dtype=np.int64)
            if initial_k is not None:
                heuristic_k = np.clip(int(initial_k), min_k, max_k)
                candidate_k = np.append(candidate_k, heuristic_k)
            
            if max_k > min_k + 2:
                n_geom = max_candidates - candidate_k.size
                if n_geom > 0:
                    geom = np.geomspace(max(min_k, 1), max_k, n_geom)
                    candidate_k = np.append(candidate_k, geom.astype(np.int64))
        else:
            # Exhaustive mode: more comprehensive initial sampling
            # Start with boundary points and heuristic
            candidate_k = np.array([min_k, max_k], dtype=np.int64)
            if initial_k is not None:
                heuristic_k = np.clip(int(initial_k), min_k, max_k)
                candidate_k = np.append(candidate_k, heuristic_k)
            
            # Add logarithmic sampling for broad coverage
            n_log = min(50, max_candidates // 4)
            if max_k > min_k + 2 and n_log > 0:
                geom = np.geomspace(max(min_k, 1), max_k, n_log)
                candidate_k = np.append(candidate_k, geom.astype(np.int64))
            
            # Add linear sampling in the lower range (often where optimal k is)
            # Sample more densely in first 30% of range
            lower_bound = min_k
            upper_bound = int(min_k + (max_k - min_k) * 0.3)
            if upper_bound > lower_bound:
                n_linear = min(100, max_candidates // 2)
                linear_k = np.linspace(lower_bound, upper_bound, n_linear, dtype=np.int64)
                candidate_k = np.append(candidate_k, linear_k)
            
            # Add some linear sampling in mid-range
            mid_lower = int(min_k + (max_k - min_k) * 0.3)
            mid_upper = int(min_k + (max_k - min_k) * 0.7)
            if mid_upper > mid_lower:
                n_mid = min(50, max_candidates // 4)
                mid_k = np.linspace(mid_lower, mid_upper, n_mid, dtype=np.int64)
                candidate_k = np.append(candidate_k, mid_k)

        candidate_k = np.unique(np.clip(candidate_k, min_k, max_k))
        # Limit to max_candidates if we exceeded it
        if len(candidate_k) > max_candidates:
            # Keep boundaries and heuristic, then evenly sample the rest
            important = np.array([min_k, max_k])
            if initial_k is not None:
                important = np.append(important, np.clip(int(initial_k), min_k, max_k))
            important = np.unique(important)
            
            remaining_slots = max_candidates - len(important)
            if remaining_slots > 0:
                other_k = np.setdiff1d(candidate_k, important)
                if len(other_k) > remaining_slots:
                    # Evenly sample from remaining
                    indices = np.linspace(0, len(other_k) - 1, remaining_slots, dtype=np.int64)
                    sampled = other_k[indices]
                else:
                    sampled = other_k
                candidate_k = np.unique(np.concatenate([important, sampled]))
        
        candidate_k = np.sort(candidate_k)
        n_candidates = candidate_k.size
        
        ba_results = np.empty(n_candidates, dtype=np.float64)
        detailed_results = []
        
        logger.info(f"  Phase 1 (coarse): Evaluating {n_candidates} candidate k values...")
        
        # Track when BA=1.0 is achieved to optimize search
        ba_1_0_achieved_at_k = None  # Minimum k where BA=1.0 was achieved
        
        for i in range(n_candidates):
            k = int(candidate_k[i])
            
            # Optimization: Skip candidates >= k where BA=1.0 was already achieved
            # Since we want minimum k with BA=1.0, testing larger k values is wasteful
            if ba_1_0_achieved_at_k is not None and k >= ba_1_0_achieved_at_k:
                logger.info(f"    [{i+1}/{n_candidates}] k={k:,} → SKIPPED (BA=1.0 already achieved at k={ba_1_0_achieved_at_k:,})")
                # Fill with NaN or skip - we'll handle this later
                ba_results[i] = np.nan
                detailed_results.append(None)
                continue
            
            subset_df = sorted_df.iloc[:k]
            result = self._validate_classifier_subset(
                subset_df,
                X_calib, y_calib,
                X_test, y_test,
                val_positions, val_contexts
            )
            ba_results[i] = result['balanced_accuracy']
            detailed_results.append(result)
            
            # Track first k where BA=1.0 is achieved
            if ba_1_0_achieved_at_k is None and np.isclose(result['balanced_accuracy'], 1.0, atol=1e-6):
                ba_1_0_achieved_at_k = k
                logger.info(f"    [{i+1}/{n_candidates}] k={k:,} → BA={ba_results[i]:.6f} ⭐ BA=1.0 achieved! Will skip larger k values.")
            
            if i % max(1, n_candidates // 5) == 0 or i == n_candidates - 1 or np.isclose(ba_results[i], 1.0, atol=1e-6):
                logger.info(f"    [{i+1}/{n_candidates}] k={k:,} → BA={ba_results[i]:.6f}")

        # Filter out skipped (NaN) results before Phase 2
        valid_mask = ~np.isnan(ba_results)
        if not np.all(valid_mask):
            # Remove skipped evaluations
            candidate_k = candidate_k[valid_mask]
            ba_results = ba_results[valid_mask]
            detailed_results = [r for r, valid in zip(detailed_results, valid_mask) if valid]
            n_candidates = len(candidate_k)
            logger.info(f"  Phase 1 complete: {n_candidates} valid evaluations (skipped {np.sum(~valid_mask)} redundant candidates)")
        
        # Phase 2: Refinement around top candidates (only if exhaustive)
        if exhaustive and n_candidates > 5:
            # Find top 5 candidates
            top_indices = np.argsort(-ba_results)[:5]
            top_k_values = candidate_k[top_indices]
            
            # Optimization: If BA=1.0 was achieved, only refine around candidates with BA=1.0
            # and only look at values <= the minimum k that achieved BA=1.0
            if ba_1_0_achieved_at_k is not None:
                # Find all candidates with BA=1.0
                ba_1_0_mask = np.isclose(ba_results, 1.0, atol=1e-6)
                ba_1_0_k_values = candidate_k[ba_1_0_mask]
                
                if len(ba_1_0_k_values) > 0:
                    # Only refine around candidates with BA=1.0, and only below/at the minimum k
                    min_ba_1_0_k = int(ba_1_0_k_values.min())
                    logger.info(f"  Refinement: BA=1.0 achieved at k={min_ba_1_0_k:,}, only refining k <= {min_ba_1_0_k:,}")
                    # Get smallest k values with BA=1.0 (up to 5) for refinement
                    sorted_ba_1_0_k = np.sort(ba_1_0_k_values)[:5]
                    top_k_values = sorted_ba_1_0_k
                    max_refinement_k = min_ba_1_0_k  # Cap refinement range
                else:
                    max_refinement_k = max_k
            else:
                max_refinement_k = max_k
            
            # Refine around each top candidate
            refinement_candidates = []
            for top_k in top_k_values:
                # Sample densely in a window around this top candidate
                window_size = max(10, int((max_refinement_k - min_k) * 0.05))
                window_min = max(min_k, int(top_k - window_size))
                window_max = min(max_refinement_k, int(top_k + window_size))  # Cap at max_refinement_k
                
                # Add 20 points in this window
                if window_max > window_min:
                    refined = np.linspace(window_min, window_max, 20, dtype=np.int64)
                    refinement_candidates.extend(refined.tolist())
            
            # Remove duplicates and values already evaluated
            refinement_candidates = np.array(refinement_candidates, dtype=np.int64)
            refinement_candidates = np.unique(np.clip(refinement_candidates, min_k, max_refinement_k))  # Use max_refinement_k instead of max_k
            refinement_candidates = refinement_candidates[~np.isin(refinement_candidates, candidate_k)]
            
            if len(refinement_candidates) > 0:
                logger.info(f"  Phase 2 (refinement): Evaluating {len(refinement_candidates)} additional candidates around top performers...")
                
                # Evaluate refinement candidates
                refinement_ba = np.empty(len(refinement_candidates), dtype=np.float64)
                refinement_results = []
                
                for i, k in enumerate(refinement_candidates):
                    # Optimization: Skip if BA=1.0 was achieved and k >= minimum k with BA=1.0
                    if ba_1_0_achieved_at_k is not None and k >= ba_1_0_achieved_at_k:
                        logger.info(f"    [{i+1}/{len(refinement_candidates)}] k={k:,} → SKIPPED (BA=1.0 already achieved at k={ba_1_0_achieved_at_k:,})")
                        refinement_ba[i] = np.nan
                        refinement_results.append(None)
                        continue
                    
                    subset_df = sorted_df.iloc[:k]
                    result = self._validate_classifier_subset(
                        subset_df,
                        X_calib, y_calib,
                        X_test, y_test,
                        val_positions, val_contexts
                    )
                    refinement_ba[i] = result['balanced_accuracy']
                    refinement_results.append(result)
                    
                    # Update minimum k with BA=1.0 if we find a smaller one
                    if ba_1_0_achieved_at_k is None and np.isclose(result['balanced_accuracy'], 1.0, atol=1e-6):
                        ba_1_0_achieved_at_k = k
                        logger.info(f"    [{i+1}/{len(refinement_candidates)}] k={k:,} → BA={refinement_ba[i]:.6f} ⭐ BA=1.0 achieved!")
                    elif ba_1_0_achieved_at_k is not None and np.isclose(result['balanced_accuracy'], 1.0, atol=1e-6) and k < ba_1_0_achieved_at_k:
                        ba_1_0_achieved_at_k = k
                        logger.info(f"    [{i+1}/{len(refinement_candidates)}] k={k:,} → BA={refinement_ba[i]:.6f} ⭐ Found smaller k with BA=1.0!")
                    
                    if i % max(1, len(refinement_candidates) // 5) == 0 or i == len(refinement_candidates) - 1 or np.isclose(refinement_ba[i], 1.0, atol=1e-6):
                        logger.info(f"    [{i+1}/{len(refinement_candidates)}] k={k:,} → BA={refinement_ba[i]:.6f}")
                
                # Filter out skipped (NaN) refinement results
                valid_refinement_mask = ~np.isnan(refinement_ba)
                if not np.all(valid_refinement_mask):
                    refinement_candidates = refinement_candidates[valid_refinement_mask]
                    refinement_ba = refinement_ba[valid_refinement_mask]
                    refinement_results = [r for r, valid in zip(refinement_results, valid_refinement_mask) if valid]
                    logger.info(f"  Refinement: {len(refinement_candidates)} valid evaluations (skipped {np.sum(~valid_refinement_mask)} redundant candidates)")
                
                # Combine results
                candidate_k = np.concatenate([candidate_k, refinement_candidates])
                ba_results = np.concatenate([ba_results, refinement_ba])
                detailed_results.extend(refinement_results)
                
                # Re-sort by k for consistency
                sort_idx = np.argsort(candidate_k)
                candidate_k = candidate_k[sort_idx]
                ba_results = ba_results[sort_idx]
                detailed_results = [detailed_results[i] for i in sort_idx]
                
                n_candidates = len(candidate_k)
                logger.info(f"  Total evaluations: {n_candidates} (coarse + refinement)")

        # Find best k (minimal k achieving maximum BA)
        max_ba = ba_results.max()
        best_mask = np.isclose(ba_results, max_ba, atol=1e-6) | (ba_results == max_ba)
        best_indices = np.where(best_mask)[0]
        best_k_values = candidate_k[best_indices]
        best_k = int(best_k_values.min())
        best_result_idx = int(best_indices[best_k_values == best_k][0])
        best_result = detailed_results[best_result_idx]
        
        logger.info(f"  ✅ FeatureCuts complete: {len(candidate_k)} evaluations, max BA={max_ba:.6f} at k={best_k:,}")
        if np.isclose(max_ba, 0.5, atol=1e-4):
            logger.warning(
                "Optimization achieved BA≈0.5 (coin toss). Check that validation data has both classes in test set "
                "and that DMP alpha/beta parameters are valid; consider trying optimization_method='binary_search' or 'bayesian_optimization'."
            )
        top5_indices = np.argsort(-ba_results)[:5]
        if top5_indices.size > 0:
            logger.debug("  Top 5 k candidates: " + ", ".join(f"k={int(candidate_k[i]):,}(BA={ba_results[i]:.3f})" for i in top5_indices))
        return best_k, best_result

    def _optimize_dmps_binary_search(
        self,
        sorted_df: pd.DataFrame,
        target_ba: float,
        max_k: int,
        X_calib: np.ndarray,
        y_calib: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray,
        val_positions: np.ndarray,
        val_contexts: np.ndarray
    ) -> int:
        """
        Logarithmic binary search to find minimal k achieving target balanced accuracy.
        Uses geometric spacing to efficiently explore the k-space, starting with small k values.
        Assumes monotonic BA increase with k (validated by our weighting fixes).
        """
        if max_k <= 1:
            return max_k

        # First, do a logarithmic exploration to find a reasonable starting point
        # Try geometric spacing: 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, etc.
        logger.info(f"🔍 Logarithmic binary search: exploring k-space up to {max_k:,} DMPs")

        # Find the largest power of 2 that's reasonable to start with
        max_power = int(np.log2(min(max_k, 8192)))  # Cap at 8192 to avoid too many evaluations
        geometric_k = [2**i for i in range(max_power + 1) if 2**i <= max_k]

        # Add some intermediate points for better coverage
        if max_k > 100:
            geometric_k.extend([int(max_k * 0.1), int(max_k * 0.25), int(max_k * 0.5)])
        geometric_k = sorted(list(set(geometric_k)))  # Remove duplicates and sort

        logger.info(f"📊 Testing geometric sequence: {geometric_k[:10]}{'...' if len(geometric_k) > 10 else ''}")

        best_k = max_k
        min_achieved_ba = 0.0

        # Test geometric points to find where BA starts to stabilize
        for k in geometric_k:
            subset_df = sorted_df.iloc[:k]
            result = self._validate_classifier_subset(
                subset_df, X_calib, y_calib, X_test, y_test, val_positions, val_contexts
            )

            current_ba = result['balanced_accuracy']
            logger.info(f"  [geom] k={k:,} → BA={current_ba:.4f}")

            if current_ba >= target_ba:
                best_k = k
                break  # Found a k that achieves target - can refine from here
            elif current_ba > min_achieved_ba:
                min_achieved_ba = current_ba

        # If we didn't find a k that achieves target_ba, we need more DMPs
        # Do a focused binary search in the upper range
        if best_k == max_k:
            logger.info(f"⚠️  Target BA {target_ba:.3f} not achieved with geometric search, doing full binary search")
            left, right = geometric_k[-1] if geometric_k else 1, max_k
        else:
            # Found a k that works - search for minimal k in the lower range
            # Find the largest k in geometric_k that didn't achieve target
            failed_k = [k for k in geometric_k if k < best_k]
            left = failed_k[-1] if failed_k else 1
            right = best_k

        logger.info(f"🔍 Focused binary search: k ∈ [{left}, {right}], target BA ≥ {target_ba:.3f}")

        iterations = 0
        max_iterations = 8  # Limit iterations for focused search

        while left <= right and iterations < max_iterations:
            iterations += 1
            mid = (left + right) // 2

            # Test current k
            subset_df = sorted_df.iloc[:mid]
            result = self._validate_classifier_subset(
                subset_df, X_calib, y_calib, X_test, y_test, val_positions, val_contexts
            )

            current_ba = result['balanced_accuracy']
            logger.info(f"  [{iterations}] k={mid:,} → BA={current_ba:.4f}")

            if current_ba >= target_ba:
                # Achieved target - try smaller k
                best_k = mid
                right = mid - 1
            else:
                # Need more DMPs
                left = mid + 1

        # Check if we achieved the target with the final best_k
        if best_k == max_k:
            # Test the maximum k to see what BA we actually achieve
            subset_df = sorted_df.iloc[:max_k]
            final_result = self._validate_classifier_subset(
                subset_df, X_calib, y_calib, X_test, y_test, val_positions, val_contexts
            )
            actual_ba = final_result['balanced_accuracy']

            if actual_ba < target_ba:
                logger.warning(f"⚠️  Target BA {target_ba:.3f} not achievable (maximum BA = {actual_ba:.4f} with {max_k:,} DMPs)")
                logger.info("💡 Consider lowering target_balanced_accuracy in config for this dataset")

        logger.info(f"🔍 Binary search converged after {iterations + len(geometric_k)} total evaluations")
        return best_k

    def _optimize_dmps_bayesian(
        self,
        sorted_df: pd.DataFrame,
        max_k: int,
        X_calib: np.ndarray,
        y_calib: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray,
        val_positions: np.ndarray,
        val_contexts: np.ndarray,
        initial_k: Optional[int] = None
    ) -> int:
        """
        Optimize DMP count using Bayesian Optimization with Gaussian Process surrogate.

        This implements BO using sklearn's GP regressor and Expected Improvement acquisition.
        More efficient than DE for non-monotonic functions, typically requiring 20-50 evaluations.

        Args:
            sorted_df: Sorted DMPs by importance
            max_k: Maximum k to consider
            X_calib, y_calib, X_test, y_test: Validation data
            val_positions, val_contexts: Position/context arrays
            initial_k: Optional heuristic starting point

        Returns:
            Optimal k value
        """
        import warnings
        from scipy.stats import norm
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import RBF, ConstantKernel as C

        if max_k <= 0:
            logger.warning("Bayesian optimization received empty candidate set; returning k=0")
            return 0

        min_k = 1 if max_k > 0 else 0
        logger.info(f"  BO search range: k ∈ [{min_k:,}, {max_k:,}]")

        # Cache for performance evaluations
        evaluation_cache: Dict[int, float] = {}

        def objective_function(k: int) -> float:
            """Evaluate BA for given k (return negative BA for minimization)"""
            k = int(round(k))
            k = max(min_k, min(k, max_k))

            if k in evaluation_cache:
                return -evaluation_cache[k]

            test_subset = sorted_df.iloc[:k]
            result = self._validate_classifier_subset(
                test_subset, X_calib, y_calib, X_test, y_test, val_positions, val_contexts
            )
            ba = result['balanced_accuracy']
            evaluation_cache[k] = ba

            return -ba  # Minimize negative BA = maximize BA

        # Initial evaluations: 8-12 diverse points (limited by available range)
        n_initial = min(10, max_k - min_k + 1)

        # Generate initial points
        initial_points: List[int] = []
        if initial_k is not None:
            heuristic = int(np.clip(initial_k, min_k, max_k))
            initial_points.append(heuristic)
            for offset in [-25, -10, 10, 25]:
                candidate = heuristic + offset
                if min_k <= candidate <= max_k:
                    initial_points.append(candidate)

        if not initial_points:
            initial_points.append(min_k)
        if max_k != min_k and max_k not in initial_points:
            initial_points.append(max_k)

        # Fill with random points for diversity where range allows
        while len(initial_points) < n_initial and max_k > min_k:
            candidate = np.random.randint(min_k, max_k + 1)
            if candidate not in initial_points:
                initial_points.append(candidate)

        initial_points = sorted(list(set(initial_points)))[:n_initial]

        # Evaluate initial points
        X_observed = np.array([[k] for k in initial_points])
        y_observed = np.array([objective_function(k) for k in initial_points])

        logger.info(f"  Initial BO evaluations: {len(initial_points)} points, best BA: {-np.min(y_observed):.6f}")

        # Bayesian Optimization loop: 15-25 iterations
        n_iterations = min(20, max_k - min_k)

        # Suppress GP kernel convergence warnings (bounds hitting is normal for BO)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning,
                                  message=".*optimal value found.*close to the specified.*bound.*")

            for iteration in range(n_iterations):
                # Fit GP surrogate model
                kernel = C(1.0, (1e-6, 1e6)) * RBF(10, (1e-3, 1e6))
                gp = GaussianProcessRegressor(
                    kernel=kernel,
                    alpha=1e-6,
                    normalize_y=True,
                    n_restarts_optimizer=3
                )
                gp.fit(X_observed, y_observed)

                # Expected Improvement acquisition function
                def expected_improvement(X):
                    X = X.reshape(-1, 1)
                    mu, sigma = gp.predict(X, return_std=True)
                    best_y = np.min(y_observed)

                    with np.errstate(divide='ignore', invalid='ignore'):
                        Z = (best_y - mu) / sigma
                        ei = (best_y - mu) * norm.cdf(Z) + sigma * norm.pdf(Z)
                        ei[sigma == 0.0] = 0.0

                    return ei

                # Evaluate EI at candidate points and select next evaluation
                candidate_points = np.linspace(min_k, max_k, min(100, max_k - min_k + 1)).reshape(-1, 1)
                ei_values = expected_improvement(candidate_points)

                best_idx = np.argmax(ei_values)
                next_k = int(candidate_points[best_idx, 0])

                # Evaluate objective and update observations
                next_y = objective_function(next_k)
                X_observed = np.vstack([X_observed, [[next_k]]])
                y_observed = np.append(y_observed, next_y)

                # Log progress every 5 iterations or when improvement found
                current_best_k = X_observed[np.argmin(y_observed), 0]
                current_best_ba = -np.min(y_observed)
                if iteration % 5 == 0 or -next_y > current_best_ba - 0.001:
                    logger.info(f"    BO iter {iteration+1}: k={next_k:,} → BA={-next_y:.6f}, best: k={int(current_best_k):,} BA={current_best_ba:.6f}")

        # Return best result
        best_idx = np.argmin(y_observed)
        optimal_k = int(X_observed[best_idx, 0])
        optimal_ba = -y_observed[best_idx]

        logger.info(f"  ✅ BO complete: k={optimal_k:,}, BA={optimal_ba:.6f}")
        logger.info(f"  BO stats: {len(y_observed)} evaluations ({n_initial} initial + {n_iterations} BO)")

        return optimal_k

    
    def _save_validation_results(
        self,
        n_dmps_exported: Optional[int] = None,
        total_statistical_dmps: Optional[int] = None,
        total_biological_dmps: Optional[int] = None,
    ):
        """Save validation results to JSON file using Pydantic model."""
        from datetime import datetime

        from ..models import (
            MethylModelerValidationResults,
            ValidationResults,
            PerformanceMetrics,
            ConfusionMatrix,
            SampleCounts
        )

        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        results_path = output_dir / f"results-{self.chromosome}.json"

        # Get config dict (Pydantic v2 mode='json' handles Path conversion)
        try:
            config_dict = self.config.model_dump(mode='json')
        except (TypeError, ValueError):
            # Fallback for older Pydantic versions
            config_dict = self.config.model_dump()

        # Create validation results objects
        optimization_validation = None
        if hasattr(self, '_final_validation_results') and self._final_validation_results:
            result = self._final_validation_results
            optimization_validation = ValidationResults(
                type=self.config.validation_mode,
                performance=PerformanceMetrics(
                    balanced_accuracy=result['balanced_accuracy'],
                    sensitivity=result['metrics']['sensitivity'],
                    specificity=result['metrics']['specificity'],
                    precision=result['metrics']['precision'],
                    accuracy=result['metrics']['accuracy']
                ),
                confusion_matrix=ConfusionMatrix(**result['confusion_matrix']),
                sample_counts=SampleCounts(**result['counts'])
            )

        real_validation = None
        if hasattr(self, '_real_validation_results') and self._real_validation_results:
            result = self._real_validation_results
            real_validation = ValidationResults(
                type='real',
                performance=PerformanceMetrics(
                    balanced_accuracy=result['balanced_accuracy'],
                    sensitivity=result['metrics']['sensitivity'],
                    specificity=result['metrics']['specificity'],
                    precision=result['metrics']['precision'],
                    accuracy=result['metrics']['accuracy']
                ),
                confusion_matrix=ConfusionMatrix(**result['confusion_matrix']),
                sample_counts=SampleCounts(**result['counts'])
            )

        biological_filter = getattr(self, "_biological_filter_summary", None)

        # Create the main results object
        results = MethylModelerValidationResults(
            chromosome=self.chromosome,
            timestamp=datetime.now().isoformat(),
            config=config_dict,
            optimization_validation=optimization_validation,
            real_validation=real_validation,
            n_dmps_exported=n_dmps_exported,
            total_statistical_dmps=total_statistical_dmps,
            total_biological_dmps=total_biological_dmps,
            biological_filter=biological_filter,
        )

        # Save to JSON using Pydantic's model_dump_json for proper serialization
        with open(results_path, 'w') as f:
            f.write(results.model_dump_json(indent=2))

        logger.info(f"💾 Saved results to {results_path}")

    def _compute_sample_size_estimate(self, df: pd.DataFrame):
        """Compute n per group to achieve target_power (two-sample t-test, Cohen's d). Returns Series, NaN where not computable."""
        import warnings
        need = ['mean1', 'mean2']
        if not all(c in df.columns for c in need):
            return pd.Series(index=df.index, dtype=np.float64)
        if 'combined_variance' in df.columns:
            combined_var = df['combined_variance'].values.astype(np.float64)
        elif 'variance1' in df.columns and 'variance2' in df.columns:
            combined_var = df['variance1'].values.astype(np.float64) + df['variance2'].values.astype(np.float64)
        else:
            return pd.Series(index=df.index, dtype=np.float64)
        delta = np.abs(df['mean1'].values.astype(np.float64) - df['mean2'].values.astype(np.float64))
        eps = 1e-12
        pooled_std = np.sqrt(np.maximum(combined_var, eps))
        cohens_d = np.where(pooled_std > 0, delta / pooled_std, np.nan)
        # Clip to range where statsmodels solve_power typically converges (avoids ConvergenceWarning)
        cohens_d = np.clip(cohens_d, 0.02, 10.0)
        alpha = getattr(self.config, 'alpha', 0.05)
        power = getattr(self.config, 'target_power', 0.8)
        try:
            from statsmodels.stats.power import TTestIndPower
            from statsmodels.tools.sm_exceptions import ConvergenceWarning as StatsmodelsConvergenceWarning
            tt = TTestIndPower()
            n_est = np.full(len(df), np.nan, dtype=np.float64)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=StatsmodelsConvergenceWarning, module="statsmodels")
                for i in range(len(df)):
                    d = cohens_d[i]
                    if np.isfinite(d) and d >= 0.02:
                        try:
                            n_est[i] = tt.solve_power(effect_size=d, alpha=alpha, power=power, nobs1=None, ratio=1.0)
                        except Exception:
                            pass
            return pd.Series(n_est, index=df.index)
        except ImportError:
            logger.warning("statsmodels not available; skipping n_estimated_per_group. Install with: pip install statsmodels")
            return pd.Series(index=df.index, dtype=np.float64)
    
    def _export_unified_csv(self, bio_dmps_df: pd.DataFrame, suffix: str = "") -> Path:
        """
        Export unified CSV with all contexts combined.
        
        Args:
            bio_dmps_df: DataFrame with biological DMPs
            suffix: Optional suffix to add to filename (e.g., "-1-biological")
            
        Returns:
            Path to exported CSV file
        """
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        if suffix:
            csv_path = output_dir / f"dmps-{self.chromosome}{suffix}.csv"
        else:
            csv_path = output_dir / f"dmps-{self.chromosome}.csv"
        
        # Standard column order for biologists: identity, sample counts, means/variances, overlap, effect, stats, distribution
        # dist: 1=Beta, 2=Normal, 3=Beta-Binomial, 4=Beta-Mixture (see methyl_utils.methyl_centroid_pair.DIST_*)
        STANDARD_EXPORT_COLS = [
            'chromosome', 'context', 'position',
            'n1', 'n2', 'mean1', 'mean2', 'variance1', 'variance2',
            'overlap', 'delta_mean', 'delta_sign', 'effect_size',
            'p_value', 'q_value', 'dist', 'dist_name',
        ]
        DIST_NAMES = {1: 'Beta', 2: 'Normal', 3: 'Beta-Binomial', 4: 'Beta-Mixture', 5: 'ECDF'}
        # Optional / distribution-specific columns
        EXTRA_EXPORT_COLS = [
            'context_weight', 'alpha1', 'beta1', 'alpha2', 'beta2',
            'combined_variance', 'bmm_p_value', 'bmm_js', 'bmm_status',
            'n_estimated_per_group',
        ]
        export_cols = STANDARD_EXPORT_COLS + [c for c in EXTRA_EXPORT_COLS if c not in STANDARD_EXPORT_COLS]

        export_df = bio_dmps_df.copy()
        if 'dist' in export_df.columns:
            export_df['dist_name'] = export_df['dist'].map(DIST_NAMES).fillna('Unknown').astype(str)
        if 'delta_sign' not in export_df.columns and 'mean1' in export_df.columns and 'mean2' in export_df.columns:
            export_df['delta_sign'] = np.sign(export_df['mean1'] - export_df['mean2']).astype(np.int8)
        if getattr(self.config, 'export_sample_size_estimate', False):
            export_df['n_estimated_per_group'] = self._compute_sample_size_estimate(export_df)
        available_cols = [c for c in export_cols if c in export_df.columns]
        
        # Export to CSV
        export_df[available_cols].to_csv(csv_path, index=False)
        
        logger.info(f"📁 Exported {len(bio_dmps_df):,} DMPs to {csv_path}")
        logger.info(f"📊 Columns: {', '.join(available_cols)}")
        
        # Log per-context counts
        if 'context' in bio_dmps_df.columns:
            context_counts = bio_dmps_df.groupby('context').size()
            for ctx, count in context_counts.items():
                logger.info(f"  {ctx}: {count:,} DMPs")
        
        return csv_path
    
    def _save_unified_model(self, classifier, selected_dmps_df: pd.DataFrame):
        """
        Save unified BetaClassifier model with strongly-typed dmpDF.
        
        Args:
            classifier: Classifier instance (ignored, we create BetaClassifier from dmpDF)
            selected_dmps_df: DataFrame with selected DMPs (final DMPs used by classifier)
        """
        if selected_dmps_df is None or len(selected_dmps_df) == 0:
            logger.warning("No selected DMPs; skipping classifier model save")
            return
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        ctx_str = ",".join(sorted(self.config.contexts)) if self.config.contexts else "unknown"
        model_path = output_dir / f"classifier-{self.chromosome}-{ctx_str}.pkl"
        
        # Create strongly-typed dmpDF DataFrame
        # Use effect_size (single biological importance measure)
        if 'effect_size' in selected_dmps_df.columns:
            weights = selected_dmps_df['effect_size'].values.astype(np.float64)
            logger.debug("Using 'effect_size' for saved classifier weights")
        elif 'importance' in selected_dmps_df.columns:
            weights = selected_dmps_df['importance'].values.astype(np.float64)
            logger.debug("Using 'importance' for weights (fallback); will bound")
        elif 'context_weight' in selected_dmps_df.columns:
            weights = selected_dmps_df['context_weight'].values.astype(np.float64)
        else:
            weights = np.ones(len(selected_dmps_df), dtype=np.float64)
        weights = np.where(np.isfinite(weights) & (weights > 0), weights, 1e-6)
        if weights.size == 0:
            logger.warning("No selected DMPs (zero weights); skipping classifier model save")
            return
        w_max = float(np.max(weights))
        if w_max > 1e-6:
            weights = np.clip(weights / w_max, 1e-6, 1.0)
        
        dmpDF = pd.DataFrame({
            'pos': selected_dmps_df['position'].values.astype(np.int64),
            'alpha1': selected_dmps_df['alpha1'].values.astype(np.float64),
            'beta1': selected_dmps_df['beta1'].values.astype(np.float64),
            'alpha2': selected_dmps_df['alpha2'].values.astype(np.float64),
            'beta2': selected_dmps_df['beta2'].values.astype(np.float64),
            'weight': weights.astype(np.float64)
        })

        beta_classifier = BetaClassifier.from_dataframe(
            dmpDF,
            min_sample_coverage=self.config.min_sample_coverage,
            coverage_weighting=self.config.classifier_coverage_weighting
        )
        mixture_attached = self._attach_bmm_mixtures(beta_classifier, selected_dmps_df)
        if mixture_attached:
            logger.info("Attached BMM mixtures to classifier (hybrid Beta/BMM)")
        classifier_label = "BetaMixtureClassifier" if mixture_attached else "BetaClassifier"

        # Create model package
        import pickle
        model_package = {
            'classifier': beta_classifier,
            'dmpDF': dmpDF,  # Strongly typed DataFrame
            'context_weights_summary': selected_dmps_df.groupby('context')['context_weight'].first().to_dict() if 'context' in selected_dmps_df.columns else {},
            'chromosome': self.chromosome,
            'n_dmps': len(selected_dmps_df),
            'n_dmps_per_context': selected_dmps_df.groupby('context').size().to_dict() if 'context' in selected_dmps_df.columns else {},
            'metadata': {
                'version': '2.0.0',
                'classifier_type': classifier_label,
                'bmm_mixture_attached': mixture_attached,
                'context': ctx_str,
                'config': self.config.model_dump(),
                'trimmed_percentile_low': self.config.trimmed_percentile_low,
                'trimmed_percentile_high': self.config.trimmed_percentile_high,
            }
        }
        if mixture_attached and hasattr(self, "_bmm_centroid_files"):
            model_package["metadata"]["bmm_centroid_files"] = self._bmm_centroid_files

        # Include fitted Platt calibrator when enabled (MethylClassifier can use it for better-calibrated probabilities)
        if self.config.enable_platt_calibration and getattr(self, '_platt_calibrator_bytes', None) is not None:
            model_package["metadata"]["platt_calibrator"] = self._platt_calibrator_bytes
            if getattr(self, '_platt_calibrator_scaler_bytes', None) is not None:
                model_package["metadata"]["platt_calibrator_scaler"] = self._platt_calibrator_scaler_bytes
            logger.info("  - Platt calibrator included (enable_platt_calibration=True)")
        
        # Save to pickle
        with open(model_path, 'wb') as f:
            pickle.dump(model_package, f)
        
        logger.info(f"💾 Saved model to {model_path}")
        logger.info("📦 Model package includes:")
        logger.info(f"  - Classifier: {beta_classifier}")
        logger.info(f"  - dmpDF: {len(dmpDF)} DMPs (strongly typed)")
        logger.info(f"  - Context weights: {model_package['context_weights_summary']}")
        logger.info(f"  - Total DMPs: {model_package['n_dmps']}")
        logger.info(f"  - DMPs per context: {model_package['n_dmps_per_context']}")
        if 'effect_size' in selected_dmps_df.columns:
            logger.info(f"  - Effect size range: {selected_dmps_df['effect_size'].min():.4f} to {selected_dmps_df['effect_size'].max():.4f}")
    
    def _create_multi_context_result(
        self, 
        dmps_df: pd.DataFrame, 
        bio_dmps_df: pd.DataFrame
    ) -> MethylModelerResult:
        """
        Create result object for multi-context analysis.
        
        Args:
            dmps_df: DataFrame with all statistical DMPs
            bio_dmps_df: DataFrame with biological DMPs
            
        Returns:
            MethylModelerResult
        """
        # Compute per-context statistics
        comparison_stats = []
        for context in self.config.contexts:
            ctx_dmps = dmps_df[dmps_df['context'] == context]
            ctx_bio = bio_dmps_df[bio_dmps_df['context'] == context]
            
            if len(ctx_dmps) > 0:
                stats = ComparisonStats(
                    comparison_name=f"{self.chromosome}-{context}",
                    total_positions=len(ctx_dmps),
                    statistical_dmps=len(ctx_dmps),
                    biological_dmps=len(ctx_bio),
                    processing_time_seconds=0.0,  # TODO: track per-context timing
                    gpu_used=self.gpu_config.GPU_AVAILABLE
                )
                comparison_stats.append(stats)
        
        # Create result
        config_summary = self.config.model_dump()
        if hasattr(self, "_bmm_summary") and self._bmm_summary:
            config_summary = {**config_summary, "bmm_summary": self._bmm_summary}
        if hasattr(self, "_bmm_centroid_files"):
            config_summary = {**config_summary, "bmm_centroid_files": self._bmm_centroid_files}

        balanced_accuracy = None
        if hasattr(self, '_final_validation_results') and self._final_validation_results:
            balanced_accuracy = self._final_validation_results.get('balanced_accuracy')

        result = MethylModelerResult(
            biologically_significant_dmps_df=bio_dmps_df,
            total_statistical_dmps=len(dmps_df),
            total_biological_dmps=len(bio_dmps_df),
            biological_retention_rate=len(bio_dmps_df) / max(1, len(dmps_df)),
            comparison_stats=comparison_stats,
            timestamp=datetime.now().isoformat(),
            version="2.0.0-multi-context",
            config_summary=config_summary,
            balanced_accuracy=balanced_accuracy
        )
        
        return result


    def _structured_array_to_dmp_df(self, structured_array: np.ndarray) -> pd.DataFrame:
        """Convert structured array to DataFrame with basic fields (fast, no objects)."""
        df = pd.DataFrame(structured_array)
        # Ensure 'position' column exists and is properly typed
        if 'position' not in df.columns:
            logger.warning("Structured array missing 'position' field; adding dummy positions")
            df['position'] = np.arange(len(df), dtype=np.uint32)
        # Ensure dtypes (include n1, n2, variance1, variance2 from centroid comparison). No bhattacharyya (ECDF overlap only).
        dtype_map = {
            "position": "uint32",
            "chromosome": "str",
            "context": "str",
            "p_value": "float32",
            "q_value": "float32",
            "delta_mean": "float32",
            "weight": "float32",
            "alpha1": "float64",
            "beta1": "float64",
            "alpha2": "float64",
            "beta2": "float64",
            "mean1": "float32",
            "mean2": "float32",
            "selected": "bool",
            "n1": "uint32",
            "n2": "uint32",
            "variance1": "float32",
            "variance2": "float32",
        }
        for col, dtype in dtype_map.items():
            if col in df:
                df[col] = df[col].astype(dtype)
        # Drop legacy columns; overlap and effect_size come from ECDF/Welch in _compute_chunk_metrics_df
        for legacy in ("bhattacharyya", "bhattacharyya_coefficient"):
            if legacy in df.columns:
                df.drop(columns=[legacy], inplace=True)
        return df

    def _compute_missing_metrics_df(
        self,
        df: pd.DataFrame,
        ecdf_view1: Any,
        ecdf_view2: Any,
    ) -> pd.DataFrame:
        """Compute continuous-ECDF overlap and final effect_size for the reduced set.

        Both ECDFViews must be pre-sliced to exactly the positions in df (row i of the
        view corresponds to row i of df).  The caller is responsible for building the
        views with the correct per-centroid indices.
        """
        if ecdf_view1 is None or ecdf_view2 is None or len(df) == 0:
            return df
        # Drop legacy columns if present (from MethylCentroidPair output); we use ECDF overlap only
        legacy_cols = [c for c in ("bhattacharyya", "bhattacharyya_coefficient") if c in df.columns]
        if legacy_cols:
            df = df.drop(columns=legacy_cols)
        n_rows = len(df)
        # Estimate memory for the (n_positions × grid_size) PDF matrices used in ecdf_overlap_integral.
        grid_size = getattr(self.config, "ecdf_overlap_grid_size", 512)
        mem_per_row_mb = (2 * grid_size * 8) / (1024 ** 2)  # two float64 arrays of shape (n, grid)
        from methyl_utils import get_memory_usage
        available_gb = get_memory_usage().get('gpu_free_gb', 80.0)
        available_mb = available_gb * 1024
        chunk_size = max(50000, int(available_mb * 0.9 / max(mem_per_row_mb, 1e-6)))
        logger.debug(f"ECDF chunking: {available_mb:.0f} MB available, chunk_size={chunk_size:,} rows")

        if n_rows > chunk_size:
            logger.info(f"🔄 Chunking ECDF metrics for {n_rows:,} rows (batches of {chunk_size:,})")
            chunks = []
            for i in range(0, n_rows, chunk_size):
                end_i = min(i + chunk_size, n_rows)
                chunk_df = df.iloc[i:end_i].copy()
                chunk_result = self._compute_chunk_metrics_df(
                    chunk_df,
                    ecdf_view1=ecdf_view1,
                    ecdf_view2=ecdf_view2,
                    start_row=i,
                )
                chunks.append(chunk_result)
            result_df = pd.concat(chunks, ignore_index=True)
            logger.info(f"📊 Chunked ECDF metrics complete for {n_rows:,} rows")
            return result_df
        else:
            return self._compute_chunk_metrics_df(
                df,
                ecdf_view1=ecdf_view1,
                ecdf_view2=ecdf_view2,
                start_row=0,
            )

    def _compute_chunk_metrics_df(
        self,
        chunk_df: pd.DataFrame,
        ecdf_view1: Any,
        ecdf_view2: Any,
        start_row: int = 0,
    ) -> pd.DataFrame:
        """Compute overlap and effect_size for one reduced chunk.

        Both ECDFViews are pre-sliced to the DMP set, so the correct indices for this
        chunk are simply the sequential row positions within the sliced views:
        start_row, start_row+1, ..., start_row+len(chunk_df)-1.
        """
        import time
        start_time = time.time()

        dm = chunk_df['delta_mean'].values.astype(np.float64)
        var1 = chunk_df['variance1'].values.astype(np.float64)
        var2 = chunk_df['variance2'].values.astype(np.float64)

        from methyl_utils.statistical_tests import ecdf_effect_size
        position_indices = np.arange(start_row, start_row + len(chunk_df), dtype=np.intp)
        grid_size = getattr(self.config, "ecdf_overlap_grid_size", 512)
        lambda_var = getattr(self.config, "lambda_var", 2.0)
        results = ecdf_effect_size(
            delta_mean=dm,
            var1=var1,
            var2=var2,
            ecdf_view1=ecdf_view1,
            ecdf_view2=ecdf_view2,
            position_indices=position_indices,
            grid_size=grid_size,
            lambda_var=lambda_var,
        )
        chunk_df['overlap'] = results['overlap'].astype(np.float32)
        chunk_df['effect_size'] = results['effect_size'].astype(np.float32)
        chunk_df['effect_size_reliability'] = results['reliability'].astype(np.float32)

        chunk_df['combined_variance'] = (var1 + var2).astype(np.float32)

        total_time = time.time() - start_time
        logger.debug(f"Chunk metrics completed in {total_time:.2f}s for {len(chunk_df):,} rows")
        return chunk_df


    def _generate_filter_histograms(self, df: pd.DataFrame, chromosome: str, context: str) -> None:
        """Generate interactive HTML histograms for filter statistics (debugging only)."""
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        # Create output directory
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        # Generate histograms for key statistics
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=[
                "Q-value Distribution",
                "Delta Mean Distribution",
                "P-value Distribution",
                "Biological Filters Summary",
            ],
        )
        # Q-value histogram
        fig.add_trace(
            go.Histogram(x=df["q_value"], nbinsx=50, name="Q-values"), row=1, col=1
        )
        # Delta mean histogram
        fig.add_trace(
            go.Histogram(x=df["delta_mean"].abs(), nbinsx=50, name="|Delta Mean|"),
            row=1,
            col=2,
        )
        # P-value histogram
        fig.add_trace(
            go.Histogram(x=df["p_value"], nbinsx=50, name="P-values"), row=2, col=1
        )
        # Summary statistics text
        stats_text = f"""
        Total DMPs: {len(df):,}
        Statistically significant (q ≤ {self.config.alpha}): {len(df[df['q_value'] <= self.config.alpha]):,}
        DMPs with effect_size (BD) column: {len(df) if 'effect_size' in df.columns else 0:,}
        """
        fig.add_annotation(
            text=stats_text,
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=12),
            align="left",
        )
        fig.update_layout(
            height=800, title_text="DMP Filter Statistics Overview", showlegend=False
        )
        # Save HTML file with suffix
        html_file = output_dir / f"filter_statistics_overview-{chromosome}-{context}.html"
        fig.write_html(html_file)
        logger.info(f"📊 Interactive filter statistics saved: {html_file}")
        # Generate chromosome/context breakdown histograms (but single, so simple)
        chrom_fig = go.Figure()
        chrom_counts = (
            df.groupby(["chromosome", "context"]).size().reset_index(name="count")
        )
        for ctx in df["context"].unique():
            context_data = chrom_counts[chrom_counts["context"] == ctx]
            chrom_fig.add_trace(
                go.Bar(
                    x=context_data["chromosome"],
                    y=context_data["count"],
            name=f"{ctx} context",
                )
            )
        chrom_fig.update_layout(
            title="DMPs by Chromosome and Context",
            xaxis_title="Chromosome",
            yaxis_title="Number of DMPs",
            barmode="group",
        )
        chrom_html = output_dir / f"dmps_by_chromosome_context-{chromosome}-{context}.html"
        chrom_fig.write_html(chrom_html)
        logger.info(f"📊 Chromosome/context breakdown saved: {chrom_html}")

    def _export_selected_dmps_csv(self, biological_dmps_df: pd.DataFrame) -> None:
        """Export selected DMPs to CSV with standard columns (n1, n2, variances, overlap, effect_size, distribution)."""
        if biological_dmps_df.empty:
            logger.warning("No biological DMPs to export")
            return

        export_df = biological_dmps_df.copy()
        DIST_NAMES = {1: 'Beta', 2: 'Normal', 3: 'Beta-Binomial', 4: 'Beta-Mixture', 5: 'ECDF'}
        if 'dist' in export_df.columns:
            export_df['dist_name'] = export_df['dist'].map(DIST_NAMES).fillna('Unknown').astype(str)
        if 'delta_sign' not in export_df.columns and 'mean1' in export_df.columns and 'mean2' in export_df.columns:
            export_df['delta_sign'] = np.sign(export_df['mean1'] - export_df['mean2']).astype(np.int8)
        if 'effect_size' in export_df.columns:
            export_df['weight'] = export_df['effect_size']
        elif 'importance' in export_df.columns:
            export_df['weight'] = export_df['importance']

        standard_cols = [
            'chromosome', 'context', 'position', 'n1', 'n2', 'mean1', 'mean2', 'variance1', 'variance2',
            'overlap', 'delta_mean', 'delta_sign', 'effect_size', 'p_value', 'q_value', 'dist', 'dist_name', 'weight'
        ]
        if getattr(self.config, 'export_sample_size_estimate', False):
            export_df['n_estimated_per_group'] = self._compute_sample_size_estimate(export_df)
            standard_cols.append('n_estimated_per_group')
        export_cols = [c for c in standard_cols if c in export_df.columns]
        missing_cols = [c for c in standard_cols if c not in export_df.columns]
        if missing_cols:
            logger.warning(f"Missing columns in selected DMPs: {missing_cols}")
        
        # Create output directory and CSV path
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / f"dmps-{self.chrom}-{self.ctx}.csv"
        
        # Export selected columns
        export_df[export_cols].to_csv(csv_path, index=False)
        logger.info(f"✅ Exported {len(export_df):,} selected DMPs to {csv_path} with columns: {export_cols}")
        
        # Store CSV path for result summary
        self._exported_csv_path = csv_path

    def _save_single_chrom_context_results(self, df: pd.DataFrame, output_dir: Path, chromosome: str, context: str) -> None:
        """Save biological DMPs CSV with all columns."""
        if df.empty:
            logger.warning(f"No biological DMPs to save for {chromosome}-{context}")
            return

        csv_path = output_dir / f"biological_dmps-{chromosome}-{context}.csv"
        # Save all DataFrame columns for comprehensive analysis
        df.to_csv(csv_path, index=False)
        logger.info(f"Saved {len(df):,} biological DMPs to {csv_path} with {len(df.columns)} columns")

    def _create_final_result(self, dmp_df: pd.DataFrame,
                             biological_dmps_df: Optional[pd.DataFrame] = None) -> MethylModelerResult:
        """Create final result object from DataFrames."""
        # Log biological importance range
        if biological_dmps_df is not None and not biological_dmps_df.empty:
            if 'effect_size' in biological_dmps_df.columns:
                bio_scores = biological_dmps_df['effect_size'].dropna()
                if len(bio_scores) > 0:
                    max_score = bio_scores.max()
                    min_score = bio_scores.min()
                    logger.info(f"Biological importance range: min={min_score:.6f}, max={max_score:.6f}, count={len(bio_scores)}")

        # Build comparison stats from stored metadata
        chromosome = getattr(self, 'chrom', 'unknown')
        context = getattr(self, 'ctx', 'unknown')
        comp_name = f"{chromosome}-{context}" if chromosome != 'unknown' else "single_comparison"
        logger.debug(f"Processing {len(dmp_df)} DMPs for {comp_name}")

        stats = ComparisonStats(
            comparison_name=comp_name,
            total_positions=getattr(self, 'total_positions', len(dmp_df)),
            statistical_dmps=getattr(self, 'statistical_dmps_count', len(dmp_df)),
            biological_dmps=len(biological_dmps_df) if biological_dmps_df is not None else 0,
            processing_time_seconds=getattr(self, 'processing_time_seconds', 0.0),
            gpu_used=self.gpu_config.GPU_AVAILABLE
        )
        comparison_stats = [stats]
        total_statistical_dmps = getattr(self, 'statistical_dmps_count', len(dmp_df))

        config_summary = self.config.model_dump()
        if hasattr(self, "_bmm_summary") and self._bmm_summary:
            config_summary = {**config_summary, "bmm_summary": self._bmm_summary}

        result = MethylModelerResult(
            biologically_significant_dmps_df=biological_dmps_df,
            total_statistical_dmps=total_statistical_dmps,
            total_biological_dmps=len(biological_dmps_df) if biological_dmps_df is not None else 0,
            biological_retention_rate=len(biological_dmps_df) / max(1, total_statistical_dmps) if biological_dmps_df is not None else 0.0,
            comparison_stats=comparison_stats,
            timestamp=datetime.now().isoformat(),
            version="2.0.0",
            config_summary=config_summary
        )
        return result

    def _save_results(self, result: MethylModelerResult) -> None:
        """Save results for single mode."""
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        # Global CSV already saved in filtering for single
        # Always save summaries (JSON, TXT)
        chrom = getattr(self, 'chrom', 'unknown')
        ctx = getattr(self, 'ctx', 'unknown')
        suffix = f"-{chrom}-{ctx}"
        prefix = f"dmps{suffix}"
        save_json(result.model_dump(), output_dir / f"result{suffix}.json")
        # Create and save analysis summary
        import uuid
        from datetime import datetime
        # Extract key parameters (only relevant ones)
        key_params = {
            "alpha": self.config.alpha,
            "min_delta_mean": self.config.min_delta_mean,
            "max_overlap": self.config.max_overlap,
            "min_effect_size": self.config.min_effect_size,
            "target_balanced_accuracy": self.config.target_balanced_accuracy,
            "min_selected_dmps": self.config.min_selected_dmps,
            "eps": self.config.eps,
        }
        # Input files
        input_files = {
            "centroid1": self.config.centroid1_path,
            "centroid2": self.config.centroid2_path,
        }
        # CSV path for single - use exported CSV path if available, otherwise construct from prefix
        csv_path = getattr(self, '_exported_csv_path', None)
        if csv_path is None and result.biologically_significant_dmps_df is not None and not result.biologically_significant_dmps_df.empty:
            csv_path = output_dir / f"{prefix}.csv"
        # Get top DMP importance
        top_dmp_importance = None
        if result.biologically_significant_dmps_df is not None and not result.biologically_significant_dmps_df.empty:
            if 'effect_size' in result.biologically_significant_dmps_df.columns:
                top_dmp_importance = result.biologically_significant_dmps_df['effect_size'].max()
        # Model info
        model_path = getattr(result, 'classifier_model_path', None)
        training_accuracy = getattr(result, 'training_accuracy', None)
        summary = MethylModelerSummary(
            analysis_id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            version="2.0.0",
            input_files=input_files,
            total_statistical_dmps=result.total_statistical_dmps,
            total_biological_dmps=result.total_biological_dmps,
            biological_retention_rate=result.biological_retention_rate,
            output_directory=output_dir,
            csv_file=csv_path,
            summary_json_file=output_dir / f"summary{suffix}.json",
            classifier_model_file=model_path,
            key_parameters=key_params,
            classifier_accuracy=training_accuracy,
            top_dmp_significance=top_dmp_importance, 
        )
        save_json(
            summary.model_dump(),
            output_dir / f"analysis_summary{suffix}.json"
        )
        summary_lines = [
            "MethylDetector Analysis Summary",
            "=" * 40,
            f"Analysis Date: {result.timestamp}",
            f"Version: {result.version}",
            "",
            "Configuration:",
            f"  Alpha (q-value threshold): {self.config.alpha}",
            f"  Min delta_mean (|Δβ|): {self.config.min_delta_mean}",
            f"  Max overlap: {self.config.max_overlap}",
            f"  Min effect size (in [0,1]): {self.config.min_effect_size}",
            f"  Target Balanced Accuracy: {self.config.target_balanced_accuracy}",
            "",
            "Biological filter: min_delta_mean (|Δβ|≥), max_overlap (overlap≤), min_effect_size (effect size in [0,1], ≥).",
            "",
            "Results:",
            f"  Statistical DMPs (q≤{self.config.alpha}): {result.total_statistical_dmps:,}",
            f"  Biological DMPs (selected): {result.total_biological_dmps:,}",
            f"  Retention Rate: {result.biological_retention_rate:.1%}"
        ]
        if model_path:
            summary_lines.append(f"Classifier Model: {model_path}")
            if training_accuracy is not None:
                summary_lines.append(f"Model Accuracy (centroids): {training_accuracy * 100:.1f}%")
        save_summary_txt(summary_lines, output_dir / f"summary{suffix}.txt")


def _setup_imports_for_direct_execution():
    """Set up imports when running this file directly."""
    import sys
    from pathlib import Path

    # When run directly, set up the package structure
    script_dir = Path(__file__).parent  # methyl_modeler/core/
    package_root = script_dir.parent  # methyl_modeler/
    # Add package root to sys.path for imports
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    # Also add methylutils from monorepo if available (for development)
    # In monorepo: packages/methyldetector/../methylutils/methyl_utils
    methyl_utils_path = package_root.parent.parent / "methylutils" / "methyl_utils"
    if methyl_utils_path.exists() and str(methyl_utils_path) not in sys.path:
        sys.path.insert(0, str(methyl_utils_path))
    # Now import the relative imports and update globals
    global MethylModelerConfig, ComparisonStats, MethylModelerResult, MethylModelerSummary
    global GPUConfig, save_csv, save_json, save_summary_txt
    global CentroidPairHandler, create_centroid_from_arrays, get_chromosome_context_from_filename
    try:
        from models.config import MethylModelerConfig as MDC  # type: ignore[import-not-found]
        from models.results import (  # type: ignore[import-not-found]
            ComparisonStats as CS,
            MethylModelerResult as MDR,
            MethylModelerSummary as MDS,
        )
        from utils.core import (  # type: ignore[import-not-found]
            GPUConfig as GC,
            save_csv as sc,
            save_json as sj,
            save_summary_txt as sst,
        )
        from utils.sample_handler import (  # type: ignore[import-not-found]
            CentroidPairHandler as CPH,
            create_centroid_from_arrays as cca,
        )
        from utils.file_utils import get_chromosome_context_from_filename as gccf  # type: ignore[import-not-found]

        # Update the global variables
        MethylModelerConfig = MDC
        ComparisonStats = CS
        MethylModelerResult = MDR
        MethylModelerSummary = MDS
        GPUConfig = GC
        save_csv = sc
        save_json = sj
        save_summary_txt = sst
        CentroidPairHandler = CPH
        create_centroid_from_arrays = cca
        get_chromosome_context_from_filename = gccf
    except ImportError as e:
        raise RuntimeError(
            f"Failed to import required modules for direct execution: {e}"
        )


if __name__ == "__main__":
    """Allow direct execution of MethylModeler for development/testing."""
    _setup_imports_for_direct_execution()
    # Delegate to CLI main function
    try:
        from methyl_modeler.cli.main import main  # type: ignore[import-not-found]

        main()
    except ImportError as e:
        import sys

        print(f"Error: {e}")
        print("Try running: python run_methyl_modeler.py")
        print("Or: python -m methyl_modeler.cli.main")
        sys.exit(1)
