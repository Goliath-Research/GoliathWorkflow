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

# Import MethylTrainer for delegating training logic (required dependency)
from methyl_trainer import MethylTrainer, TrainingConfig

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
            target_auc=self.config.target_auc,
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

    # NOTE: Training methods moved to MethylTrainer (packages/methyltrainer)
    # The following methods have been moved:
    # - _filter_and_select_dmps, _apply_biological_filters, _compute_effect_size
    # - _select_dmps_binary_search, _compute_subset_performance
    # - _validate_classifier_on_synthetic_samples, _validate_classifier_on_real_samples
    # - _get_validation_sample_paths, _load_validation_samples_for_binary_search
    # - _compute_real_auc_from_samples, _load_sample_methylation_at_dmps
    #
    # MethylDetector now delegates training to MethylTrainer (see run() method above)
    
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

    @timer
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


    @timer
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

    @timer
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

    @timer
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

    # NOTE: Legacy fallback method kept for backward compatibility when MethylTrainer is not available
    def _filter_and_select_dmps(self, dmp_df: pd.DataFrame) -> pd.DataFrame:
        """
        LEGACY FALLBACK: Filter and select biological DMPs.
        
        This method is kept for backward compatibility when MethylTrainer is not available.
        In normal operation, this logic has been moved to MethylTrainer.
        """
        logger.warning("Using legacy filtering method - MethylTrainer not available or failed")
        # Simplified fallback: just return top DMPs by delta_mean
        filtered = dmp_df[dmp_df['delta_mean'].abs() >= self.config.min_delta_mean]
        if len(filtered) > self.config.min_dmps_for_export:
            filtered = filtered.nlargest(self.config.min_dmps_for_export, 'delta_mean')
        
        # Save results
        chromosome = getattr(self, 'chrom', 'unknown')
        context = getattr(self, 'ctx', 'unknown')
        output_dir = Path(self.config.output_dir) if self.config.output_dir else Path.cwd()
        output_dir.mkdir(parents=True, exist_ok=True)
        self._save_single_chrom_context_results(filtered, output_dir, str(chromosome), context)
        
        return filtered

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
        # Log biological importance range (no normalization needed)
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
            "target_auc": self.config.target_auc,
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
            top_dmp_significance=top_dmp_importance,  # Note: field name kept for backward compat
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
            f"  Target AUC: {self.config.target_auc}",
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
