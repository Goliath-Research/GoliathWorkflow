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

# Import Beta-Binomial classifier
from .beta_binomial_classifier import BetaBinomialClassifier

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
    
    def _create_trainer_config(self) -> 'TrainingConfig':
        """Convert MethylDetectorConfig to TrainingConfig for delegation."""
        if TrainingConfig is None:
            raise ImportError("TrainingConfig not available")
        
        return TrainingConfig(
            centroid1_path=str(self.config.centroid1_path),
            centroid2_path=str(self.config.centroid2_path),
            output_path=str(Path(self.config.output_dir) / f"classifier-{self.chrom}-{self.ctx}.pkl"),
            chromosome=self.chrom,
            context=self.ctx,
            # Advanced filtering configuration
            alpha=self.config.alpha,
            min_N_pct=self.config.min_N_pct,
            min_delta_mean=self.config.min_delta_mean,
            max_bc=self.config.max_bc,
            gamma=self.config.gamma,
            min_effect_size=self.config.min_effect_size if hasattr(self.config, 'min_effect_size') else None,
            biological_filters=True,
            # Binary search configuration
            target_balanced_accuracy=self.config.target_balanced_accuracy,
            min_selected_dmps=self.config.min_selected_dmps if hasattr(self.config, 'min_selected_dmps') else None,
            min_dmps_for_export=self.config.min_dmps_for_export,
            # Validation configuration
            validation_mode=self.config.validation_mode,
            centroid1_validation_samples=self.config.centroid1_validation_samples,
            centroid2_validation_samples=self.config.centroid2_validation_samples,
            n_validation_samples=self.config.n_validation_samples,
            # Validation-accuracy optimization
            optimize_for_validation_accuracy=self.config.optimize_for_validation_accuracy,
            # GPU configuration
            use_gpu=self.config.use_gpu,
            random_state=self.config.random_state,
            verbose=True,
            # New params
            temperature=self.config.temperature,
            enable_platt_calibration=self.config.enable_platt_calibration
            # No validation_data_path
        )

    def run(self) -> MethylDetectorResult:
        """Run the complete DMP detection and filtering pipeline."""
        logger.debug("Starting MethylDetector analysis pipeline...")
        
        # Check if using multi-context mode or legacy single-context mode
        use_multi_context = (
            hasattr(self.config, 'chromosome') and 
            hasattr(self.config, 'centroid1_dir') and
            hasattr(self.config, 'centroid2_dir') and
            self.config.centroid1_dir is not None and
            self.config.centroid2_dir is not None
        )
        
        if use_multi_context:
            return self._run_multi_context()
        else:
            return self._run_single_context()
    
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
        
        # Train Beta-Binomial classifier
        logger.info("🤖 Training Beta-Binomial classifier...")
        classifier = BetaBinomialClassifier.from_dataframe(bio_dmps_df, self.config.chromosome)
        logger.info(f"✅ Classifier created: {classifier}")
        
        # Export unified CSV
        if self.config.output_dir:
            logger.info("💾 Exporting unified CSV...")
            self._export_unified_csv(bio_dmps_df)
            
            # Save model
            logger.info("💾 Saving classifier model...")
            self._save_unified_model(classifier, bio_dmps_df)
        
        # Create result
        result = self._create_multi_context_result(dmps_df, bio_dmps_df)
        logger.info(f"✅ Multi-context analysis complete for chromosome {self.config.chromosome}!")
        
        return result
    
    def _run_single_context(self) -> MethylDetectorResult:
        """Run legacy single-context analysis (backward compatibility)."""
        logger.debug("Starting MethylDetector analysis pipeline (single-context mode)...")

        # Step 1: Detect statistical DMPs (DataFrame-centric)
        logger.debug("Step 1: Detecting statistical DMPs...")
        try:
            dmp_df = self._detect_statistical_dmps()
            logger.debug(f"Step 1 completed: {len(dmp_df):,} DMPs detected")
        except Exception as e:
            logger.error(f"Step 1 failed: {e}")
            import traceback

            traceback.print_exc()
            raise

        # Add DMP indices for auto-calibration
        self.dmp_positions = dmp_df['position'].values
        self.selected_dmps_indices = np.searchsorted(self.centroid1.pos, self.dmp_positions)
        logger.info(f"Set selected_dmps_indices with {len(self.selected_dmps_indices)} DMPs for auto-calibration")

        # Step 2: Train classifier using MethylTrainer (DELEGATED)
        # This includes filtering, binary search, and validation
        biological_dmps_df = pd.DataFrame()
        accuracy = None
        
        if not dmp_df.empty and self.config.output_dir:
            logger.info("Step 2: Training classifier using MethylTrainer...")
            try:
                # Create TrainingConfig from MethylDetectorConfig
                trainer_config = self._create_trainer_config()
                
                # Create trainer and train from DMPs
                trainer = MethylTrainer(trainer_config)
                model_package = trainer.train_from_dmps(
                    dmp_df=dmp_df,
                    centroid1_path=Path(self.config.centroid1_path),
                    centroid2_path=Path(self.config.centroid2_path),
                    chromosome=self.chrom,
                    context=self.ctx
                )

                self.classifier = model_package['classifier']  # Add this line - extract from package
                logger.info("Extracted classifier for auto-calibration")
                
                # Extract results
                biological_dmps_df = model_package.get('selected_dmps_df', pd.DataFrame())
                accuracy = model_package.get('validation_accuracy')
                classifier = model_package.get('classifier')
                
                # Export selected DMPs to CSV
                if not biological_dmps_df.empty:
                    self._export_selected_dmps_csv(biological_dmps_df)
                
                # Save model
                if classifier is not None:
                    output_dir = Path(self.config.output_dir)
                    model_path = output_dir / f"classifier-{self.chrom}-{self.ctx}.pkl"
                    
                    import pickle
                    with open(model_path, 'wb') as f:
                        pickle.dump(model_package, f)
                    logger.info(f"✅ Classifier saved to {model_path}")
                    
                    # Update model_metadata with new parameters
                    model_metadata = model_package.get('metadata', {})
                    model_metadata['temperature'] = self.config.temperature
                    model_metadata['enable_platt_calibration'] = self.config.enable_platt_calibration                    # Save updated metadata with model
                    with open(model_path, 'rb') as f:
                        model_package_data = pickle.load(f)
                    model_package_data['metadata'] = model_metadata
                    with open(model_path, 'wb') as f:
                        pickle.dump(model_package_data, f)
                    logger.info(f"✅ Model metadata updated and saved to {model_path}")
                    
                    if self.config.enable_platt_calibration:
                        # Load centroids if not loaded
                        self.centroid1 = MethylSample.load_from_h5(self.config.centroid1_path)
                        self.centroid2 = MethylSample.load_from_h5(self.config.centroid2_path)
                        paths0 = self.centroid1.samples
                        paths1 = self.centroid2.samples
                        samples0 = [MethylSample.load_from_h5(p) for p in paths0]
                        samples1 = [MethylSample.load_from_h5(p) for p in paths1]
                        dmp_indices = self.selected_dmps_indices
                        X0 = np.array([s.methylation_levels[dmp_indices] for s in samples0])
                        X1 = np.array([s.methylation_levels[dmp_indices] for s in samples1])
                        X_val = np.vstack([X0, X1])
                        y_val = np.array([0] * len(samples0) + [1] * len(samples1))
                        if self.classifier.n_dmps == 0 or len(X_val[0]) != self.classifier.n_dmps:
                            logger.warning("Model has 0 DMPs or shape mismatch—skipping calibration")
                        else:
                            self.classifier.calibrate_platt(X_val, y_val)
                            logger.info(f"Auto-calibrated Platt using {len(y_val)} samples from centroids")
                        
                        # Save calibrator in metadata
                        model_metadata = model_package.get('metadata', {})
                        model_metadata['platt_calibrator'] = pickle.dumps(self.classifier.calibrator)
                        model_package['metadata'] = model_metadata
                        with open(model_path, 'wb') as f:
                            pickle.dump(model_package, f)
                        logger.info("Saved pre-fitted Platt calibrator in model metadata")

            except Exception as e:
                logger.error(f"❌ Training with MethylTrainer failed: {e}")
                import traceback
                traceback.print_exc()
                biological_dmps_df = pd.DataFrame()
                accuracy = None

        logger.info("🔄 Step 3: Generating final results...")
        result = self._create_final_result(
            dmp_df, biological_dmps_df=biological_dmps_df
        )
        logger.info("✅ Step 3 completed successfully")

        # Update result with training accuracy if available
        logger.info("🔄 Updating result with training accuracy...")
        if accuracy is not None:
            result.training_accuracy = float(accuracy)
            if self.config.output_dir:
                output_dir = Path(self.config.output_dir)
                model_path = output_dir / f"classifier-{self.chrom}-{self.ctx}.pkl"
                result.classifier_model_path = str(model_path)
        logger.info("✅ Result updated with training accuracy")
        
        # Step 5: Save results
        if self.config.output_dir:
            logger.info("🔄 Step 5: Saving results...")
            self._save_results(result)
            logger.info("✅ Step 5: Results saved")

        dmp_count = len(result.biologically_significant_dmps_df) if result.biologically_significant_dmps_df is not None else 0
        logger.info(
            f"✅ Analysis complete! Found {dmp_count} DMPs"
        )
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

    def _detect_statistical_dmps(self) -> pd.DataFrame:
        """Detect statistically significant DMPs using MethylCentroidPair. Returns a DataFrame-centric result."""
        logger.debug("Processing centroids...")
        output_dir = Path(self.config.output_dir) if self.config.output_dir else Path.cwd()
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load and align centroids directly via MethylCentroidPair
        min_coverage = self.config.effective_min_N(10)  # Fallback cohort size
        centroid1, centroid2, common_positions = MethylCentroidPair.load_and_align(
            self.config.centroid1_path, 
            self.config.centroid2_path, 
            min_coverage=min_coverage
        )
        # Store centroids for later model training
        self.centroid1 = centroid1
        self.centroid2 = centroid2
        # Determine cohort size from centroid data (max coverage across both centroids)
        max_coverage = max(centroid1.N.max() if centroid1.N is not None else 0,
                    centroid2.N.max() if centroid2.N is not None else 0)
        cohort_size = max(max_coverage, 10)  # Use at least 10 as fallback
        effective_min_coverage = self.config.effective_min_N(cohort_size)
        
        # Use MethylCentroidPair for all mathematical operations
        centroid_pair = MethylCentroidPair(min_coverage=effective_min_coverage)
        
        # Time the centroid comparison
        import time
        start_time = time.time()
        logger.debug(f"Starting compare_centroids for single with {len(centroid1.pos):,} positions")
        
        # Get results as DataFrame (always)
        comparison_results = centroid_pair.compare_centroids(centroid1, centroid2)
        processing_time_seconds = time.time() - start_time
        logger.info(f"compare_centroids completed in {processing_time_seconds:.2f}s for single")
        logger.debug(f"DataFrame shape: {comparison_results.shape}")
        
        # Apply statistical filtering: keep only q_value <= alpha
        import numpy as np
        total_positions = len(comparison_results)
        filtered_results = comparison_results[comparison_results['q_value'] <= self.config.alpha].copy()
        statistical_dmps_count = len(filtered_results)
        logger.info(f"📊 Statistical filtering for single: {statistical_dmps_count:,} significant DMPs (q≤{self.config.alpha}) out of {total_positions:,} positions ({(statistical_dmps_count/total_positions)*100:.1f}% pass rate)")
        
        # Already have DataFrame, just compute missing metrics
        dmp_df = self._compute_missing_metrics_df(filtered_results)
        # Extract chromosome and context from centroid filename
        chrom_info = get_chromosome_context_from_filename(self.config.centroid1_path)
        chromosome = chrom_info.get('chromosome', 'unknown')
        context = chrom_info.get('context', 'unknown')
        dmp_df['chromosome'] = chromosome
        dmp_df['context'] = context
        # Store metadata for later use
        self.chrom = chromosome
        self.ctx = context
        self.total_positions = total_positions
        self.statistical_dmps_count = statistical_dmps_count
        self.processing_time_seconds = processing_time_seconds
        return dmp_df
    
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
            logger.debug(f"Context {context}: trimmed mean = {w_c:.6f} "
                        f"(n_trimmed={len(S_trimmed)}, n_total={len(S)})")
        
        # Normalize weights to sum=1
        total_weight = sum(weight_map.values())
        if total_weight > 0:
            weight_map = {k: v / total_weight for k, v in weight_map.items()}
        else:
            # Fallback to equal weights if all zeros
            n_contexts = len(weight_map)
            weight_map = {k: 1.0 / n_contexts for k in weight_map.keys()}
            logger.warning("All context weights are zero, using equal weights")
        
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
    
    def _export_unified_csv(self, bio_dmps_df: pd.DataFrame) -> Path:
        """
        Export unified CSV with all contexts combined.
        
        Args:
            bio_dmps_df: DataFrame with biological DMPs
            
        Returns:
            Path to exported CSV file
        """
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
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
        
        # Add delta_sign if possible
        if 'mean1' in bio_dmps_df.columns and 'mean2' in bio_dmps_df.columns:
            if 'delta_sign' not in bio_dmps_df.columns:
                bio_dmps_df['delta_sign'] = np.sign(bio_dmps_df['mean1'] - bio_dmps_df['mean2'])
            if 'delta_sign' not in available_cols:
                available_cols.insert(available_cols.index('delta_mean') + 1, 'delta_sign')
        
        # Export to CSV
        bio_dmps_df[available_cols].to_csv(csv_path, index=False)
        
        logger.info(f"📁 Exported {len(bio_dmps_df):,} DMPs to {csv_path}")
        logger.info(f"📊 Columns: {', '.join(available_cols)}")
        
        # Log per-context counts
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
