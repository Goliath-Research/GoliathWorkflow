"""Core MethylDetector pipeline for DMP detection, filtering, and selection."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

# Import statistical functions from MethylUtils (required)
from methyl_utils import (
    auto_compute_distance,
    compute_beta_llr_moments,
    compute_bhattacharyya_distance,
    compute_distribution_overlap,
    likelihood_ratio_test_beta,
    BayesianClassifierTrainer,
    ProbabilisticBetaClassifier
)
from methyl_utils.logging_utils import setup_module_logging
from scipy.optimize import root_scalar
from scipy.special import gammaln
from scipy.stats import chi2, norm

# Import sample handler for proper SRP compliance
from methyl_utils import MethylSample

# Import MethylCentroidPair from MethylUtils for mathematical operations
from methyl_utils import MethylCentroidPair

# Import Beta-Binomial classifier from MethylUtils
from methyl_utils import BetaBinomialClassifier

# Import MethylTrainer conditionally (only when needed)
# This allows the module to be imported even if methyl_trainer is not available
try:
    from methyl_trainer import MethylTrainer, TrainingConfig
    METHYL_TRAINER_AVAILABLE = True
except ImportError:
    MethylTrainer = None
    TrainingConfig = None
    METHYL_TRAINER_AVAILABLE = False

# Handle relative imports - try module import first, fall back to direct execution setup
try:
    from ..models.config import MethylDetectorConfig
    from ..models.results import (
        ComparisonStats,
        MethylDetectorResult,
        MethylDetectorSummary,
    )
    from ..utils.core import GPUConfig, save_csv, save_json, save_summary_txt
    from ..utils.file_utils import get_chromosome_context_from_filename
except ImportError:
    # For direct execution, these will be set up in __main__
    MethylDetectorConfig = None
    ComparisonStats = None
    MethylDetectorResult = None
    GPUConfig = None
    save_csv = None
    save_json = None
    save_summary_txt = None
    CentroidPairHandler = None
    create_centroid_from_arrays = None
    get_chromosome_context_from_filename = None
import psutil  # For mem tracking (pip install psutil if needed)

logger = setup_module_logging(__name__)


# DMPFilterResult and DMPData dataclasses removed - using DataFrame directly throughout


def bhattacharyya_coefficient(bd: np.ndarray) -> np.ndarray:
    """
    Convert Bhattacharyya Distance (BD) to Bhattacharyya Coefficient (BC).
    
    Args:
        bd: Bhattacharyya Distance values (0 to ∞, typically capped at 20)
        
    Returns:
        Bhattacharyya Coefficient values (0 to 1)
        - 0 = no overlap (perfect separation)
        - 1 = complete overlap (identical distributions)
    
    Mathematical relationship: BC = exp(-BD)
    """
    return np.exp(-bd)


class MethylDetector:
    """Main class for MethylDetector DMP detection and filtering."""

    def __init__(self, config: MethylDetectorConfig):
        """Initialize with configuration."""
        self.config = config
        np.random.seed(config.random_state)
        self.gpu_config = GPUConfig()  # From MethylUtils for memory management
        self.df = None  # Current working dataframe
        self._exported_csv_path = None  # Path to exported CSV file
        logger.debug("Initialized MethylDetector")
    
    def run(self) -> MethylDetectorResult:
        """Run the complete DMP detection and filtering pipeline."""
        logger.debug("Starting MethylDetector analysis pipeline...")
        
        # Single unified implementation for all cases
        return self._run_multi_context()
    
    def _run_multi_context(self) -> MethylDetectorResult:
        """Run multi-context analysis (new unified approach)."""
        logger.info(f"🧬 Starting multi-context analysis for chromosome {self.config.chromosome}")
        logger.info(f"📍 Contexts: {', '.join(self.config.contexts)}")
        
        all_dmps = []  # List to collect DataFrames from each context
        
        # Loop over all contexts
        for context in self.config.contexts:
            logger.info(f"🔬 Processing context: {context}")
            
            # Build paths to centroid files
            c1_path = Path(self.config.centroid1_dir) / f"{self.config.chromosome}-{context}.h5"
            c2_path = Path(self.config.centroid2_dir) / f"{self.config.chromosome}-{context}.h5"
            
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
        
        # Filter biological DMPs (apply biological filters)
        logger.info("🔬 Filtering biologically significant DMPs...")
        bio_dmps_df = self._filter_biological_dmps(dmps_df)
        logger.info(f"✅ Biological DMPs: {len(bio_dmps_df):,} (retention: {len(bio_dmps_df)/len(dmps_df)*100:.1f}%)")
        
        # Export Stage 1: Biological DMPs
        if self.config.output_dir:
            logger.info("💾 Exporting Stage 1: Biological DMPs...")
            self._export_unified_csv(bio_dmps_df, suffix="-1-biological")
        
        # Binary search for optimal DMP selection (if enabled)
        selected_dmps_df = bio_dmps_df
        binary_search_dmps_df = None
        if not self.config.export_all_biological_dmps:
            logger.info("🎯 Running binary search to optimize DMP selection...")
            selected_dmps_df = self._select_dmps_binary_search_multicontext(bio_dmps_df)
            logger.info(f"✅ Selected {len(selected_dmps_df):,} DMPs out of {len(bio_dmps_df):,} biological DMPs")
            
            # Store binary search result before potential DE optimization
            binary_search_dmps_df = selected_dmps_df.copy()
            
            # Export Stage 2: Binary Search DMPs (before DE optimization)
            if self.config.output_dir and not self.config.optimize_for_validation_accuracy:
                # Only export now if DE is not enabled (otherwise export after DE)
                logger.info("💾 Exporting Stage 2: Binary Search DMPs...")
                self._export_unified_csv(selected_dmps_df, suffix="-2-binary-search")
        else:
            logger.info("📋 Using all biological DMPs (export_all_biological_dmps=True)")
        
        # Train Beta-Binomial classifier
        logger.info("🤖 Training Beta-Binomial classifier...")
        classifier = BetaBinomialClassifier.from_dataframe(selected_dmps_df, self.config.chromosome)
        logger.info(f"✅ Classifier created: {classifier}")
        
        # Export unified CSVs
        if self.config.output_dir:
            # Export Stage 2: Binary Search DMPs (if DE was enabled, export now)
            if binary_search_dmps_df is not None and self.config.optimize_for_validation_accuracy:
                logger.info("💾 Exporting Stage 2: Binary Search DMPs...")
                self._export_unified_csv(binary_search_dmps_df, suffix="-2-binary-search")
            
            # Export Stage 3: Final DMPs (after DE optimization if enabled)
            if self.config.optimize_for_validation_accuracy and binary_search_dmps_df is not None:
                logger.info("💾 Exporting Stage 3: Differential Evolution Optimized DMPs...")
                self._export_unified_csv(selected_dmps_df, suffix="-3-differential-evolution")
            else:
                # Export final CSV with default name
                logger.info("💾 Exporting final DMPs...")
                self._export_unified_csv(selected_dmps_df)
            
            # Save model
            logger.info("💾 Saving classifier model...")
            self._save_unified_model(classifier, selected_dmps_df)
            
            # Save validation results if binary search was performed
            if hasattr(self, '_final_validation_results') and self._final_validation_results:
                self._save_validation_results()
        
        # Create result (use selected DMPs for result stats)
        result = self._create_multi_context_result(dmps_df, selected_dmps_df)
        logger.info(f"✅ Multi-context analysis complete for chromosome {self.config.chromosome}!")
        
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
        
        # Create centroid pair for comparison
        centroid_pair = MethylCentroidPair(min_coverage=effective_min_coverage)
        
        # Compare centroids
        import time
        start_time = time.time()
        comparison_results = centroid_pair.compare_centroids(centroid1, centroid2)
        processing_time = time.time() - start_time
        
        logger.info(f"Context {context}: Compared {len(comparison_results):,} positions in {processing_time:.2f}s")
        
        # Apply statistical filtering
        total_positions = len(comparison_results)
        filtered_results = comparison_results[comparison_results['q_value'] <= self.config.alpha].copy()
        statistical_dmps_count = len(filtered_results)
        
        logger.info(f"Context {context}: {statistical_dmps_count:,} significant DMPs (q≤{self.config.alpha}) "
                   f"out of {total_positions:,} ({(statistical_dmps_count/total_positions)*100:.1f}% pass rate)")
        
        # Compute missing metrics
        dmp_df = self._compute_missing_metrics_df(filtered_results)
        
        # Add chromosome and context columns
        dmp_df['chromosome'] = self.config.chromosome
        dmp_df['context'] = context
        
        return dmp_df
    
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
        weight_map = {}
        
        # Use effect_size if available, otherwise delta_mean
        if 'effect_size' in dmps_df.columns:
            score_col = 'effect_size'
        elif 'delta_mean' in dmps_df.columns:
            score_col = 'delta_mean'
            dmps_df['effect_size'] = np.abs(dmps_df['delta_mean'])  # Fallback
            score_col = 'effect_size'
        else:
            raise ValueError("DataFrame must have 'effect_size' or 'delta_mean' column")
        
        # Compute trimmed mean per context
        for context, group in dmps_df.groupby('context'):
            S = group[score_col].values
            
            # Trim bottom and top percentiles
            qlo = self.config.trimmed_percentile
            qhi = 1.0 - self.config.trimmed_percentile
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
        logger.info("Note: Weights based on average effect size (|delta_mean|) after")
        logger.info("      trimming top/bottom 10%. Higher weight = stronger methylation")
        logger.info("      differences on average, NOT necessarily more biological importance.")
        logger.info("="*60)
        logger.info("")
        
        # Map weights to DataFrame
        dmps_df['context_weight'] = dmps_df['context'].map(weight_map)
        
        return dmps_df
    
    def _filter_biological_dmps(self, dmps_df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter DMPs by biological significance criteria.
        
        Applies filters based on config settings:
        - min_delta_mean: minimum absolute methylation difference
        - max_bc: maximum Bhattacharyya coefficient (overlap)
        - min_effect_size: minimum effect size threshold
        
        Args:
            dmps_df: DataFrame with all DMPs
            
        Returns:
            DataFrame with only biologically significant DMPs
        """
        bio_df = dmps_df.copy()
        initial_count = len(bio_df)
        
        # Filter by delta_mean if configured
        if 'delta_mean' in self.config.biological_filters and self.config.min_delta_mean > 0:
            bio_df = bio_df[np.abs(bio_df['delta_mean']) >= self.config.min_delta_mean]
            logger.info(f"After delta_mean filter (≥{self.config.min_delta_mean}): "
                       f"{len(bio_df):,} DMPs ({len(bio_df)/initial_count*100:.1f}%)")
        
        # Filter by Bhattacharyya coefficient if configured
        if 'bhattacharyya' in self.config.biological_filters and self.config.max_bc is not None:
            if 'bhattacharyya_coefficient' in bio_df.columns:
                bio_df = bio_df[bio_df['bhattacharyya_coefficient'] <= self.config.max_bc]
                logger.info(f"After BC filter (≤{self.config.max_bc}): "
                           f"{len(bio_df):,} DMPs ({len(bio_df)/initial_count*100:.1f}%)")
            elif 'overlap' in bio_df.columns:
                bio_df = bio_df[bio_df['overlap'] <= self.config.max_bc]
                logger.info(f"After overlap filter (≤{self.config.max_bc}): "
                           f"{len(bio_df):,} DMPs ({len(bio_df)/initial_count*100:.1f}%)")
        
        # Filter by effect size if configured
        if self.config.min_effect_size is not None and 'effect_size' in bio_df.columns:
            bio_df = bio_df[bio_df['effect_size'] >= self.config.min_effect_size]
            logger.info(f"After effect_size filter (≥{self.config.min_effect_size}): "
                       f"{len(bio_df):,} DMPs ({len(bio_df)/initial_count*100:.1f}%)")
        
        return bio_df
    
    def _compute_biological_importance(self, dmps_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute biological importance score for multi-context DMPs.
        
        Importance = weighted combination of:
        - |delta_mean|: effect size (normalized)
        - (1 - overlap): distribution separation (normalized)
        - context_weight: context importance
        
        Args:
            dmps_df: DataFrame with DMPs
            
        Returns:
            DataFrame with added 'importance' column, sorted by importance (descending)
        """
        df = dmps_df.copy()
        
        # Ensure required columns exist
        if 'effect_size' not in df.columns and 'delta_mean' in df.columns:
            df['effect_size'] = np.abs(df['delta_mean'])
        
        # Normalize delta_mean to [0, 1]
        delta_max = np.abs(df['delta_mean']).max()
        if delta_max > 0:
            delta_norm = np.abs(df['delta_mean']) / delta_max
        else:
            delta_norm = np.zeros(len(df))
        
        # Normalize (1 - overlap) to [0, 1] - higher is better
        if 'overlap' in df.columns:
            overlap_max = (1 - df['overlap']).max()
            if overlap_max > 0:
                overlap_norm = (1 - df['overlap']) / overlap_max
            else:
                overlap_norm = np.zeros(len(df))
        else:
            overlap_norm = np.ones(len(df))  # Default if not available
        
        # Use context_weight as third component (already normalized)
        if 'context_weight' in df.columns:
            context_norm = df['context_weight']
        else:
            context_norm = np.ones(len(df))
        
        # Combined importance (equal weighting of three components)
        df['importance'] = (delta_norm + overlap_norm + context_norm) / 3.0
        
        # Sort by importance (descending)
        df = df.sort_values('importance', ascending=False).reset_index(drop=True)
        
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
        from pathlib import Path
        
        # If config explicitly provides a list, use it
        if isinstance(config_samples, list):
            logger.debug(f"Using {len(config_samples)} validation samples from config for {centroid_name}")
            return config_samples
        
        # If config says "use_metadata", read from centroid
        if config_samples == "use_metadata":
            try:
                # Load first context to get metadata
                if centroid_dir:
                    first_ctx = self.config.contexts[0] if hasattr(self.config, 'contexts') else 'CG'
                    centroid_path = Path(centroid_dir) / f"{self.config.chromosome}-{first_ctx}.h5"
                    
                    if centroid_path.exists():
                        centroid = MethylSample.load_from_h5(str(centroid_path))
                        if centroid.metadata and 'sample_paths' in centroid.metadata:
                            samples = centroid.metadata['sample_paths']
                            logger.info(f"✅ Loaded {len(samples)} validation samples from {centroid_name} metadata")
                            return samples
                        else:
                            logger.warning(f"No sample_paths in {centroid_name} metadata")
                    else:
                        logger.warning(f"Centroid file not found: {centroid_path}")
            except Exception as e:
                logger.warning(f"Failed to read validation samples from {centroid_name} metadata: {e}")
        
        return []
    
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
            
            # Generate class 1 (healthy) samples
            X_class1 = np.zeros((n_samples_per_class, n_positions))
            for i in range(n_positions):
                # Sample from Beta(alpha1, beta1)
                X_class1[:, i] = beta_dist.rvs(alpha1[i], beta1[i], size=n_samples_per_class, random_state=self.config.random_state + i)
            
            # Generate class 2 (cancer) samples
            X_class2 = np.zeros((n_samples_per_class, n_positions))
            for i in range(n_positions):
                # Sample from Beta(alpha2, beta2)
                X_class2[:, i] = beta_dist.rvs(alpha2[i], beta2[i], size=n_samples_per_class, random_state=self.config.random_state + n_positions + i)
            
            # Combine classes
            X_all = np.vstack([X_class1, X_class2])
            y_all = np.concatenate([np.zeros(n_samples_per_class, dtype=int), np.ones(n_samples_per_class, dtype=int)])
            
            logger.info(f"✅ Generated {len(X_all)} synthetic samples")
            
            # Split based on config
            if self.config.validation_split_ratio > 0:
                # Split for evaluation during optimization
                n_total = len(X_all)
                test_ratio = self.config.validation_split_ratio
                n_test = int(n_total * test_ratio)
                
                np.random.seed(self.config.random_state)
                indices = np.arange(n_total)
                np.random.shuffle(indices)
                
                test_indices = indices[:n_test]
                calib_indices = indices[n_test:]
                
                X_calib, y_calib = X_all[calib_indices], y_all[calib_indices]
                X_test, y_test = X_all[test_indices], y_all[test_indices]
                
                logger.info(f"   Split: {len(calib_indices)} calibration, {len(test_indices)} test (split_ratio={test_ratio})")
            else:
                # No split: use all for calibration
                X_calib, y_calib = X_all, y_all
                X_test, y_test = X_all, y_all
                logger.info(f"   Using all {len(X_all)} samples for calibration (no split)")
            
            return X_calib, y_calib, X_test, y_test, positions, contexts
            
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
        Load validation samples for multi-context binary search.
        
        Returns:
            Tuple of (X, y, positions, contexts) or None if loading fails
            - X: methylation matrix (n_samples x n_positions)
            - y: labels (0 for class1, 1 for class2)
            - positions: genomic positions
            - contexts: methylation contexts
        """
        try:
            from pathlib import Path
            
            # Get validation sample paths from config or centroid metadata
            class1_paths = self._get_validation_samples(
                self.config.centroid1_validation_samples,
                self.config.centroid1_dir,
                "centroid1"
            )
            class2_paths = self._get_validation_samples(
                self.config.centroid2_validation_samples,
                self.config.centroid2_dir,
                "centroid2"
            )
            
            if not class1_paths and not class2_paths:
                logger.warning("No validation samples specified")
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
        Validate a DMP subset using BetaBinomialClassifier with proper train/test split.
        
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
                logger.warning(f"No matching positions found in validation data")
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
            
            temp_classifier = BetaBinomialClassifier.from_dataframe(
                dmps_for_classifier,
                self.config.chromosome
            )
            
            # PHASE 1: Fit Platt calibration using calibration set
            depth = 100
            calib_llrs = []
            
            for i in range(len(X_calib_subset)):
                methylation_fractions = X_calib_subset[i]
                valid_mask = ~np.isnan(methylation_fractions)
                
                if not np.any(valid_mask):
                    calib_llrs.append(0.0)
                    continue
                
                meth_valid = methylation_fractions[valid_mask]
                m_counts = np.round(meth_valid * depth).astype(int)
                u_counts = depth - m_counts
                
                result = temp_classifier.predict_sample(
                    sample_positions=matched_positions[valid_mask],
                    sample_contexts=matched_contexts[valid_mask],
                    sample_m=m_counts,
                    sample_u=u_counts
                )
                calib_llrs.append(result['chromosome_llr'])
            
            calib_llrs = np.array(calib_llrs)
            
            # Fit Platt calibration on calibration set
            temp_classifier.fit_platt_calibration(calib_llrs, y_calib)
            
            # PHASE 2: Evaluate on held-out test set
            y_pred = np.zeros(len(X_test_subset), dtype=int)
            probabilities = []
            
            for i in range(len(X_test_subset)):
                methylation_fractions = X_test_subset[i]
                valid_mask = ~np.isnan(methylation_fractions)
                
                if not np.any(valid_mask):
                    y_pred[i] = 0
                    probabilities.append(0.5)
                    continue
                
                meth_valid = methylation_fractions[valid_mask]
                m_counts = np.round(meth_valid * depth).astype(int)
                u_counts = depth - m_counts
                
                result = temp_classifier.predict_sample(
                    sample_positions=matched_positions[valid_mask],
                    sample_contexts=matched_contexts[valid_mask],
                    sample_m=m_counts,
                    sample_u=u_counts
                )
                
                prob = result['probability']  # Now calibrated!
                probabilities.append(prob)
                
                y_pred[i] = 1 if prob >= 0.5 else 0
            
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
            
            # Return both balanced accuracy and confusion matrix details
            return {
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
    
    def _select_dmps_binary_search_multicontext(self, bio_dmps_df: pd.DataFrame) -> pd.DataFrame:
        """
        Select optimal subset of DMPs using binary search for multi-context mode.
        
        Args:
            bio_dmps_df: DataFrame of biologically filtered DMPs
            
        Returns:
            DataFrame with optimal subset of DMPs
        """
        n_dmps = len(bio_dmps_df)
        target_ba = self.config.target_balanced_accuracy
        
        logger.info(f"🔍 Binary search DMP selection: {n_dmps:,} candidates, target BA={target_ba:.3f}")
        
        if n_dmps == 0:
            return bio_dmps_df
        
        # Compute importance scores and sort
        logger.debug("Computing biological importance scores...")
        sorted_df = self._compute_biological_importance(bio_dmps_df)
        
        # Load validation samples if in real mode
        validation_data = None
        if self.config.validation_mode == "real":
            logger.info("📊 Loading validation samples for binary search...")
            validation_data = self._load_validation_samples_multicontext(sorted_df)
            if validation_data is not None:
                X_val, y_val, val_positions, val_contexts = validation_data
                logger.info(f"✅ Loaded {len(X_val)} validation samples with {len(val_positions)} positions")
                
                # Split validation set based on config
                if self.config.validation_split_ratio > 0:
                    # Split for proper evaluation during optimization
                    n_samples = len(X_val)
                    test_ratio = self.config.validation_split_ratio
                    n_test = int(n_samples * test_ratio)
                    n_calib = n_samples - n_test
                    
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
                    # User has separate independent test set
                    X_calib, y_calib = X_val, y_val
                    X_test, y_test = X_val, y_val
                    logger.info(f"   Using all {len(X_val)} samples for calibration (no split, validation_split_ratio=0)")
                
                # Store both sets for binary search
                validation_data = (X_calib, y_calib, X_test, y_test, val_positions, val_contexts)
            else:
                logger.warning("Failed to load validation samples, falling back to all DMPs")
                return sorted_df
        else:
            # Synthetic validation mode
            logger.info("📊 Generating synthetic validation samples from Beta distributions...")
            validation_data = self._generate_synthetic_validation_samples(sorted_df)
            if validation_data is None:
                logger.warning("Failed to generate synthetic samples, using all DMPs")
                return sorted_df
        
        # Unpack validation data (now includes calibration split)
        X_calib, y_calib, X_test, y_test, val_positions, val_contexts = validation_data
        
        # Binary search for optimal k (only for real validation - synthetic gives BA=1.0 everywhere)
        if self.config.validation_mode == "real":
            low, high = max(10, self.config.min_selected_dmps or 10), n_dmps
            best_k = n_dmps
            best_ba = 0.0
            
            logger.info(f"Binary search range: {low}-{high}")
            
            iteration = 0
            best_result = None
            no_improvement_count = 0
            
            while low <= high:
                mid = (low + high) // 2
                test_subset = sorted_df.iloc[:mid]
                
                iteration += 1
                logger.info(f"  Iteration {iteration}: Testing k={mid:,} DMPs...")
                
                import time
                start_time = time.time()
                result = self._validate_classifier_subset(
                    test_subset,
                    X_calib, y_calib,
                    X_test, y_test,
                    val_positions, val_contexts
                )
                elapsed = time.time() - start_time
                
                ba = result['balanced_accuracy']
                
                # Track best result
                if ba > best_ba:
                    best_ba = ba
                    best_k = mid
                    best_result = result
                    no_improvement_count = 0
                    logger.info(f"  → k={mid:,}: BA={ba:.6f} ✓ New best!")
                else:
                    no_improvement_count += 1
                    logger.info(f"  → k={mid:,}: BA={ba:.6f}")
                
                if ba >= target_ba:
                    # Target achieved, try fewer DMPs
                    high = mid - 1
                else:
                    # Need more DMPs, but check if we're making progress
                    if no_improvement_count >= 3:
                        logger.info(f"  Stopping early: no improvement for {no_improvement_count} iterations")
                        break
                    low = mid + 1
            
            # Apply min_dmps_for_export
            original_k = best_k
            best_k = max(best_k, self.config.min_dmps_for_export)
            best_k = min(best_k, n_dmps)
            
            if best_k != original_k:
                logger.info(f"Adjusting k from {original_k:,} to {best_k:,} (min_dmps_for_export={self.config.min_dmps_for_export:,})")
            
            # Final subset and validation
            final_subset = sorted_df.iloc[:best_k]
            final_result = self._validate_classifier_subset(
                final_subset,
                X_calib, y_calib,
                X_test, y_test,
                val_positions, val_contexts
            )
        else:
            # Synthetic mode: skip binary search (BA=1.0 everywhere), go straight to DE
            logger.info("⏭️  Skipping binary search for synthetic validation (BA=1.0 trivially achievable)")
            logger.info("   Proceeding directly to Differential Evolution optimization...")
            best_k = n_dmps // 2  # Start DE from middle
            best_ba = 1.0
            final_result = None
        
        # Log results only if binary search ran (real mode)
        if final_result is not None:
            final_ba = final_result['balanced_accuracy']
            cm = final_result['confusion_matrix']
            metrics = final_result['metrics']
            counts = final_result['counts']
            
            # Log final results with confusion matrix
            logger.info("")
            logger.info("="*60)
            logger.info(f"✅ Binary Search Complete - Selected {best_k:,} DMPs")
            logger.info("="*60)
            logger.info(f"Balanced Accuracy: {final_ba:.4f}" + (" ✓ Target Achieved" if final_ba >= target_ba else f" (Target: {target_ba:.3f})"))
            logger.info("")
            logger.info("📊 Confusion Matrix:")
            logger.info(f"                     Predicted")
            logger.info(f"                Negative  Positive")
            logger.info(f"  Actual Negative:  {cm['tn']:3d}      {cm['fp']:3d}      (Class 1: {counts['n_negative']} samples)")
            logger.info(f"  Actual Positive:  {cm['fn']:3d}      {cm['tp']:3d}      (Class 2: {counts['n_positive']} samples)")
            logger.info("")
            logger.info("📈 Performance Metrics:")
            logger.info(f"  Sensitivity (Recall):  {metrics['sensitivity']:.4f}  ({cm['tp']}/{counts['n_positive']} positives correctly identified)")
            logger.info(f"  Specificity:           {metrics['specificity']:.4f}  ({cm['tn']}/{counts['n_negative']} negatives correctly identified)")
            logger.info(f"  Precision (PPV):       {metrics['precision']:.4f}  ({cm['tp']}/{cm['tp']+cm['fp']} predicted positives were correct)")
            logger.info(f"  Overall Accuracy:      {metrics['accuracy']:.4f}  ({cm['tp']+cm['tn']}/{counts['n_total']} total correct)")
            logger.info("="*60)
            logger.info("")
            
            # Store validation results for later use
            self._final_validation_results = final_result
        
        # Optional: Differential Evolution optimization (if enabled)
        if self.config.optimize_for_validation_accuracy and best_k < n_dmps:
            logger.info("")
            logger.info(f"🧬 Starting Differential Evolution optimization from k={best_k:,}...")
            optimized_k = self._optimize_dmps_differential_evolution(
                sorted_df, best_k, n_dmps,
                X_calib, y_calib, X_test, y_test,
                val_positions, val_contexts
            )
            
            if optimized_k != best_k:
                logger.info(f"📈 DE optimization: k={best_k:,} → k={optimized_k:,}")
                best_k = optimized_k
            else:
                logger.info(f"📊 DE optimization: k={best_k:,} is already optimal")
            
            # Always validate final result after DE
            final_subset = sorted_df.iloc[:best_k]
            final_result = self._validate_classifier_subset(
                final_subset,
                X_calib, y_calib,
                X_test, y_test,
                val_positions, val_contexts
            )
            self._final_validation_results = final_result
            
            # Log final DE results
            final_ba = final_result['balanced_accuracy']
            cm = final_result['confusion_matrix']
            logger.info(f"✅ Final: k={best_k:,} DMPs, BA={final_ba:.4f}, TP={cm['tp']}, TN={cm['tn']}, FP={cm['fp']}, FN={cm['fn']}")
        else:
            # No DE optimization, use binary search result
            final_subset = sorted_df.iloc[:best_k]
        
        # If we used synthetic validation, verify on real samples from centroid metadata
        if self.config.validation_mode == "synthetic":
            logger.info("")
            logger.info("🔬 Verifying model on real samples from centroid metadata...")
            real_validation = self._validate_on_real_samples(final_subset)
            if real_validation is not None:
                logger.info(f"✅ Real validation: BA={real_validation['balanced_accuracy']:.4f}")
                logger.info(f"   TP={real_validation['confusion_matrix']['tp']}, "
                          f"TN={real_validation['confusion_matrix']['tn']}, "
                          f"FP={real_validation['confusion_matrix']['fp']}, "
                          f"FN={real_validation['confusion_matrix']['fn']}")
                # Store real validation results alongside synthetic
                self._real_validation_results = real_validation
        
        return final_subset
    
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
            # Get real samples from config (they should be specified there)
            real_class1_paths = self._get_validation_samples(
                self.config.centroid1_validation_samples,
                self.config.centroid1_dir,
                "centroid1"
            )
            real_class2_paths = self._get_validation_samples(
                self.config.centroid2_validation_samples,
                self.config.centroid2_dir,
                "centroid2"
            )
            
            if not real_class1_paths and not real_class2_paths:
                logger.warning("No real samples specified in config for verification")
                return None
            
            logger.info(f"   Loading {len(real_class1_paths)} healthy + {len(real_class2_paths)} cancer samples from metadata...")
            
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
        class2_paths: List[str]
    ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
        """
        Implementation of validation sample loading (extracted for reuse).
        """
        from pathlib import Path
        
        if not class1_paths and not class2_paths:
            return None
        
        # Extract positions and contexts from DMPs
        dmp_positions = dmps_df['position'].values
        dmp_contexts = dmps_df['context'].values
        
        # Create methylation matrix
        all_sample_paths = [(p, 0) for p in class1_paths] + [(p, 1) for p in class2_paths]
        n_samples = len(all_sample_paths)
        n_positions = len(dmp_positions)
        X = np.zeros((n_samples, n_positions))
        y = np.zeros(n_samples, dtype=int)
        
        # Load each sample and extract methylation values - VECTORIZED
        successful_samples = 0
        for i, (sample_path, label) in enumerate(all_sample_paths):
            try:
                sample_dir = Path(sample_path)
                
                # Group DMP positions by context for vectorized extraction
                context_groups = {}
                for ctx in np.unique(dmp_contexts):
                    ctx_mask = dmp_contexts == ctx
                    context_groups[ctx] = {
                        'indices': np.where(ctx_mask)[0],
                        'positions': dmp_positions[ctx_mask]
                    }
                    
                    # Determine the H5 file for this context
                    if sample_dir.suffix == '.h5':
                        h5_file = sample_dir
                    else:
                        h5_file = sample_dir / f"{self.config.chromosome}-{ctx}.h5"
                    
                    if h5_file.exists():
                        try:
                            # Load sample for this context
                            context_sample = MethylSample.load_from_h5(str(h5_file))
                            
                            # Vectorized position lookup using searchsorted
                            if not np.all(np.diff(context_sample.pos) >= 0):
                                sort_idx = np.argsort(context_sample.pos)
                                sorted_pos = context_sample.pos[sort_idx]
                                sorted_mC = context_sample.mC[sort_idx]
                                sorted_uC = context_sample.uC[sort_idx]
                            else:
                                sorted_pos = context_sample.pos
                                sorted_mC = context_sample.mC
                                sorted_uC = context_sample.uC
                            
                            search_indices = np.searchsorted(sorted_pos, context_groups[ctx]['positions'])
                            valid_mask = (search_indices < len(sorted_pos)) & (sorted_pos[search_indices] == context_groups[ctx]['positions'])
                            
                            mC_vals = np.where(valid_mask, sorted_mC[search_indices], 0)
                            uC_vals = np.where(valid_mask, sorted_uC[search_indices], 0)
                            total_vals = mC_vals + uC_vals
                            
                            with np.errstate(divide='ignore', invalid='ignore'):
                                meth_fractions = np.where(total_vals > 0, mC_vals / total_vals, np.nan)
                            meth_fractions = np.where(valid_mask, meth_fractions, np.nan)
                            
                            X[i, context_groups[ctx]['indices']] = meth_fractions
                            
                        except Exception as e:
                            logger.debug(f"Failed to load {h5_file}: {e}")
                            X[i, context_groups[ctx]['indices']] = np.nan
                    else:
                        X[i, context_groups[ctx]['indices']] = np.nan
                
                y[i] = label
                successful_samples += 1
                
            except Exception as e:
                logger.warning(f"Failed to load sample {sample_path}: {e}")
                X[i, :] = np.nan
                y[i] = label
        
        if successful_samples == 0:
            logger.error("No validation samples could be loaded")
            return None
        
        logger.debug(f"Loaded validation data: X shape={X.shape}, y shape={y.shape}, successful={successful_samples}/{n_samples}")
        
        return X, y, dmp_positions, dmp_contexts
    
    def _optimize_dmps_differential_evolution(
        self,
        sorted_df: pd.DataFrame,
        start_k: int,
        max_k: int,
        X_calib: np.ndarray,
        y_calib: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray,
        val_positions: np.ndarray,
        val_contexts: np.ndarray
    ) -> int:
        """
        Optimize DMP count using Differential Evolution for global search.
        
        Args:
            sorted_df: Sorted DMPs by importance
            start_k: Starting k from binary search
            max_k: Maximum k to consider
            X_calib, y_calib: Calibration set for Platt
            X_test, y_test: Test set for evaluation
            val_positions, val_contexts: Validation data positions
            
        Returns:
            Optimal k value
        """
        from scipy.optimize import differential_evolution
        
        logger.info(f"  Search range: k ∈ [10, {max_k:,}]")
        logger.info(f"  Starting hint: k={start_k:,}")
        
        # Cache for performance evaluations
        evaluation_cache = {}
        
        def objective_function(k_float):
            """Minimize negative BA = maximize BA"""
            k = int(round(k_float[0]))
            k = max(10, min(k, max_k))
            
            # Check cache
            if k in evaluation_cache:
                return -evaluation_cache[k]  # Return negative (we minimize)
            
            # Evaluate this k
            test_subset = sorted_df.iloc[:k]
            result = self._validate_classifier_subset(
                test_subset,
                X_calib, y_calib,
                X_test, y_test,
                val_positions, val_contexts
            )
            ba = result['balanced_accuracy']
            
            # Cache result
            evaluation_cache[k] = ba
            
            # Only log improvements or every 10th evaluation
            if ba > max(evaluation_cache.values(), default=0) or len(evaluation_cache) % 10 == 0:
                logger.info(f"    DE eval #{len(evaluation_cache)}: k={k:,} → BA={ba:.6f}")
            
            return -ba  # Minimize negative = maximize
        
        # Run Differential Evolution
        logger.info(f"  Running DE (maxiter=30, popsize=10)...")
        bounds = [(10, max_k)]
        
        result = differential_evolution(
            objective_function,
            bounds,
            maxiter=30,
            popsize=10,
            tol=0.001,
            seed=self.config.random_state,
            strategy='best1bin',
            workers=1
        )
        
        optimal_k = int(round(result.x[0]))
        optimal_ba = -result.fun
        
        logger.info(f"  ✅ DE complete: k={optimal_k:,}, BA={optimal_ba:.6f}")
        logger.info(f"  DE stats: {result.nfev} evaluations, {result.nit} iterations, success={result.success}")
        
        return optimal_k
    
    def _save_validation_results(self):
        """Save validation results to JSON file."""
        import json
        from datetime import datetime
        
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results_path = output_dir / f"validation_results-{self.config.chromosome}.json"
        
        # Prepare results for JSON serialization
        results = {
            'chromosome': self.config.chromosome,
            'timestamp': datetime.now().isoformat(),
            'config': {
                'target_balanced_accuracy': self.config.target_balanced_accuracy,
                'validation_mode': self.config.validation_mode,
                'min_dmps_for_export': self.config.min_dmps_for_export,
                'optimize_for_validation_accuracy': self.config.optimize_for_validation_accuracy
            }
        }
        
        # Add main validation results (from optimization)
        if hasattr(self, '_final_validation_results') and self._final_validation_results:
            results['optimization_validation'] = {
                'type': self.config.validation_mode,
                'performance': {
                    'balanced_accuracy': self._final_validation_results['balanced_accuracy'],
                    'sensitivity': self._final_validation_results['metrics']['sensitivity'],
                    'specificity': self._final_validation_results['metrics']['specificity'],
                    'precision': self._final_validation_results['metrics']['precision'],
                    'accuracy': self._final_validation_results['metrics']['accuracy']
                },
                'confusion_matrix': self._final_validation_results['confusion_matrix'],
                'sample_counts': self._final_validation_results['counts']
            }
        
        # Add real validation results if available (from synthetic mode verification)
        if hasattr(self, '_real_validation_results') and self._real_validation_results:
            results['real_validation'] = {
                'type': 'real',
                'performance': {
                    'balanced_accuracy': self._real_validation_results['balanced_accuracy'],
                    'sensitivity': self._real_validation_results['metrics']['sensitivity'],
                    'specificity': self._real_validation_results['metrics']['specificity'],
                    'precision': self._real_validation_results['metrics']['precision'],
                    'accuracy': self._real_validation_results['metrics']['accuracy']
                },
                'confusion_matrix': self._real_validation_results['confusion_matrix'],
                'sample_counts': self._real_validation_results['counts']
            }
        
        # Legacy format for backward compatibility (use optimization results)
        if hasattr(self, '_final_validation_results') and self._final_validation_results:
            results['performance'] = results['optimization_validation']['performance']
            results['confusion_matrix'] = results['optimization_validation']['confusion_matrix']
            results['sample_counts'] = results['optimization_validation']['sample_counts']
        
        # Save to JSON
        with open(results_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"💾 Saved validation results to {results_path}")
    
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
            csv_path = output_dir / f"dmps-{self.config.chromosome}{suffix}.csv"
        else:
            csv_path = output_dir / f"dmps-{self.config.chromosome}.csv"
        
        # Define export columns (include all relevant data)
        export_cols = [
            'chromosome', 'context', 'position',
            'p_value', 'q_value', 'delta_mean',
            'overlap', 'effect_size', 'context_weight',
            'alpha1', 'beta1', 'alpha2', 'beta2',
            'mean1', 'mean2'
        ]
        
        # Filter to only columns that exist
        available_cols = [c for c in export_cols if c in bio_dmps_df.columns]
        
        # Add delta_sign if possible - make explicit copy to avoid SettingWithCopyWarning
        export_df = bio_dmps_df.copy()
        if 'mean1' in export_df.columns and 'mean2' in export_df.columns:
            if 'delta_sign' not in export_df.columns:
                export_df['delta_sign'] = np.sign(export_df['mean1'] - export_df['mean2'])
            if 'delta_sign' not in available_cols:
                available_cols.insert(available_cols.index('delta_mean') + 1, 'delta_sign')
        
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
    
    def _save_unified_model(self, classifier: BetaBinomialClassifier, bio_dmps_df: pd.DataFrame):
        """
        Save unified Beta-Binomial classifier model.
        
        Args:
            classifier: BetaBinomialClassifier instance
            bio_dmps_df: DataFrame with biological DMPs
        """
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        model_path = output_dir / f"classifier-{self.config.chromosome}.pkl"
        
        # Create model package
        import pickle
        model_package = {
            'classifier': classifier,
            'context_weights_summary': bio_dmps_df.groupby('context')['context_weight'].first().to_dict(),
            'chromosome': self.config.chromosome,
            'n_dmps': len(bio_dmps_df),
            'n_dmps_per_context': bio_dmps_df.groupby('context').size().to_dict(),
            'metadata': {
                'version': '2.0.0',
                'classifier_type': 'BetaBinomialClassifier',
                'config': self.config.model_dump(),
                'trimmed_percentile': self.config.trimmed_percentile,
            }
        }
        
        # Save to pickle
        with open(model_path, 'wb') as f:
            pickle.dump(model_package, f)
        
        logger.info(f"💾 Saved model to {model_path}")
        logger.info(f"📦 Model package includes:")
        logger.info(f"  - Classifier: {classifier}")
        logger.info(f"  - Context weights: {model_package['context_weights_summary']}")
        logger.info(f"  - Total DMPs: {model_package['n_dmps']}")
        logger.info(f"  - DMPs per context: {model_package['n_dmps_per_context']}")
    
    def _create_multi_context_result(
        self, 
        dmps_df: pd.DataFrame, 
        bio_dmps_df: pd.DataFrame
    ) -> MethylDetectorResult:
        """
        Create result object for multi-context analysis.
        
        Args:
            dmps_df: DataFrame with all statistical DMPs
            bio_dmps_df: DataFrame with biological DMPs
            
        Returns:
            MethylDetectorResult
        """
        # Compute per-context statistics
        comparison_stats = []
        for context in self.config.contexts:
            ctx_dmps = dmps_df[dmps_df['context'] == context]
            ctx_bio = bio_dmps_df[bio_dmps_df['context'] == context]
            
            if len(ctx_dmps) > 0:
                stats = ComparisonStats(
                    comparison_name=f"{self.config.chromosome}-{context}",
                    total_positions=len(ctx_dmps),
                    statistical_dmps=len(ctx_dmps),
                    biological_dmps=len(ctx_bio),
                    processing_time_seconds=0.0,  # TODO: track per-context timing
                    gpu_used=self.gpu_config.GPU_AVAILABLE
                )
                comparison_stats.append(stats)
        
        # Create result
        result = MethylDetectorResult(
            biologically_significant_dmps_df=bio_dmps_df,
            total_statistical_dmps=len(dmps_df),
            total_biological_dmps=len(bio_dmps_df),
            biological_retention_rate=len(bio_dmps_df) / max(1, len(dmps_df)),
            comparison_stats=comparison_stats,
            timestamp=datetime.now().isoformat(),
            version="2.0.0-multi-context",
            config_summary=self.config.model_dump()
        )
        
        return result


    def _structured_array_to_dmp_df(self, structured_array: np.ndarray) -> pd.DataFrame:
        """Convert structured array to DataFrame with basic fields (fast, no objects)."""
        df = pd.DataFrame(structured_array)
        # Ensure 'position' column exists and is properly typed
        if 'position' not in df.columns:
            logger.warning("Structured array missing 'position' field; adding dummy positions")
            df['position'] = np.arange(len(df), dtype=np.uint32)
        # Ensure dtypes
        dtype_map = {
            "position": "uint32",
            "chromosome": "str",
            "context": "str",
            "p_value": "float32",
            "q_value": "float32",
            "delta_mean": "float32",
            "bhattacharyya": "float32",
            "weight": "float32",
            "alpha1": "float64",
            "beta1": "float64",
            "alpha2": "float64",
            "beta2": "float64",
            "mean1": "float32",
            "mean2": "float32",
            "selected": "bool",
        }
        for col, dtype in dtype_map.items():
            if col in df:
                df[col] = df[col].astype(dtype)
        return df

    def _compute_missing_metrics_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Vectorized computation of missing biological metrics on DataFrame. GPU-memory aware chunking."""
        import time
        df_start = time.time()
        n_rows = len(df)
        # Determine chunk size based on GPU memory (use max memory for performance)
        from methyl_utils import get_memory_usage
        available_gb = get_memory_usage().get('gpu_free_gb', 80.0)  # Fallback to 80GB if unavailable
        available_mb = available_gb * 1024
        # Estimate memory per row (rough: floats/int for columns)
        mem_per_row_mb = 0.3  # Less conservative estimate
        chunk_size = max(50000, int(available_mb * 0.9 / mem_per_row_mb))  # Use 90% of GPU mem
        logger.debug(f"GPU-aware chunking: {available_mb}MB available, chunk_size={chunk_size:,} rows")

        if n_rows > chunk_size:
            logger.info(f"🔄 Chunking metrics computation for {n_rows:,} rows (GPU-optimized batches of {chunk_size:,})")
            chunks = []
            for i in range(0, n_rows, chunk_size):
                end_i = min(i + chunk_size, n_rows)
                chunk_df = df.iloc[i:end_i].copy()
                chunk_result = self._compute_chunk_metrics_df(chunk_df)
                chunks.append(chunk_result)
            # Concat chunk DFs
            result_df = pd.concat(chunks, ignore_index=True)
            logger.info(f"📊 Chunked metrics complete for {n_rows:,} rows")
            return result_df
        else:
            return self._compute_chunk_metrics_df(df)

    def _compute_chunk_metrics_df(self, chunk_df: pd.DataFrame) -> pd.DataFrame:
        """Compute only essential metrics for a chunk DataFrame (vectorized, GPU-optimized)."""
        import time
        start_time = time.time()
        
        # MethylUtils provides 'bhattacharyya' column with Distance (BD) values
        # Convert to Coefficient (BC) for biologist-friendly interpretation
        if 'bhattacharyya' not in chunk_df.columns:
            logger.warning("Bhattacharyya Distance not found in chunk, computing...")
            alpha1 = chunk_df['alpha1'].values
            beta1 = chunk_df['beta1'].values
            alpha2 = chunk_df['alpha2'].values
            beta2 = chunk_df['beta2'].values
            delta_mean = chunk_df['delta_mean'].values
            
            try:
                # Compute Bhattacharyya Distance (BD) from MethylUtils
                bd_values = []
                for i in range(len(alpha1)):
                    try:
                        bd = compute_bhattacharyya_distance(alpha1[i], beta1[i], alpha2[i], beta2[i])
                        bd_values.append(bd)
                    except Exception as e:
                        logger.warning(f"Bhattacharyya Distance computation failed for position {i}: {e}")
                        bd_values.append(abs(delta_mean[i]))  # Fallback to delta_mean
                bd_array = np.array(bd_values, dtype=np.float32)
            except Exception as e:
                logger.warning(f"Bhattacharyya Distance computation failed: {e}, using fallback")
                bd_array = np.abs(delta_mean).astype(np.float32)
        else:
            # BD values from MethylUtils
            bd_array = chunk_df['bhattacharyya'].values
        
        # Convert BD to BC (overlap coefficient) for biologist-friendly interpretation
        # BC = exp(-BD), where BC ∈ [0,1]: 0 = no overlap, 1 = complete overlap
        bc_values = bhattacharyya_coefficient(bd_array)
        chunk_df['bhattacharyya_coefficient'] = bc_values
        chunk_df['overlap'] = bc_values  # Add 'overlap' column for CSV export (biologist-friendly name)
        
        # Remove the BD column - we only keep BC for outputs
        if 'bhattacharyya' in chunk_df.columns:
            chunk_df.drop(columns=['bhattacharyya'], inplace=True)

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
        Large effect size (|Δμ| ≥ {self.config.min_delta_mean}): {len(df[df['delta_mean'].abs() >= self.config.min_delta_mean]):,}
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
        """Export selected DMPs to CSV with required columns."""
        if biological_dmps_df.empty:
            logger.warning("No biological DMPs to export")
            return

        # Create a copy to avoid modifying the original DataFrame
        export_df = biological_dmps_df.copy()
        
        # Add sign of delta_mean (sign of mean1 - mean2)
        if 'mean1' in export_df.columns and 'mean2' in export_df.columns:
            export_df['delta_sign'] = np.sign(export_df['mean1'] - export_df['mean2'])
            logger.debug("Added delta_sign column (sign of mean1 - mean2)")
        else:
            logger.warning("mean1 and/or mean2 columns not found, cannot compute delta_sign")
        
        # Map effect_size to weight if effect_size exists
        if 'effect_size' in export_df.columns:
            export_df['weight'] = export_df['effect_size']
            logger.debug("Mapped effect_size to weight column")
        elif 'weight' not in export_df.columns:
            logger.warning("Neither effect_size nor weight column found")
        
        # Map overlap from bhattacharyya_coefficient if needed
        if 'overlap' not in export_df.columns and 'bhattacharyya_coefficient' in export_df.columns:
            export_df['overlap'] = export_df['bhattacharyya_coefficient']
            logger.debug("Mapped bhattacharyya_coefficient to overlap column")
        
        # Define required columns (with weight instead of effect_size)
        required_cols = [
            'chromosome', 'context', 'position', 'p_value', 'q_value', 'delta_mean', 'delta_sign',
            'overlap', 'weight'
        ]
        
        # Select only available required columns
        export_cols = [c for c in required_cols if c in export_df.columns]
        missing_cols = [c for c in required_cols if c not in export_df.columns]
        
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
                             biological_dmps_df: Optional[pd.DataFrame] = None) -> MethylDetectorResult:
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

        result = MethylDetectorResult(
            biologically_significant_dmps_df=biological_dmps_df,
            total_statistical_dmps=total_statistical_dmps,
            total_biological_dmps=len(biological_dmps_df) if biological_dmps_df is not None else 0,
            biological_retention_rate=len(biological_dmps_df) / max(1, total_statistical_dmps) if biological_dmps_df is not None else 0.0,
            comparison_stats=comparison_stats,
            timestamp=datetime.now().isoformat(),
            version="2.0.0",
            config_summary=self.config.model_dump()
        )
        return result

    def _save_results(self, result: MethylDetectorResult) -> None:
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
            "max_bc": self.config.max_bc,
            "target_balanced_accuracy": self.config.target_balanced_accuracy,
            "min_selected_dmps": self.config.min_selected_dmps,
            "biological_filters": self.config.biological_filters,
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
        summary = MethylDetectorSummary(
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
            f"  Min Delta Mean: {self.config.min_delta_mean}",
            f"  Max Overlap (Bhattacharyya Coefficient): {self.config.max_bc} ({self.config.max_bc*100:.0f}%)",
            f"  Target Balanced Accuracy: {self.config.target_balanced_accuracy}",
            "",
            "Biological Importance (Effect Size):",
            f"  Formula: effect_size = |delta_mu| / sqrt(var1² + var2²) * (1 - BC)^gamma",
            f"  This is a variance-weighted, overlap-penalized metric combining:",
            f"    • Standardized mean difference (confidence-weighted)",
            f"    • Distribution overlap penalty: (1 - BC)^{self.config.gamma}",
            f"  where BC = Bhattacharyya Coefficient (0=no overlap, 1=complete overlap)",
            f"  Higher values indicate more reliable, biologically significant DMPs",
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
    script_dir = Path(__file__).parent  # methyl_detector/core/
    package_root = script_dir.parent  # methyl_detector/
    # Add package root to sys.path for imports
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    # Also add methylutils from monorepo if available (for development)
    # In monorepo: packages/methyldetector/../methylutils/methyl_utils
    methyl_utils_path = package_root.parent.parent / "methylutils" / "methyl_utils"
    if methyl_utils_path.exists() and str(methyl_utils_path) not in sys.path:
        sys.path.insert(0, str(methyl_utils_path))
    # Now import the relative imports and update globals
    global MethylDetectorConfig, ComparisonStats, MethylDetectorResult
    global GPUConfig, save_csv, save_json, save_summary_txt
    global CentroidPairHandler, create_centroid_from_arrays, get_chromosome_context_from_filename
    try:
        from models.config import MethylDetectorConfig as MDC
        from models.results import (
            ComparisonStats as CS,
            MethylDetectorResult as MDR,
            MethylDetectorSummary as MDS,
        )
        from utils.core import (
            GPUConfig as GC,
            save_csv as sc,
            save_json as sj,
            save_summary_txt as sst,
        )
        from utils.sample_handler import (
            CentroidPairHandler as CPH,
            create_centroid_from_arrays as cca,
        )
        from utils.file_utils import get_chromosome_context_from_filename as gccf

        # Update the global variables
        MethylDetectorConfig = MDC
        ComparisonStats = CS
        MethylDetectorResult = MDR
        MethylDetectorSummary = MDS
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
    """Allow direct execution of MethylDetector for development/testing."""
    _setup_imports_for_direct_execution()
    # Delegate to CLI main function
    try:
        from methyl_detector.cli.main import main

        main()
    except ImportError as e:
        import sys

        print(f"Error: {e}")
        print("Try running: python run_methyl_detector.py")
        print("Or: python -m methyl_detector.cli.main")
        sys.exit(1)
