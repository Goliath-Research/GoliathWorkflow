"""
MethylTrainer class for training classifiers from DMP DataFrames.

This module contains the core training logic moved from MethylDetector,
including biological filtering, binary search with real sample validation,
and classifier creation.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd
import pickle

from methyl_utils import (
    compute_beta_llr_moments,
    ProbabilisticBetaClassifier,
    MethylSample,
    is_gpu_available
)
from methyl_utils.logging_utils import setup_module_logging
from scipy.stats import norm
from scipy.stats import beta  # Add this

from .config import TrainingConfig

logger = setup_module_logging(__name__)


class MethylTrainer:
    """
    Trains classifiers from DMP DataFrames with real sample validation.
    
    This class encapsulates the training logic including:
    - Biological filtering of DMPs
    - Binary search for optimal DMP selection
    - Real sample validation
    - Classifier creation and validation
    """
    
    def __init__(self, config: TrainingConfig):
        """
        Initialize MethylTrainer with configuration.
        
        Args:
            config: TrainingConfig object with all training parameters
        """
        self.config = config
        self.gpu_available = is_gpu_available()
        self.df = None  # Current working dataframe
        
        # Validation sample cache
        self._validation_samples = None
        self._validation_labels = None
        self._validation_dmp_positions = None
        
        # Accuracy evaluation cache for optimization
        self._accuracy_cache = {}
        
        np.random.seed(config.random_state)
        logger.debug("Initialized MethylTrainer")
    
    def train_from_dmps(
        self,
        dmp_df: pd.DataFrame,
        centroid1_path: Path,
        centroid2_path: Path,
        chromosome: str,
        context: str
    ) -> Dict[str, Any]:
        """
        Train classifier from filtered DMPs using binary search + validation.
        
        Args:
            dmp_df: DataFrame with statistical DMPs from centroid comparison
            centroid1_path: Path to first centroid file
            centroid2_path: Path to second centroid file
            chromosome: Chromosome identifier
            context: Context (CG, CHG, CHH)
            
        Returns:
            model_package dict with:
                - classifier: Trained ProbabilisticBetaClassifier
                - selected_dmps_df: DataFrame of selected DMPs
                - validation_accuracy: Accuracy on validation set
                - metadata: Dict with training details
        """
        self.chrom = chromosome
        self.ctx = context
        
        logger.info(f"🚀 Starting training for {chromosome}-{context}")
        logger.info(f"Input DMPs: {len(dmp_df):,}")
        
        # Step 1: Apply biological filters and select DMPs
        logger.info("=== DMP FILTERING AND SELECTION PHASE ===")
        logger.info("🚀 Applying biological filters...")
        
        try:
            biological_dmps_df = self._filter_and_select_dmps(dmp_df)
            logger.info(f"✅ Found {len(biological_dmps_df):,} biological DMPs")
        except Exception as e:
            logger.error(f"❌ DMP filtering/selection failed: {e}")
            import traceback
            traceback.print_exc()
            biological_dmps_df = pd.DataFrame()
        
        if biological_dmps_df.empty:
            logger.warning("No DMPs selected, returning empty model")
            return {
                'classifier': None,
                'selected_dmps_df': pd.DataFrame(),
                'validation_accuracy': None,
                'metadata': {
                    'chromosome': chromosome,
                    'context': context,
                    'n_dmps': 0
                }
            }
        
        # Step 2: Create classifier from selected DMPs
        logger.info("🔧 Building classifier model...")
        classifier_data, classifier = self._create_classifier(biological_dmps_df)
        
        # Step 3: Validate classifier
        accuracy = self._validate_classifier(classifier, biological_dmps_df, centroid1_path, centroid2_path)
        
        # Step 4: Package the model
        model_package = {
            'classifier': classifier,
            'data': classifier_data,
            'selected_dmps_df': biological_dmps_df,
            'validation_accuracy': accuracy,
            'chromosome': chromosome,
            'context': context,
            'n_dmps': len(biological_dmps_df),
            'threshold': getattr(self, '_cum_stats', {}).get('threshold', 0.0),
            'cum_stats': getattr(self, '_cum_stats', {}),  # Cumulative LLR statistics
            'metadata': {
                'chromosome': chromosome,
                'context': context,
                'n_dmps': len(biological_dmps_df),
                'validation_accuracy': accuracy,
                'config': {
                    'alpha': self.config.alpha,
                    'min_delta_mean': self.config.min_delta_mean,
                    'max_bc': self.config.max_bc,
                    'target_auc': self.config.target_auc,
                    'validation_mode': self.config.validation_mode
                }
            }
        }
        
        accuracy_str = f"{accuracy:.6f}" if accuracy is not None else "N/A"
        logger.info(f"✅ Training complete: {len(biological_dmps_df)} DMPs, accuracy={accuracy_str}")
        
        return model_package
    
    def _filter_and_select_dmps(self, dmp_df: pd.DataFrame) -> pd.DataFrame:
        """Filter and select biological DMPs on DataFrame (vectorized, GPU-aware)."""
        self.df = dmp_df.copy()  # Work on a copy
        
        logger.info(f"🔬 Bio filtering for {self.chrom}-{self.ctx}: starting with {len(self.df):,} significant DMPs")
        
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
        
        logger.info(f"✅ Selected {len(self.df):,} biological DMPs for {self.chrom}-{self.ctx}")
        
        return self.df
    
    def _apply_biological_filters(self) -> None:
        """Apply biological filters (delta_mean and bhattacharyya) to self.df."""
        initial_count = len(self.df)
        logger.info(f"🔬 Applying biological filters to {initial_count:,} DMPs")
        
        # Filter 1: Delta mean
        before = len(self.df)
        self.df = self.df[self.df['delta_mean'].abs() >= self.config.min_delta_mean]
        after = len(self.df)
        logger.info(f"  • Delta mean filter (≥ {self.config.min_delta_mean}): {before:,} → {after:,} DMPs ({(after/before)*100:.1f}% retained)")
        
        # Filter 2: Bhattacharyya Coefficient (overlap)
        if 'bhattacharyya_coefficient' in self.df.columns:
            before = len(self.df)
            self.df = self.df[self.df['bhattacharyya_coefficient'] <= self.config.max_bc]
            after = len(self.df)
            logger.info(f"  • Bhattacharyya Coefficient filter (overlap ≤ {self.config.max_bc*100:.0f}%): {before:,} → {after:,} DMPs ({(after/before)*100:.1f}% retained)")
        
        logger.info(f"✅ Biological filtering complete: {initial_count:,} → {len(self.df):,} DMPs ({(len(self.df)/initial_count)*100:.1f}% overall retention)")
    
    def _compute_effect_size(self) -> None:
        """
        Compute variance-weighted, overlap-penalized effect size.
        
        Effect Size Formula:
            effect_size = |delta_mu| / sqrt(var1² + var2²) * (1 - BC)^gamma
        
        Where:
            - delta_mu: Difference in log-likelihood ratio means between centroids
            - var1, var2: Variance of LLR distributions for each centroid
            - BC: Bhattacharyya Coefficient (distribution overlap, 0=distinct, 1=identical)
            - gamma: Overlap penalty exponent (default 1.5)
        
        This is NOT simply |delta_mean| / (BC + eps), but a more sophisticated metric that:
            1. Weights by statistical confidence (variance of LLR distributions)
            2. Penalizes overlapping distributions with (1-BC)^gamma
            3. Uses log-likelihood ratio moments for proper probabilistic interpretation
        
        Higher effect_size values indicate DMPs with:
            - Large mean methylation differences
            - Low variance (high confidence)
            - Minimal distribution overlap
        """
        if len(self.df) == 0:
            return
        
        # Extract Beta parameters
        alpha1 = self.df['alpha1'].values
        beta1 = self.df['beta1'].values
        alpha2 = self.df['alpha2'].values
        beta2 = self.df['beta2'].values
        
        # Compute LLR moments for variance-weighted effect size
        # This uses the log-likelihood ratio distributions, not simple delta_mean
        da = alpha1 - alpha2
        db = beta1 - beta2
        mu_d, var_d = compute_beta_llr_moments(alpha1, beta1, da, db, use_gpu=self.config.use_gpu)
        mu_h, var_h = compute_beta_llr_moments(alpha2, beta2, da, db, use_gpu=self.config.use_gpu)
        
        # Standardized effect: |delta_mu| / sqrt(total_variance)
        # This is analogous to Cohen's d but for LLR distributions
        delta_mu = np.abs(mu_d - mu_h)
        total_var = var_d + var_h
        
        # Handle zero variance (numerical stability)
        total_var = np.where(total_var > 1e-10, total_var, 1e-10)
        standardized_effect = delta_mu / np.sqrt(total_var)
        
        # Get Bhattacharyya coefficient (distribution overlap)
        if 'bhattacharyya_coefficient' in self.df.columns:
            bc = self.df['bhattacharyya_coefficient'].values
        else:
            bc = np.ones(len(self.df)) * 0.5
        
        # Apply overlap penalty: (1 - BC)^gamma
        # This heavily penalizes DMPs with overlapping distributions
        overlap_penalty = np.power(1.0 - bc, self.config.gamma)
        
        # Final effect size = standardized_effect * overlap_penalty
        self.df['effect_size'] = standardized_effect * overlap_penalty
        
        logger.debug(f"Effect size range: {self.df['effect_size'].min():.6f} - {self.df['effect_size'].max():.6f}")
    
    def _select_dmps_binary_search(self, dmp_df: pd.DataFrame) -> pd.DataFrame:
        """
        Select optimal subset of DMPs using binary search.
        
        Args:
            dmp_df: DataFrame of filtered DMPs with effect_size computed
            
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
        
        # Load validation samples once if available (for real AUC computation during binary search)
        self._validation_samples = None
        self._validation_labels = None
        self._validation_dmp_positions = None
        
        if (self.config.validation_mode == "real" and 
            (self.config.centroid1_validation_samples or self.config.centroid2_validation_samples)):
            logger.info("📊 Loading validation samples for binary search...")
            samples_data = self._load_validation_samples_for_binary_search(sorted_df)
            if samples_data is not None:
                self._validation_samples, self._validation_labels, self._validation_dmp_positions = samples_data
                logger.info(f"✅ Loaded {len(self._validation_samples)} validation samples with {len(self._validation_dmp_positions)} positions")
        
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
            
            logger.info(f"  Testing k={mid}: AUC={performance:.6f}")
            
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
        
        # Apply min_dmps_for_export: export max(selected_k, min_dmps_for_export)
        # This ensures we export at least min_dmps_for_export, but more if binary search selected more
        min_export = self.config.min_dmps_for_export
        original_k = best_k
        desired_k = max(best_k, min_export)
        best_k = min(desired_k, n_dmps)  # Cap at available DMPs
        
        if best_k != original_k:
            if best_k < min_export:
                logger.info(f"Binary search selected k={original_k}, desired k={desired_k} (min_dmps_for_export={min_export}), but only {n_dmps} DMPs available → exporting k={best_k}")
            else:
                logger.info(f"Binary search selected k={original_k}, exporting k={best_k} (max of selected and min_dmps_for_export={min_export})")
        
        # Verify final performance
        final_subset = sorted_df.iloc[:best_k]
        final_performance = self._compute_subset_performance(final_subset, use_gpu=self.config.use_gpu)
        
        logger.info(f"✅ Binary search complete: selected k={best_k} DMPs with AUC={final_performance:.6f}")
        
        # Optional: optimize for validation accuracy (requires real samples)
        if (self.config.optimize_for_validation_accuracy and 
            self.config.validation_mode == "real" and
            self._validation_samples is not None):
            
            logger.info(f"🎯 Starting validation-accuracy optimization from k={best_k}...")
            optimized_k = self._optimize_for_validation_accuracy(sorted_df, start_k=best_k)
            
            if optimized_k != best_k:
                logger.info(f"📈 Validation optimization: k={best_k} → k={optimized_k}")
                best_k = optimized_k
                final_subset = sorted_df.iloc[:best_k]
            else:
                logger.info(f"📊 Validation optimization: k={best_k} is already optimal")
        
        return final_subset
    
    def _compute_subset_performance(self, df_subset: pd.DataFrame, use_gpu: bool = True) -> float:
        """
        Compute performance metric (AUC) for a subset of DMPs.
        
        Uses real samples if available (faster, more accurate), otherwise theoretical Beta moments.
        """
        # Use real AUC if validation samples are loaded
        if self._validation_samples is not None:
            return self._compute_real_auc_from_samples(df_subset)
        
        # Fall back to theoretical Beta distribution AUC
        return self._compute_theoretical_auc(df_subset, use_gpu)
    
    def _compute_theoretical_auc(self, df_subset: pd.DataFrame, use_gpu: bool = True) -> float:
        """Compute theoretical AUC based on Beta distribution moments."""
        if len(df_subset) == 0:
            return 0.5
        
        # Extract Beta parameters
        alpha1 = df_subset['alpha1'].values
        beta1 = df_subset['beta1'].values
        alpha2 = df_subset['alpha2'].values
        beta2 = df_subset['beta2'].values
        
        # Use GPU if available
        gpu_enabled = use_gpu and self.gpu_available
        if gpu_enabled:
            try:
                import cupy as cp
                xp = cp
                alpha1 = cp.asarray(alpha1)
                beta1 = cp.asarray(beta1)
                alpha2 = cp.asarray(alpha2)
                beta2 = cp.asarray(beta2)
            except ImportError:
                xp = np
                gpu_enabled = False
        else:
            xp = np
        
        # Compute LLR moments
        da = alpha1 - alpha2
        db = beta1 - beta2
        mu_d, var_d = compute_beta_llr_moments(alpha1, beta1, da, db, use_gpu=gpu_enabled)
        mu_h, var_h = compute_beta_llr_moments(alpha2, beta2, da, db, use_gpu=gpu_enabled)
        
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
        if gpu_enabled:
            d_val_cpu = float(d_val.get())
        else:
            d_val_cpu = float(d_val)
        
        if not np.isfinite(d_val_cpu):
            return 0.5
        
        return norm.cdf(d_val_cpu)
    
    def _compute_real_auc_from_samples(self, df_subset: pd.DataFrame) -> float:
        """
        Compute real AUC using pre-loaded validation samples with Beta classifier.
        
        Args:
            df_subset: Subset of DMPs to evaluate
            
        Returns:
            AUC value
        """
        try:
            
            # Get positions for this subset
            subset_positions = df_subset['position'].values
            
            # Find indices of subset positions in the full validation data
            position_indices = np.isin(self._validation_dmp_positions, subset_positions)
            
            if not np.any(position_indices):
                return 0.5
            
            # Extract features for this subset
            X = self._validation_samples[:, position_indices]
            y = self._validation_labels
            
            # Extract Beta parameters for temporary classifier
            alpha1 = df_subset['alpha1'].values
            beta1 = df_subset['beta1'].values
            alpha2 = df_subset['alpha2'].values
            beta2 = df_subset['beta2'].values
            
            # Compute llr_const on the fly
            from scipy.special import betaln
            llr_const = -(betaln(alpha1, beta1) - betaln(alpha2, beta2))
            
            # Create temporary classifier data
            classifier_data = {
                'positions': subset_positions,
                'alpha1': alpha1,
                'beta1': beta1,
                'alpha2': alpha2,
                'beta2': beta2,
                'llr_const': llr_const,
                'directions': np.ones(len(alpha1))
            }
            
            # Create temporary Beta classifier
            temp_classifier = ProbabilisticBetaClassifier(classifier_data)
            
            # Get probability predictions (column 1 = class 1 probability)
            y_pred_proba = temp_classifier.predict_proba(X, debug=False)
            y_pred = y_pred_proba[:, 1]
            
            # Compute AUC manually without sklearn
            # Sort by predicted probability
            sorted_indices = np.argsort(y_pred)[::-1]
            y_sorted = y[sorted_indices]
            
            # Count positives and negatives
            n_pos = np.sum(y_sorted == 1)
            n_neg = np.sum(y_sorted == 0)
            
            if n_pos == 0 or n_neg == 0:
                return 0.5
            
            # Calculate AUC using trapezoidal rule
            tp = 0
            fp = 0
            auc = 0.0
            
            for label in y_sorted:
                if label == 1:
                    tp += 1
                else:
                    fp += 1
                    auc += tp
            
            auc = auc / (n_pos * n_neg)
            
            return auc
            
        except Exception as e:
            logger.debug(f"Failed to compute real AUC: {e}")
            return 0.5
    
    def _optimize_for_validation_accuracy(self, sorted_df: pd.DataFrame, start_k: int) -> int:
        """
        Optimize DMP count for maximum validation accuracy using Differential Evolution.
        
        Handles multimodal accuracy functions by using global optimization.
        Strategy: Find maximum accuracy globally, then find minimum k achieving it.
        
        Args:
            sorted_df: Sorted DataFrame of DMPs (descending by effect size)
            start_k: Starting k value (from AUC binary search)
            
        Returns:
            Minimum k that achieves maximum validation accuracy
        """
        from scipy.optimize import differential_evolution
        
        n_dmps = len(sorted_df)
        # Use the number of biological DMPs as max_k
        max_k = n_dmps
        
        # Ensure max_k is at least as large as start_k
        max_k = max(max_k, start_k)
        
        logger.info(f"  Configuration: start_k={start_k}, max_k={max_k}")
        
        # If start_k equals max_k, no optimization needed
        if start_k >= max_k:
            logger.info(f"  ⚠️ start_k ({start_k}) >= max_k ({max_k}), skipping optimization")
            return start_k
        
        # Clear accuracy cache at start of optimization
        self._accuracy_cache.clear()
        
        # Phase 1: Find maximum achievable accuracy using Differential Evolution
        logger.info(f"  🎯 Phase 1: Finding maximum accuracy using Differential Evolution...")
        
        def objective_function(k_float):
            """Objective function for DE: minimize negative accuracy = maximize accuracy"""
            # Handle both scalar and array inputs
            if hasattr(k_float, '__len__') and len(k_float) > 1:
                # If array, take first element
                k_float = k_float[0]
            
            k = int(round(float(k_float)))
            k = max(start_k, min(k, max_k))  # Ensure k is within bounds
            
            test_subset = sorted_df.iloc[:k]
            accuracy = self._compute_validation_accuracy(test_subset)
            
            # Return negative accuracy (minimize = maximize)
            return -accuracy
        
        # Run Differential Evolution
        bounds = [(start_k, max_k)]
        result = differential_evolution(
            objective_function,
            bounds,
            maxiter=self.config.de_max_iterations,
            popsize=self.config.de_population_size,
            tol=self.config.de_tolerance,
            seed=self.config.random_state,
            strategy='best1bin'
        )
        
        # Extract results
        k_max = int(round(result.x[0]))
        accuracy_max = -result.fun  # Convert back from negative
        
        logger.info(f"  ✅ DE found maximum accuracy {accuracy_max:.6f} at k={k_max}")
        logger.info(f"  📊 DE converged: {result.success}, iterations: {result.nit}, evaluations: {result.nfev}")
        
        # Phase 2: Find minimum k that achieves maximum accuracy
        logger.info(f"  🔍 Phase 2: Finding minimum k that achieves {accuracy_max:.6f}...")
        
        # Use binary search to find minimum k achieving the maximum accuracy
        # Allow small tolerance to prefer smaller k values
        target_accuracy = accuracy_max - self.config.de_tolerance
        
        optimal_k = self._binary_search_for_accuracy(sorted_df, start_k, k_max, target_accuracy)
        
        # Verify final result
        final_subset = sorted_df.iloc[:optimal_k]
        final_accuracy = self._compute_validation_accuracy(final_subset)
        
        logger.info(f"  🏆 Final optimal: k={optimal_k} achieves accuracy={final_accuracy:.6f}")
        
        return optimal_k
    
    def _binary_search_for_accuracy(self, sorted_df: pd.DataFrame, k_low: int, k_high: int, target_accuracy: float) -> int:
        """
        Binary search to find the minimum k that achieves target_accuracy.
        Also tracks if we find even better accuracy during search.
        
        Args:
            sorted_df: Sorted DataFrame of DMPs
            k_low: Lower bound for search
            k_high: Upper bound for search (known to achieve target_accuracy)
            target_accuracy: Target accuracy to achieve
            
        Returns:
            Minimum k that achieves best accuracy found
        """
        best_k = k_high  # Default to the known good value
        best_accuracy = target_accuracy
        
        # Binary search for the smallest k that achieves target_accuracy
        low, high = k_low, k_high
        
        while low < high:
            mid = (low + high) // 2
            test_subset = sorted_df.iloc[:mid]
            accuracy = self._compute_validation_accuracy(test_subset)
            
            logger.info(f"    k={mid}: accuracy={accuracy:.6f}")
            
            # Track if we find better accuracy
            if accuracy > best_accuracy:
                best_accuracy = accuracy
                logger.info(f"    ✨ Found better accuracy: {best_accuracy:.6f}")
            
            if accuracy >= target_accuracy:
                # This k achieves target - try smaller k
                best_k = mid
                high = mid
            else:
                # Need larger k
                low = mid + 1
        
        logger.info(f"  ✅ Binary search complete: minimum k={best_k} achieves {best_accuracy:.6f}")
        
        # If we found better accuracy, re-search for minimum k achieving it
        if best_accuracy > target_accuracy:
            logger.info(f"  🔄 Re-searching for minimum k that achieves improved accuracy {best_accuracy:.6f}...")
            return self._binary_search_for_accuracy(sorted_df, k_low, k_high, best_accuracy)
        
        return best_k
    
    def _compute_validation_accuracy(self, df_subset: pd.DataFrame) -> float:
        """
        Compute classification accuracy on validation samples using Beta classifier.
        
        Args:
            df_subset: DataFrame subset with DMP parameters
            
        Returns:
            Accuracy score [0, 1]
        """
        # Create cache key based on subset positions
        subset_positions = df_subset['position'].values
        cache_key = tuple(sorted(subset_positions))
        
        # Check cache first
        if cache_key in self._accuracy_cache:
            logger.debug(f"Using cached accuracy for {len(subset_positions)} DMPs")
            return self._accuracy_cache[cache_key]
        
        try:
            # Find indices in validation data
            position_indices = np.isin(self._validation_dmp_positions, subset_positions)
            
            if not np.any(position_indices):
                logger.debug(f"No matching positions found for validation")
                accuracy = 0.0
                self._accuracy_cache[cache_key] = accuracy
                return accuracy
            
            # Extract features
            X = self._validation_samples[:, position_indices]
            y_true = self._validation_labels
            
            # Extract Beta parameters
            alpha1 = df_subset['alpha1'].values
            beta1 = df_subset['beta1'].values
            alpha2 = df_subset['alpha2'].values
            beta2 = df_subset['beta2'].values
            
            # Compute llr_const on the fly (same logic as in _create_classifier)
            from scipy.special import betaln
            llr_const = -(betaln(alpha1, beta1) - betaln(alpha2, beta2))
            
            # Create temporary classifier data
            classifier_data = {
                'positions': subset_positions,
                'alpha1': alpha1,
                'beta1': beta1,
                'alpha2': alpha2,
                'beta2': beta2,
                'llr_const': llr_const,
                'directions': np.ones(len(alpha1))  # Default directions
            }
            
            # Create classifier
            classifier = ProbabilisticBetaClassifier(classifier_data)
            
            # Predict
            proba = classifier.predict_proba(X, debug=False)
            y_pred = np.argmax(proba, axis=1)
            
            # Compute accuracy
            accuracy = np.mean(y_pred == y_true)
            
            # Cache the result
            self._accuracy_cache[cache_key] = accuracy
            
            return accuracy
            
        except Exception as e:
            logger.warning(f"Failed to compute validation accuracy: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            accuracy = 0.0
            self._accuracy_cache[cache_key] = accuracy
            return accuracy
    
    def _load_validation_samples_for_binary_search(self, dmp_df: pd.DataFrame) -> Optional[tuple]:
        """
        Load validation samples once before binary search.
        
        Args:
            dmp_df: DataFrame with all candidate DMPs
            
        Returns:
            Tuple of (samples_array, labels_array, dmp_positions) or None if loading fails
        """
        try:
            # Get sample paths from both centroids
            centroid1_samples = self.config.centroid1_validation_samples or []
            centroid2_samples = self.config.centroid2_validation_samples or []
            
            sample_paths_1 = self._get_validation_sample_paths(
                self.config.centroid1_path, 
                centroid1_samples if isinstance(centroid1_samples, list) else []
            )
            sample_paths_2 = self._get_validation_sample_paths(
                self.config.centroid2_path,
                centroid2_samples if isinstance(centroid2_samples, list) else []
            )
            
            if not sample_paths_1 or not sample_paths_2:
                logger.warning("No validation samples available for binary search")
                return None
            
            # Extract DMP positions
            dmp_positions = dmp_df['position'].values
            
            logger.info(f"Loading {len(sample_paths_1)} samples from centroid 1 at {len(dmp_positions)} positions")
            logger.info(f"Loading {len(sample_paths_2)} samples from centroid 2 at {len(dmp_positions)} positions")
            
            # Load all samples
            samples_list = []
            labels_list = []
            
            # Load class 0 samples (centroid 1)
            for sample_path in sample_paths_1:
                sample_values = self._load_sample_methylation_at_dmps(
                    sample_path, self.chrom, self.ctx, dmp_positions
                )
                if sample_values is not None:
                    samples_list.append(sample_values)
                    labels_list.append(0)
            
            # Load class 1 samples (centroid 2)
            for sample_path in sample_paths_2:
                sample_values = self._load_sample_methylation_at_dmps(
                    sample_path, self.chrom, self.ctx, dmp_positions
                )
                if sample_values is not None:
                    samples_list.append(sample_values)
                    labels_list.append(1)
            
            if len(samples_list) < 4:  # Need at least 2 samples per class
                logger.warning(f"Too few samples loaded ({len(samples_list)}), need at least 4")
                return None
            
            # Stack into arrays
            samples_array = np.vstack(samples_list)  # Shape: (n_samples, n_positions)
            labels_array = np.array(labels_list)
            
            logger.info(f"✅ Loaded validation data: {samples_array.shape[0]} samples × {samples_array.shape[1]} positions")
            
            return (samples_array, labels_array, dmp_positions)
            
        except Exception as e:
            logger.warning(f"Failed to load validation samples for binary search: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _load_sample_methylation_at_dmps(
        self,
        sample_dir: Union[str, Path],
        chrom: str,
        ctx: str,
        dmp_positions: np.ndarray
    ) -> Optional[np.ndarray]:
        """
        Load methylation values from a sample at specific DMP positions.
        
        Args:
            sample_dir: Directory containing the sample HDF5 file
            chrom: Chromosome identifier
            ctx: Context (CG, CHG, CHH)
            dmp_positions: Array of genomic positions to extract
            
        Returns:
            Array of methylation levels (mC/(mC+uC)) at DMP positions, or None if failed
        """
        sample_path = Path(sample_dir) / f"{chrom}-{ctx}.h5"
        
        if not sample_path.exists():
            logger.warning(f"Sample file not found: {sample_path}")
            return None
        
        try:
            # Load sample
            sample = MethylSample.load_from_h5(sample_path)
            
            # Find matching positions (DMP positions that exist in this sample)
            # Use numpy's searchsorted for efficient lookup
            sample_pos_idx = np.searchsorted(sample.pos, dmp_positions)
            
            # Verify positions actually match (handle out of bounds)
            # IMPORTANT: Check bounds BEFORE accessing sample.pos with the indices
            valid_mask = (sample_pos_idx < len(sample.pos))
            
            # For valid indices, check if positions actually match
            if np.any(valid_mask):
                # Only access sample.pos for valid indices
                valid_sample_pos_idx = sample_pos_idx[valid_mask]
                position_match = sample.pos[valid_sample_pos_idx] == dmp_positions[valid_mask]
                
                # Update valid_mask to include only matching positions
                temp_mask = np.zeros(len(dmp_positions), dtype=bool)
                temp_mask[valid_mask] = position_match
                valid_mask = temp_mask
            
            # Extract methylation values
            methyl_values = np.full(len(dmp_positions), np.nan, dtype=np.float32)
            
            if np.any(valid_mask):
                valid_indices = sample_pos_idx[valid_mask]
                mC = sample.mC[valid_indices].astype(np.float32)
                uC = sample.uC[valid_indices].astype(np.float32)
                
                # Calculate methylation levels with safe division
                total = mC + uC
                with np.errstate(divide='ignore', invalid='ignore'):
                    methyl_values[valid_mask] = np.where(total > 0, mC / total, 0.0)
            
            # Replace NaNs with 0.0 for positions not in sample
            methyl_values = np.nan_to_num(methyl_values, nan=0.0)
            
            return methyl_values
            
        except Exception as e:
            logger.warning(f"Error loading sample {sample_path}: {e}")
            return None
    
    def _get_validation_sample_paths(self, centroid_path: Union[str, Path], config_samples) -> List[str]:
        """
        Get validation sample paths from config or centroid metadata.
        
        Args:
            centroid_path: Path to the centroid file
            config_samples: Sample specification from config (can be "use_metadata" or list of paths)
            
        Returns:
            List of sample directory paths
        """
        # If config specifies sample paths, use them
        if config_samples and config_samples != "use_metadata":
            if isinstance(config_samples, list):
                return config_samples
            elif isinstance(config_samples, str):
                return [config_samples]
        
        # Otherwise, try to read from centroid metadata
        try:
            centroid_path = Path(centroid_path)
            centroid = MethylSample.load_from_h5(centroid_path)
            if hasattr(centroid, 'metadata') and centroid.metadata:
                # Try new metadata fields first
                if 'samples_used' in centroid.metadata and centroid.metadata['samples_used']:
                    return centroid.metadata['samples_used']
                # Fall back to old 'samples' field
                elif 'samples' in centroid.metadata and centroid.metadata['samples']:
                    return centroid.metadata['samples']
        except Exception as e:
            logger.warning(f"Could not read metadata from {centroid_path}: {e}")
        
        return []
    
    def _create_classifier(self, biological_dmps_df: pd.DataFrame) -> tuple:
        """
        Create classifier from selected DMPs with improved algorithm support.
        
        Returns:
            Tuple of (classifier_data dict, ProbabilisticBetaClassifier)
        """
        from scipy.special import betaln
        
        # Extract Beta parameters
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
        
        # Prepare weights - use equal weights if 'weight' column doesn't exist
        if 'weight' in biological_dmps_df.columns:
            weights = biological_dmps_df['weight'].values
        else:
            weights = np.ones(len(biological_dmps_df))
        
        # Compute LLR constants (betaln differences) for threshold-based classification
        # Direct assignment: centroid1=class0, centroid2=class1
        llr_const = -(betaln(alpha1, beta1) - betaln(alpha2, beta2))
        
        classifier_data = {
            'positions': biological_dmps_df['position'].values,
            'alpha1': alpha1,
            'beta1': beta1,
            'alpha2': alpha2,
            'beta2': beta2,
            'weights': weights,
            'directions': directions,
            'llr_const': llr_const  # Add LLR constants for improved algorithm
        }
        
        # Create classifier
        classifier = ProbabilisticBetaClassifier(classifier_data)

        # NOTE: Directions calibration removed - following copilot.py approach
        # Direct centroid1=class0, centroid2=class1 assignment without per-position flipping
        
        return classifier_data, classifier
    
    def _calibrate_directions(self, classifier, classifier_data):
        """Calibrate directions by checking sample alignments. Returns possibly updated classifier."""
        # Get positions
        positions = classifier_data['positions']
        
        # Find matching indices in validation data
        position_indices = np.isin(self._validation_dmp_positions, positions)
        if not np.any(position_indices):
            logger.warning("No matching positions for calibration")
            return classifier # Return the original classifier if no match
        
        X_val = self._validation_samples[:, position_indices]
        
        # Split by class
        class0_mask = self._validation_labels == 0
        class1_mask = self._validation_labels == 1
        
        x_class0 = X_val[class0_mask]
        x_class1 = X_val[class1_mask]
        
        if len(x_class0) == 0 or len(x_class1) == 0:
            logger.warning("Insufficient samples for calibration")
            return classifier # Return the original classifier if insufficient samples
        
        # Per-position calibration (vectorized)
        n_dmps = X_val.shape[1]
        directions = classifier_data['directions'].copy()

        # Broadcast params
        a0 = np.where(directions == 1, classifier.data['alpha1'], classifier.data['alpha2'])[np.newaxis, :]
        b0 = np.where(directions == 1, classifier.data['beta1'], classifier.data['beta2'])[np.newaxis, :]
        a1 = np.where(directions == 1, classifier.data['alpha2'], classifier.data['alpha1'])[np.newaxis, :]
        b1 = np.where(directions == 1, classifier.data['beta2'], classifier.data['beta1'])[np.newaxis, :]

        # Validate params per position
        valid1 = (classifier.data['alpha1'] > 0) & (classifier.data['beta1'] > 0) & np.isfinite(classifier.data['alpha1']) & np.isfinite(classifier.data['beta1'])
        valid2 = (classifier.data['alpha2'] > 0) & (classifier.data['beta2'] > 0) & np.isfinite(classifier.data['alpha2']) & np.isfinite(classifier.data['beta2'])
        valid = valid1 & valid2

        # Mask invalid in logpdf (use nan for nanmean)
        log_p0_class0 = np.where(valid[np.newaxis, :], beta.logpdf(x_class0, a0, b0), np.nan)
        log_p1_class0 = np.where(valid[np.newaxis, :], beta.logpdf(x_class0, a1, b1), np.nan)
        log_p0_class1 = np.where(valid[np.newaxis, :], beta.logpdf(x_class1, a0, b0), np.nan)
        log_p1_class1 = np.where(valid[np.newaxis, :], beta.logpdf(x_class1, a1, b1), np.nan)

        # Use np.nanmean to ignore nans
        correct_current_class0 = np.nanmean(log_p0_class0, axis=0)
        correct_current_class1 = np.nanmean(log_p1_class1, axis=0)
        avg_correct_current = np.nanmean([correct_current_class0, correct_current_class1], axis=0)  # Per position

        correct_flipped_class0 = np.nanmean(log_p1_class0, axis=0)
        correct_flipped_class1 = np.nanmean(log_p0_class1, axis=0)
        avg_correct_flipped = np.nanmean([correct_flipped_class0, correct_flipped_class1], axis=0)

        # Flip where flipped better and valid
        flip_mask = (avg_correct_flipped > avg_correct_current) & valid
        directions[flip_mask] = -directions[flip_mask]
        flipped_better_count = np.sum(flip_mask)

        if flipped_better_count > 0:
            improvement = avg_correct_flipped[flip_mask] - avg_correct_current[flip_mask]
            avg_improvement = np.mean(improvement)
            logger.info(f"Per-position calibration: flipped {flipped_better_count}/{n_dmps} ({flipped_better_count/n_dmps*100:.1f}%), avg improvement {avg_improvement:.3f}")
            classifier_data['directions'] = directions
            classifier = ProbabilisticBetaClassifier(classifier_data)
        else:
            logger.info("Per-position calibration: no flips needed")

        return classifier

    def _validate_classifier(
        self, 
        classifier, 
        biological_dmps_df: pd.DataFrame,
        centroid1_path: Path,
        centroid2_path: Path
    ) -> Optional[float]:
        """
        Validate the trained classifier.
        
        Returns:
            Accuracy on validation set, or None if validation fails
        """
        # Check if we already validated during binary search
        if (hasattr(self, '_validation_samples') and 
            self._validation_samples is not None and 
            self.config.validation_mode == "real"):
            logger.info("✅ Validation already performed during binary search with real samples")
            # Compute accuracy with the selected DMPs
            selected_positions = biological_dmps_df['position'].values
            position_indices = np.isin(self._validation_dmp_positions, selected_positions)
            
            if np.any(position_indices):
                X_val = self._validation_samples[:, position_indices]
                y_val = self._validation_labels
                logger.info(f"🔄 Predicting on {X_val.shape[0]} samples × {X_val.shape[1]} DMPs...")
                proba = classifier.predict_proba(X_val)
                y_pred = np.argmax(proba, axis=1)
                accuracy = np.mean(y_pred == y_val)
                
                logger.info(f"Classifier validation: accuracy {accuracy*100:.1f}%")
                return accuracy
        
        # Perform validation based on mode
        if self.config.validation_mode == "real":
            return self._validate_on_real_samples(classifier, biological_dmps_df, centroid1_path, centroid2_path)
        else:
            return self._validate_on_synthetic_samples(classifier, biological_dmps_df)
    
    def _validate_on_synthetic_samples(
        self, 
        classifier, 
        biological_dmps_df: pd.DataFrame
    ) -> float:
        """Validate classifier on synthetic samples generated from Beta distributions."""
        from scipy.stats import beta as beta_dist
        
        n_samples = self.config.n_validation_samples
        
        # Extract Beta parameters for each DMP
        alpha1 = biological_dmps_df['alpha1'].values
        beta1 = biological_dmps_df['beta1'].values
        alpha2 = biological_dmps_df['alpha2'].values
        beta2 = biological_dmps_df['beta2'].values
        
        n_dmps = len(alpha1)
        
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
        
        logger.info(f"Validation on {n_samples} synthetic samples per class: accuracy {accuracy*100:.1f}%")
        
        return accuracy
    
    def _validate_on_real_samples(
        self, 
        classifier, 
        biological_dmps_df: pd.DataFrame,
        centroid1_path: Path,
        centroid2_path: Path
    ) -> float:
        """Validate classifier on real samples from the centroids."""
        logger.info("Validating classifier on real samples...")
        
        # Get validation sample paths
        sample_paths_1 = self._get_validation_sample_paths(centroid1_path, 
                                                           self.config.centroid1_validation_samples)
        sample_paths_2 = self._get_validation_sample_paths(centroid2_path,
                                                           self.config.centroid2_validation_samples)
        
        if not sample_paths_1 or not sample_paths_2:
            logger.warning("No validation samples available, falling back to synthetic validation")
            return self._validate_on_synthetic_samples(classifier, biological_dmps_df)
        
        logger.info(f"Loading {len(sample_paths_1)} samples from centroid 1")
        logger.info(f"Loading {len(sample_paths_2)} samples from centroid 2")
        
        # Extract DMP positions
        dmp_positions = biological_dmps_df['position'].values
        
        # Load methylation values for class 0 (centroid 1 samples)
        samples_class0_data = []
        for sample_path in sample_paths_1:
            try:
                sample_values = self._load_sample_methylation_at_dmps(
                    sample_path, self.chrom, self.ctx, dmp_positions
                )
                if sample_values is not None:
                    samples_class0_data.append(sample_values)
            except Exception as e:
                logger.warning(f"Failed to load sample {sample_path}: {e}")
        
        # Load methylation values for class 1 (centroid 2 samples)
        samples_class1_data = []
        for sample_path in sample_paths_2:
            try:
                sample_values = self._load_sample_methylation_at_dmps(
                    sample_path, self.chrom, self.ctx, dmp_positions
                )
                if sample_values is not None:
                    samples_class1_data.append(sample_values)
            except Exception as e:
                logger.warning(f"Failed to load sample {sample_path}: {e}")
        
        if len(samples_class0_data) == 0 or len(samples_class1_data) == 0:
            logger.warning("Failed to load sufficient samples, falling back to synthetic validation")
            return self._validate_on_synthetic_samples(classifier, biological_dmps_df)
        
        # Stack samples
        X_val_class0 = np.vstack(samples_class0_data)
        X_val_class1 = np.vstack(samples_class1_data)
        X_val = np.vstack([X_val_class0, X_val_class1])
        
        # Create labels: centroid1 samples → 0, centroid2 samples → 1
        y_true = np.array([0] * len(X_val_class0) + [1] * len(X_val_class1))

        # Predict
        proba = classifier.predict_proba(X_val, debug=False)
        y_pred = np.argmax(proba, axis=1)
        accuracy = np.mean(y_pred == y_true)
        
        # Debug: show predictions vs truth for first 10 samples
        print("\n" + "="*60)
        print("DEBUG: First 10 predictions vs truth:")
        for i in range(min(10, len(y_pred))):
            print(f"  Sample {i}: pred={y_pred[i]}, true={y_true[i]}, P(0)={proba[i,0]:.3f}, P(1)={proba[i,1]:.3f}")
        print("="*60 + "\n")
        
        logger.info(f"Classifier validation on real samples: accuracy {accuracy*100:.1f}%")
        
        return accuracy

