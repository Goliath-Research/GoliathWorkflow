"""Core MethylModeler pipeline for DMP detection, filtering, and selection."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union
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

# Import BetaClassifier from MethylUtils
from methyl_utils import BetaClassifier

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
import psutil  # For mem tracking (pip install psutil if needed)

# Add import at top if not present
from methyl_utils.classifier_factory import ClassifierFactory

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


class MethylModeler:
    """Main class for MethylModeler DMP detection and filtering."""

    def __init__(self, config: MethylModelerConfig):
        """Initialize with configuration."""
        self.config = config
        np.random.seed(config.random_state)
        self.gpu_config = GPUConfig()  # From MethylUtils for memory management
        self.df = None  # Current working dataframe
        self._exported_csv_path = None  # Path to exported CSV file
        logger.debug("Initialized MethylModeler")
    
    def run(self) -> MethylModelerResult:
        """Run the complete DMP detection and filtering pipeline."""
        logger.debug("Starting MethylModeler analysis pipeline...")
        
        # Single unified implementation for all cases
        return self._run_multi_context()
    
    def _run_multi_context(self) -> MethylModelerResult:
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
        
        # Prepare DMPs for validation and optimization
        selected_dmps_df = bio_dmps_df
        pre_optimization_dmps_df = None
               
        if self.config.optimize_dmps:
            logger.info("🎯 Preparing DMPs for validation and optimization...")
            selected_dmps_df = self._select_dmps_multicontext(bio_dmps_df)
            logger.info(f"✅ Prepared {len(selected_dmps_df):,} DMPs for validation")

            # Store pre-optimization result for export comparison (before advanced optimization)
            pre_optimization_dmps_df = selected_dmps_df.copy()
            
            # Export Stage 2: Pre-optimization DMPs (before advanced optimization)
            # Only export now if advanced optimization is not enabled (otherwise export after optimization)
            if self.config.output_dir and self.config.optimization_method not in ["bayesian_optimization", "featurecuts"]:
                logger.info("💾 Exporting Stage 2: Pre-optimization DMPs...")
                self._export_unified_csv(pre_optimization_dmps_df, suffix="-2-pre-optimization")
        else:
            logger.info("📋 Using all biological DMPs (optimize_dmps=False)")
        
        # Prepare classifier data
        classifier_data = {
            'positions': selected_dmps_df['position'].values,
            'contexts': selected_dmps_df['context'].values,
            'alpha1': selected_dmps_df['alpha1'].values,
            'beta1': selected_dmps_df['beta1'].values,
            'alpha2': selected_dmps_df['alpha2'].values,
            'beta2': selected_dmps_df['beta2'].values,
            'weights': selected_dmps_df.get('effect_size', np.ones(len(selected_dmps_df))).values
        }

        # Create classifier using factory based on config
        classifier_type_str = self.config.classifier_type
        classifier = ClassifierFactory.create(
            classifier_type_str,
            classifier_data,
            min_sample_coverage=self.config.min_sample_coverage,
            coverage_weighting=self.config.classifier_coverage_weighting
        )

        logger.info(f"✅ Classifier created: {classifier}")
        
        # Export unified CSVs
        if self.config.output_dir:
            # Export Stage 2: Pre-optimization DMPs (if optimization was enabled, export now)
            if pre_optimization_dmps_df is not None and self.config.optimize_dmps:
                logger.info("💾 Exporting Stage 2: Pre-optimization DMPs...")
                self._export_unified_csv(pre_optimization_dmps_df, suffix="-2-pre-optimization")
            
            # Export Stage 3: Final DMPs (after optimization if enabled)
            if self.config.optimize_dmps and pre_optimization_dmps_df is not None:
                logger.info("💾 Exporting Stage 3: Optimized DMPs...")
                self._export_unified_csv(selected_dmps_df, suffix="-3-optimized")
            else:
                # Export final CSV with default name
                logger.info("💾 Exporting final DMPs...")
                self._export_unified_csv(selected_dmps_df)
            
            # Save model
            logger.info("💾 Saving classifier model...")
            self._save_unified_model(classifier, selected_dmps_df)
            
            # Save validation results if optimization produced them
            if hasattr(self, '_final_validation_results') and self._final_validation_results:
                self._save_validation_results(n_dmps_exported=len(selected_dmps_df))
        
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
                        # Use the .samples property which checks both 'sample_paths' and 'samples_used'
                        # Centroids are typically saved with 'samples_used' in metadata
                        if centroid.metadata:
                            samples = centroid.samples  # This property handles both 'sample_paths' and 'samples_used'
                            if samples:
                                logger.info(f"✅ Loaded {len(samples)} validation samples from {centroid_name} metadata")
                                return samples
                            else:
                                logger.warning(f"No sample paths found in {centroid_name} metadata (checked 'sample_paths' and 'samples_used')")
                        else:
                            logger.warning(f"No metadata in {centroid_name} centroid")
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
        Load validation samples for multi-context optimization.
        
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
            
            # Create dmpDF for BetaClassifier
            weights = dmps_for_classifier.get('effect_size', np.ones(len(dmps_for_classifier)))
            if isinstance(weights, pd.Series):
                weights = weights.values
            
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
            
            # PHASE 1: Fit Platt calibration using calibration set (if supported)
            # BetaClassifier uses calibrate_platt method with methylation levels
            X_calib_subset_clean = X_calib_subset.copy()
            X_calib_subset_clean = np.nan_to_num(X_calib_subset_clean, nan=0.5)
            X_calib_subset_clean = np.clip(X_calib_subset_clean, 1e-6, 1-1e-6)
            
            # Create availability mask
            calib_availability = ~np.isnan(X_calib_subset)
            
            # Fit Platt calibration if method exists
            if hasattr(temp_classifier, 'calibrate_platt'):
                try:
                    temp_classifier.calibrate_platt(X_calib_subset_clean, y_calib, calib_availability)
                except Exception as e:
                    logger.warning(f"Platt calibration failed: {e}, using uncalibrated predictions")
            
            # PHASE 2: Evaluate on held-out test set
            X_test_subset_clean = X_test_subset.copy()
            X_test_subset_clean = np.nan_to_num(X_test_subset_clean, nan=0.5)
            X_test_subset_clean = np.clip(X_test_subset_clean, 1e-6, 1-1e-6)
            test_availability = ~np.isnan(X_test_subset)
            
            # Get probabilities using BetaClassifier.predict_proba
            test_probas = temp_classifier.predict_proba(X_test_subset_clean, test_availability, debug=False)
            
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
    
    def _select_dmps_multicontext(self, bio_dmps_df: pd.DataFrame) -> pd.DataFrame:
        """
        Prepare DMPs for validation and optimization in multi-context mode.

        Loads validation data and sorts DMPs by biological importance.
        Returns all DMPs for subsequent optimization if enabled.

        Args:
            bio_dmps_df: DataFrame of biologically filtered DMPs

        Returns:
            DataFrame with sorted DMPs ready for optimization
        """
        n_dmps = len(bio_dmps_df)
        logger.info(f"🔍 Preparing DMPs for validation: {n_dmps:,} candidates")
        
        if n_dmps == 0:
            return bio_dmps_df
        
        # Compute importance scores and sort
        logger.debug("Computing biological importance scores...")
        sorted_df = self._compute_biological_importance(bio_dmps_df)
        
        # Load validation samples if in real mode
        validation_data = None
        if self.config.validation_mode == "real":
            logger.info("📊 Loading validation samples for optimization...")
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
                
                # Store both sets for downstream optimization
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

        selected_dmps_df = sorted_df
        final_result = None

        if self.config.validation_mode == "real" and self.config.optimize_dmps:
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

            else:
                logger.warning(
                    f"Unknown optimization_method '{self.config.optimization_method}', skipping optimization step."
                )

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
                            in_bounds = search_indices < len(sorted_pos)
                            search_indices_safe = np.clip(search_indices, 0, len(sorted_pos) - 1)
                            exact_matches = sorted_pos[search_indices_safe] == context_groups[ctx]['positions']
                            valid_mask = in_bounds & exact_matches
                            
                            mC_vals = np.where(valid_mask, sorted_mC[search_indices_safe], 0)
                            uC_vals = np.where(valid_mask, sorted_uC[search_indices_safe], 0)
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

        Evaluates a diverse set of k values, refines around the strongest performers,
        and returns the minimal k that attains the maximal balanced accuracy along
        with the cached validation result for that subset.

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

        logger.info(f"  FeatureCuts search range: k ∈ [{min_k:,}, {max_k:,}]")

        # Coarse grid: logarithmic sampling (similar to binary search efficiency)
        # Evaluate ~15-20 candidates total (log2(123k) ≈ 17, so similar efficiency)
        n_coarse = min(20, max_k - min_k + 1)
        
        if max_k <= 50:
            candidate_k = np.arange(min_k, max_k + 1, dtype=np.int64)
        else:
            candidate_k = np.array([min_k, max_k], dtype=np.int64)
            if initial_k is not None:
                heuristic_k = np.clip(int(initial_k), min_k, max_k)
                candidate_k = np.append(candidate_k, heuristic_k)
            
            if max_k > min_k + 2:
                geom = np.geomspace(max(min_k, 1), max_k, n_coarse - candidate_k.size)
                candidate_k = np.append(candidate_k, geom.astype(np.int64))
        
        candidate_k = np.unique(np.clip(candidate_k, min_k, max_k))
        n_candidates = candidate_k.size
        
        ba_results = np.empty(n_candidates, dtype=np.float64)
        detailed_results = []
        
        logger.info(f"  Evaluating {n_candidates} candidate k values...")
        
        for i in range(n_candidates):
            k = int(candidate_k[i])
            subset_df = sorted_df.iloc[:k]
            result = self._validate_classifier_subset(
                subset_df,
                X_calib, y_calib,
                X_test, y_test,
                val_positions, val_contexts
            )
            ba_results[i] = result['balanced_accuracy']
            detailed_results.append(result)
            logger.debug(f"    k={k:,} → BA={ba_results[i]:.6f}")
        
        max_ba = ba_results.max()
        best_mask = np.isclose(ba_results, max_ba, atol=1e-6) | (ba_results == max_ba)
        best_indices = np.where(best_mask)[0]
        best_k_values = candidate_k[best_indices]
        best_k = int(best_k_values.min())
        best_result_idx = int(best_indices[best_k_values == best_k][0])
        best_result = detailed_results[best_result_idx]
        
        logger.info(f"  FeatureCuts: {n_candidates} evaluations, max BA={max_ba:.6f} at k={best_k:,}")
        
        top5_indices = np.argsort(-ba_results)[:5]
        if top5_indices.size > 0:
            logger.info("  Top candidates:")
            for rank, idx in enumerate(top5_indices, 1):
                logger.info(f"    [{rank}] k={int(candidate_k[idx]):,} → BA={ba_results[idx]:.6f}")
        
        return best_k, best_result

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

    
    def _save_validation_results(self, n_dmps_exported: Optional[int] = None):
        """Save validation results to JSON file using Pydantic model."""
        import json
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

        results_path = output_dir / f"results-{self.config.chromosome}.json"

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

        # Create the main results object
        results = MethylModelerValidationResults(
            chromosome=self.config.chromosome,
            timestamp=datetime.now().isoformat(),
            config=config_dict,
            optimization_validation=optimization_validation,
            real_validation=real_validation,
            n_dmps_exported=n_dmps_exported
        )

        # Save to JSON using Pydantic's model_dump_json for proper serialization
        with open(results_path, 'w') as f:
            f.write(results.model_dump_json(indent=2))

        logger.info(f"💾 Saved results to {results_path}")
    
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
    
    def _save_unified_model(self, classifier, selected_dmps_df: pd.DataFrame):
        """
        Save unified BetaClassifier model with strongly-typed dmpDF.
        
        Args:
            classifier: Classifier instance (ignored, we create BetaClassifier from dmpDF)
            selected_dmps_df: DataFrame with selected DMPs (final DMPs used by classifier)
        """
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        model_path = output_dir / f"classifier-{self.config.chromosome}.pkl"
        
        # Create strongly-typed dmpDF DataFrame
        # Get weight from effect_size or context_weight, defaulting to 1.0
        if 'effect_size' in selected_dmps_df.columns:
            weights = selected_dmps_df['effect_size'].values
        elif 'context_weight' in selected_dmps_df.columns:
            weights = selected_dmps_df['context_weight'].values
        else:
            weights = np.ones(len(selected_dmps_df), dtype=np.float64)
        
        dmpDF = pd.DataFrame({
            'pos': selected_dmps_df['position'].values.astype(np.int64),
            'alpha1': selected_dmps_df['alpha1'].values.astype(np.float64),
            'beta1': selected_dmps_df['beta1'].values.astype(np.float64),
            'alpha2': selected_dmps_df['alpha2'].values.astype(np.float64),
            'beta2': selected_dmps_df['beta2'].values.astype(np.float64),
            'weight': weights.astype(np.float64)
        })
        
        # Create BetaClassifier from dmpDF
        beta_classifier = BetaClassifier.from_dataframe(
            dmpDF,
            min_sample_coverage=self.config.min_sample_coverage,
            coverage_weighting=self.config.classifier_coverage_weighting
        )
        
        # Create model package
        import pickle
        model_package = {
            'classifier': beta_classifier,
            'dmpDF': dmpDF,  # Strongly typed DataFrame
            'context_weights_summary': selected_dmps_df.groupby('context')['context_weight'].first().to_dict() if 'context' in selected_dmps_df.columns else {},
            'chromosome': self.config.chromosome,
            'n_dmps': len(selected_dmps_df),
            'n_dmps_per_context': selected_dmps_df.groupby('context').size().to_dict() if 'context' in selected_dmps_df.columns else {},
            'metadata': {
                'version': '2.0.0',
                'classifier_type': 'BetaClassifier',
                'config': self.config.model_dump(),
                'trimmed_percentile_low': self.config.trimmed_percentile_low,
                'trimmed_percentile_high': self.config.trimmed_percentile_high,
            }
        }
        
        # Save to pickle
        with open(model_path, 'wb') as f:
            pickle.dump(model_package, f)
        
        logger.info(f"💾 Saved model to {model_path}")
        logger.info(f"📦 Model package includes:")
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
                    comparison_name=f"{self.config.chromosome}-{context}",
                    total_positions=len(ctx_dmps),
                    statistical_dmps=len(ctx_dmps),
                    biological_dmps=len(ctx_bio),
                    processing_time_seconds=0.0,  # TODO: track per-context timing
                    gpu_used=self.gpu_config.GPU_AVAILABLE
                )
                comparison_stats.append(stats)
        
        # Create result
        result = MethylModelerResult(
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

        result = MethylModelerResult(
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
    global MethylModelerConfig, ComparisonStats, MethylModelerResult
    global GPUConfig, save_csv, save_json, save_summary_txt
    global CentroidPairHandler, create_centroid_from_arrays, get_chromosome_context_from_filename
    try:
        from models.config import MethylModelerConfig as MDC
        from models.results import (
            ComparisonStats as CS,
            MethylModelerResult as MDR,
            MethylModelerSummary as MDS,
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
        from methyl_modeler.cli.main import main

        main()
    except ImportError as e:
        import sys

        print(f"Error: {e}")
        print("Try running: python run_methyl_modeler.py")
        print("Or: python -m methyl_modeler.cli.main")
        sys.exit(1)
