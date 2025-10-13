"""Core MethylDetector pipeline for DMP detection, filtering, and selection."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple
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
        logger.debug("Initialized MethylDetector")

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

        # Step 2: Filter and select biological DMPs (DataFrame-centric)
        logger.info("=== DMP FILTERING AND SELECTION PHASE ===")
        if self.config.apply_dmp_filtering:
            logger.info("🚀 Applying biological filters...")
            try:
                # _filter_and_select_dmps returns ONLY the selected DMPs (not all with a flag)
                biological_dmps_df = self._filter_and_select_dmps(dmp_df)
                logger.info(f"✅ Found {len(biological_dmps_df):,} biological DMPs")
            except Exception as e:
                logger.error(f"❌ DMP filtering/selection failed: {e}")
                import traceback
                traceback.print_exc()
                biological_dmps_df = pd.DataFrame()
        else:
            logger.info("⏭️ DMP filtering disabled")
            biological_dmps_df = pd.DataFrame()

        logger.debug("About to start Step 3...")
        # Step 3: Generate final results
        logger.info("Step 3: Generating final results...")
        result = self._create_final_result(
            dmp_df, biological_dmps_df=biological_dmps_df
        )
        logger.debug("Step 3 completed successfully")

        # Step 4: Build classifier model
        if not biological_dmps_df.empty and self.config.output_dir:
            logger.info("Step 4: Building classifier model...")
            output_dir = Path(self.config.output_dir)
            model_path = output_dir / f"classifier-{self.chrom}-{self.ctx}.pkl"
            
            # Build classifier data from DataFrame (matching probabilistic_beta_classifier.py interface)
            # Compute directions based on LLR moments (like in binary search)
            alpha1 = biological_dmps_df['alpha1'].values
            beta1 = biological_dmps_df['beta1'].values
            alpha2 = biological_dmps_df['alpha2'].values
            beta2 = biological_dmps_df['beta2'].values
            
            # Compute LLR moments to determine correct orientation
            da = alpha1 - alpha2
            db = beta1 - beta2
            mu1_ind, _ = compute_beta_llr_moments(alpha1, beta1, da, db, use_gpu=False)
            mu2_ind, _ = compute_beta_llr_moments(alpha2, beta2, da, db, use_gpu=False)
            
            # Direction: 1 if mu1 > mu2, else -1
            directions = np.where(mu1_ind > mu2_ind, 1, -1)
            
            # Create classifier data
            # Prepare weights - use equal weights if 'weight' column doesn't exist
            if 'weight' in biological_dmps_df.columns:
                weights = biological_dmps_df['weight'].values
            else:
                weights = np.ones(len(biological_dmps_df))
            
            classifier_data = {
                'positions': biological_dmps_df['position'].values,
                'alpha1': alpha1,
                'beta1': beta1,
                'alpha2': alpha2,
                'beta2': beta2,
                'weights': weights,
                'directions': directions
            }
            
            # Create and save classifier
            from methyl_utils import ProbabilisticBetaClassifier
            classifier = ProbabilisticBetaClassifier(classifier_data)
            
            # Package the model
            model_package = {
                'classifier': classifier,
                'data': classifier_data,
                'chromosome': self.chrom,
                'context': self.ctx,
                'n_dmps': len(biological_dmps_df),
                'config': {
                    'alpha': self.config.alpha,
                    'min_delta_mean': self.config.min_delta_mean,
                    'max_bc': self.config.max_bc,
                    'target_auc': self.config.target_auc
                }
            }
            
            # Save the trained model
            import pickle
            with open(model_path, 'wb') as f:
                pickle.dump(model_package, f)
            logger.info(f"Classifier saved to {model_path}")
            
            # Validate on synthetic samples generated from Beta distributions
            if not biological_dmps_df.empty:
                n_validation_samples = self.config.n_validation_samples  # Default 100 per class
                accuracy = self._validate_classifier_on_synthetic_samples(
                    classifier, 
                    biological_dmps_df, 
                    n_validation_samples
                )
                logger.info(f"Classifier validation on {n_validation_samples} synthetic samples per class: accuracy {accuracy * 100:.1f}%")
                result.training_accuracy = float(accuracy)
                result.classifier_model_path = str(model_path)
        
        # Step 5: Save results
        if self.config.output_dir:
            logger.info("Step 5: Saving results...")
            self._save_results(result)

        dmp_count = len(result.biologically_significant_dmps_df) if result.biologically_significant_dmps_df is not None else 0
        logger.info(
            f"Analysis complete! Found {dmp_count} DMPs"
        )
        return result

    def _validate_classifier_on_synthetic_samples(
        self, 
        classifier, 
        biological_dmps_df: pd.DataFrame, 
        n_samples: int = 100
    ) -> float:
        """
        Validate classifier on synthetic samples generated from Beta distributions.
        
        This generates random samples from the Beta distributions of both centroids
        and tests the classifier's accuracy on these synthetic samples. This is a
        proper validation that tests generalization, unlike testing on the centroids
        themselves.
        
        Args:
            classifier: Trained ProbabilisticBetaClassifier
            biological_dmps_df: DataFrame with DMP data including alpha/beta parameters
            n_samples: Number of synthetic samples to generate per class
            
        Returns:
            Accuracy (float) on synthetic samples
        """
        from scipy.stats import beta as beta_dist
        
        # Extract Beta parameters for each DMP
        alpha1 = biological_dmps_df['alpha1'].values
        beta1 = biological_dmps_df['beta1'].values
        alpha2 = biological_dmps_df['alpha2'].values
        beta2 = biological_dmps_df['beta2'].values
        
        n_dmps = len(alpha1)
        
        # Set random seed for reproducibility
        if self.config.random_state is not None:
            np.random.seed(self.config.random_state)
        
        # Generate synthetic samples for centroid 1
        samples_class0 = np.zeros((n_samples, n_dmps))
        for i in range(n_dmps):
            samples_class0[:, i] = beta_dist.rvs(alpha1[i], beta1[i], size=n_samples)
        
        # Generate synthetic samples for centroid 2
        samples_class1 = np.zeros((n_samples, n_dmps))
        for i in range(n_dmps):
            samples_class1[:, i] = beta_dist.rvs(alpha2[i], beta2[i], size=n_samples)
        
        # Combine samples
        X_val = np.vstack([samples_class0, samples_class1])
        y_true = np.array([0] * n_samples + [1] * n_samples)
        
        # Predict
        y_pred = classifier.predict(X_val)
        
        # Calculate accuracy
        accuracy = np.mean(y_pred == y_true)
        
        logger.debug(f"Validation: {n_samples} samples per class, {n_dmps} DMPs")
        logger.debug(f"  Class 0 accuracy: {np.mean(y_pred[:n_samples] == 0) * 100:.1f}%")
        logger.debug(f"  Class 1 accuracy: {np.mean(y_pred[n_samples:] == 1) * 100:.1f}%")
        
        return accuracy
    
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

    def _filter_and_select_dmps(self, dmp_df: pd.DataFrame) -> pd.DataFrame:
        """Filter and select biological DMPs on DataFrame (vectorized, GPU-aware)."""
        chromosome = getattr(self, 'chrom', 'unknown')
        context = getattr(self, 'ctx', 'unknown')
        self.df = dmp_df  # Work directly on self.df, no copy

        logger.info(f"🔬 Bio filtering for {chromosome}-{context}: starting with {len(self.df):,} significant DMPs")

        # Apply biological filters (delta_mean, bhattacharyya)
        if self.config.biological_filters:
            self._apply_biological_filters()

        # Compute effect size = |delta_mu / var_delta_mu| * (1 - BC)^gamma
        self._compute_effect_size()
        
        # Apply effect size filter if specified
        if self.config.min_effect_size is not None and len(self.df) > 0:
            before = len(self.df)
            self.df = self.df[self.df['effect_size'] >= self.config.min_effect_size]
            after = len(self.df)
            logger.info(f"  • Effect size filter (≥ {self.config.min_effect_size}): {before:,} → {after:,} DMPs ({(after/before)*100:.1f}% retained)")

        # Binary search selection to find optimal k DMPs
        if len(self.df) > 0:
            self.df = self._select_dmps_binary_search(self.df)

        logger.info(f"✅ Selected {len(self.df):,} biological DMPs for {chromosome}-{context}")

        # Save CSV
        output_dir = Path(self.config.output_dir) if self.config.output_dir else Path.cwd()
        output_dir.mkdir(parents=True, exist_ok=True)
        self._save_single_chrom_context_results(self.df, output_dir, str(chromosome), context)

        if not self.df.empty and (self.config.generate_histograms or self.config.verbose):
            self._generate_filter_histograms(self.df, chromosome, context)

        return self.df

    def _apply_biological_filters(self) -> None:
        """Apply biological filters (delta_mean and bhattacharyya) to self.df."""
        initial_count = len(self.df)
        logger.info(f"🔬 Applying biological filters to {initial_count:,} DMPs")

        # Delta mean filter: |mean1 - mean2| >= min_delta_mean
        if 'delta_mean' in self.config.biological_filters and self.config.min_delta_mean is not None:
            before = len(self.df)
            self.df = self.df[np.abs(self.df['delta_mean']) >= self.config.min_delta_mean]
            after = len(self.df)
            logger.info(f"  • Delta mean filter (≥ {self.config.min_delta_mean}): {before:,} → {after:,} DMPs ({(after/before)*100:.1f}% retained)")

        # Bhattacharyya Coefficient filter: BC <= max_bc (maximum overlap allowed)
        # BC ∈ [0,1] where 0=no overlap, 1=complete overlap
        # Lower max_bc = stricter filtering (e.g., 0.6 means "keep only DMPs with ≤60% overlap")
        if 'bhattacharyya' in self.config.biological_filters and self.config.max_bc is not None:
            if 'bhattacharyya_coefficient' not in self.df.columns:
                logger.warning("Bhattacharyya Coefficient column not found, skipping filter")
            else:
                before = len(self.df)
                self.df = self.df[self.df['bhattacharyya_coefficient'] <= self.config.max_bc]
                after = len(self.df)
                logger.info(f"  • Bhattacharyya Coefficient filter (overlap ≤ {self.config.max_bc*100:.0f}%): {before:,} → {after:,} DMPs ({(after/before)*100:.1f}% retained)")

        final_count = len(self.df)
        if initial_count > 0:
            logger.info(f"✅ Biological filtering complete: {initial_count:,} → {final_count:,} DMPs ({(final_count/initial_count)*100:.1f}% overall retention)")
        else:
            logger.warning("No DMPs to filter")

    def _compute_effect_size(self) -> None:
        """Compute variance-weighted effect size with overlap penalty on self.df.
        
        Formula: effect_size = |delta_mu / var_delta_mu| * (1 - BC)^gamma
        
        Where:
        - delta_mu = mean1 - mean2
        - var_delta_mu = sqrt(variance1^2 + variance2^2)
        - BC = Bhattacharyya Coefficient (overlap, 0-1)
        - gamma = config parameter (1.0-2.0, default 1.5)
        
        Higher effect size indicates:
        - Large standardized mean difference (confidence-weighted)
        - Low distribution overlap (good separation)
        """
        eps = self.config.eps
        gamma = self.config.gamma
        
        if 'bhattacharyya_coefficient' not in self.df.columns:
            logger.warning("Bhattacharyya Coefficient column not found, using simplified effect size")
            self.df['effect_size'] = np.abs(self.df['delta_mean'])
            return
        
        # Get positions from DataFrame
        positions = self.df['position'].values
        
        # Find indices in centroids that match these positions
        # Since centroids are aligned, positions should match directly
        idx1 = np.searchsorted(self.centroid1.pos, positions)
        idx2 = np.searchsorted(self.centroid2.pos, positions)
        
        # Get variances from centroids
        variance1 = self.centroid1.variance[idx1]
        variance2 = self.centroid2.variance[idx2]
        
        # Calculate variance of delta_mu (error propagation)
        var_delta_mu = np.sqrt(variance1**2 + variance2**2)
        
        # Standardized effect (confidence-weighted)
        delta_mu = self.df['delta_mean'].values
        standardized_effect = np.abs(delta_mu) / (var_delta_mu + eps)
        
        # Overlap penalty using BC
        bc = self.df['bhattacharyya_coefficient'].values
        overlap_penalty = (1 - bc) ** gamma
        
        # Combined effect size
        self.df['effect_size'] = standardized_effect * overlap_penalty
        
        logger.debug(f"Effect size range: {self.df['effect_size'].min():.6f} - {self.df['effect_size'].max():.6f}")
        logger.debug(f"Standardized effect range: {standardized_effect.min():.6f} - {standardized_effect.max():.6f}")
        logger.debug(f"Overlap penalty range: {overlap_penalty.min():.6f} - {overlap_penalty.max():.6f}")
        logger.debug(f"Bhattacharyya Coefficient (overlap) range: {bc.min():.6f} - {bc.max():.6f}")

    def _compute_subset_performance(self, df_subset: pd.DataFrame, use_gpu: bool = False) -> float:
        """
        Compute AUC performance metric for a subset of DMPs using LLR moments.
        Based on oldselection.py compute_subset_performance.
        
        Args:
            df_subset: DataFrame subset of DMPs to evaluate
            use_gpu: Whether to use GPU acceleration
            
        Returns:
            AUC value (0.5 to 1.0)
        """
        if len(df_subset) == 0:
            return 0.5
        
        try:
            import cupy as cp
            xp = cp if use_gpu and self.gpu_config.GPU_AVAILABLE else np
        except ImportError:
            xp = np
        
        # Extract Beta parameters
        alpha1 = xp.array(df_subset['alpha1'].values, dtype=xp.float64)
        beta1 = xp.array(df_subset['beta1'].values, dtype=xp.float64)
        alpha2 = xp.array(df_subset['alpha2'].values, dtype=xp.float64)
        beta2 = xp.array(df_subset['beta2'].values, dtype=xp.float64)
        
        # Compute LLR moments for each DMP to determine correct orientation
        da = alpha1 - alpha2
        db = beta1 - beta2
        
        mu1_ind, var1_ind = compute_beta_llr_moments(alpha1, beta1, da, db, use_gpu)
        mu2_ind, var2_ind = compute_beta_llr_moments(alpha2, beta2, da, db, use_gpu)
        
        # Ensure arrays are on the same device
        if use_gpu and self.gpu_config.GPU_AVAILABLE:
            mu1_ind = xp.asarray(mu1_ind)
            mu2_ind = xp.asarray(mu2_ind)
        
        # Determine correct orientation (higher mu = better discrimination)
        directions_from_llr = xp.where(mu1_ind > mu2_ind, 1, -1)
        
        # Handle directional flipping
        mask_flip = directions_from_llr == -1
        alpha1_flip = xp.where(mask_flip, alpha2, alpha1)
        beta1_flip = xp.where(mask_flip, beta2, beta1)
        alpha2_flip = xp.where(mask_flip, alpha1, alpha2)
        beta2_flip = xp.where(mask_flip, beta1, beta2)
        
        # Compute moments with correct orientation
        da_flip = alpha1_flip - alpha2_flip
        db_flip = beta1_flip - beta2_flip
        
        mu_d, var_d = compute_beta_llr_moments(alpha1_flip, beta1_flip, da_flip, db_flip, use_gpu)
        mu_h, var_h = compute_beta_llr_moments(alpha2_flip, beta2_flip, da_flip, db_flip, use_gpu)
        
        # Combine moments
        combined_mu_d = xp.sum(mu_d)
        combined_var_d = xp.sum(var_d)
        combined_mu_h = xp.sum(mu_h)
        combined_var_h = xp.sum(var_h)
        
        delta_mu = xp.abs(combined_mu_d - combined_mu_h)
        total_var = combined_var_d + combined_var_h
        
        # Handle numerical stability
        if total_var <= 1e-10 or not xp.isfinite(total_var):
            return 0.5
        
        d_val = delta_mu / xp.sqrt(total_var)
        d_val = xp.clip(d_val, 0, 10)
        
        # Convert to CPU for norm.cdf if using GPU
        if use_gpu and self.gpu_config.GPU_AVAILABLE:
            d_val_cpu = float(d_val.get())
        else:
            d_val_cpu = float(d_val)
        
        if not np.isfinite(d_val_cpu):
            return 0.5
        
        return norm.cdf(d_val_cpu)
        
    def _select_dmps_binary_search(self, dmp_df: pd.DataFrame) -> pd.DataFrame:
        """
        Select optimal subset of DMPs using binary search.
        Based on oldselection.py select_subset_biological_significance_threshold.
        
        Args:
            dmp_df: DataFrame of filtered DMPs with biological_importance computed
            
        Returns:
            DataFrame with top k DMPs selected
        """
        n_dmps = len(dmp_df)
        target_auc = self.config.target_auc
        min_selected = self.config.min_selected_dmps
        
        logger.info(f"🔍 Binary search DMP selection: {n_dmps} candidates, target AUC={target_auc:.3f}")
        
        if n_dmps == 0:
            return dmp_df
        
        # Sort by effect size (descending)
        sorted_df = dmp_df.sort_values('effect_size', ascending=False).reset_index(drop=True)
        
        # If min_selected_dmps is specified and we have fewer DMPs, return all
        if min_selected and n_dmps <= min_selected:
            logger.info(f"Only {n_dmps} DMPs available, less than min_selected_dmps={min_selected}, returning all")
            return sorted_df
        
        # Binary search for smallest k that achieves target AUC
        low, high = 1, n_dmps
        best_k = n_dmps  # Default to all DMPs
        
        logger.info(f"Binary search range: {low}-{high}")
        
        while low <= high:
            mid = (low + high) // 2
            test_subset = sorted_df.iloc[:mid]
            performance = self._compute_subset_performance(test_subset, use_gpu=self.config.use_gpu)
            
            logger.info(f"  Testing k={mid}: AUC={performance:.4f}")
            
            if performance >= target_auc:
                # This k achieves target - try smaller k
                best_k = mid
                high = mid - 1
            else:
                # Need larger k
                low = mid + 1
        
        # Apply min_selected_dmps constraint if specified
        if min_selected and best_k < min_selected:
            logger.info(f"Binary search found k={best_k}, but enforcing min_selected_dmps={min_selected}")
            best_k = min(min_selected, n_dmps)
        
        # Apply min_dmps_for_export constraint (ensures enough DMPs for gene mapping)
        min_export = self.config.min_dmps_for_export
        if best_k < min_export:
            logger.info(f"Binary search found k={best_k}, but enforcing min_dmps_for_export={min_export}")
            best_k = min(min_export, n_dmps)
        
        # Verify final performance
        final_subset = sorted_df.iloc[:best_k]
        final_performance = self._compute_subset_performance(final_subset, use_gpu=self.config.use_gpu)
        
        logger.info(f"✅ Binary search complete: selected k={best_k} DMPs with AUC={final_performance:.4f}")
        
        return final_subset

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
        # CSV path for single
        csv_path = output_dir / f"{prefix}.csv" if result.biologically_significant_dmps_df is not None and not result.biologically_significant_dmps_df.empty else None
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
            "Biological Importance:",
            f"  Formula: |delta_mean| / (BC + eps)",
            f"  BC = overlap coefficient (0=no overlap, 1=complete overlap)",
            f"  Higher effect size and lower overlap = higher importance",
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
    # Also add MethylUtils if available
    methyl_utils_path = package_root.parent / "MethylUtils"
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
