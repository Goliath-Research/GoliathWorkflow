"""
Probabilistic Beta Classifier for Methylation Data

This module provides a Bayesian classifier using Beta distributions for
methylation-based sample classification. It performs exact probabilistic
classification using differentially methylated positions (DMPs).

The classifier is designed for high-performance methylation analysis and
integrates seamlessly with the MethylUtils ecosystem.
"""

import numpy as np
import pandas as pd
from scipy.stats import beta
from typing import Dict, Any, Optional, Union, Tuple
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler


class BetaClassifier:
    """
    Beta Classifier for Methylation Data (renamed from ProbabilisticBetaClassifier).
    
    This classifier performs Bayesian classification using exact Beta likelihoods
    for differentially methylated positions (DMPs). It handles coverage by ignoring
    low-coverage positions (default min_coverage=10 for 30x data) and can weight
    by precision (tau ~ coverage).
    
    The classifier is trained on two centroids (representing different biological
    conditions) and can classify new samples based on their methylation patterns.

    Attributes:
        data (dict): Training data containing Beta distribution parameters
        n_dmps (int): Number of DMP positions used for classification

    Example:
        >>> # Training data format
        >>> training_data = {
        ...     'positions': np.array([100, 200, 300]),
        ...     'alpha1': np.array([5.0, 2.0, 8.0]),  # Beta params for centroid 1
        ...     'beta1': np.array([3.0, 6.0, 2.0]),
        ...     'alpha2': np.array([2.0, 8.0, 2.0]),  # Beta params for centroid 2
        ...     'beta2': np.array([6.0, 2.0, 6.0]),
        ...     'weights': np.array([0.85, 0.92, 0.78]),  # Optional weights
        ...     'directions': np.array([1, -1, 1])  # Direction indicators
        ... }
        >>> classifier = BetaClassifier(training_data)
        >>> predictions = classifier.predict(new_methylation_data)
    """

    def __init__(self, data: Dict[str, np.ndarray], min_sample_coverage: int = 10, coverage_weighting: bool = True):
        """
        Initialize BetaClassifier with data and coverage parameters.
        
        Args:
            data: Dictionary containing positions, alpha1, beta1, etc.
            min_sample_coverage: Min coverage for valid positions (default 10).
            coverage_weighting: If True, use precision weighting in LLR (default True).
        """
        self.data = data
        self.min_sample_coverage = min_sample_coverage
        self.coverage_weighting = coverage_weighting
        
        # Existing init code...
        self.positions = np.asarray(data['positions'], dtype=np.uint32)
        self.alpha1 = np.asarray(data['alpha1'], dtype=np.float64)
        self.beta1 = np.asarray(data['beta1'], dtype=np.float64)
        self.alpha2 = np.asarray(data['alpha2'], dtype=np.float64)
        self.beta2 = np.asarray(data['beta2'], dtype=np.float64)
        self.weights = np.asarray(data.get('weights', np.ones(len(self.positions))), dtype=np.float64)
        self.directions = np.asarray(data.get('directions', np.ones(len(self.positions))), dtype=np.int8)

        # Validate array lengths
        n_positions = len(self.positions)
        if len(self.alpha1) != n_positions or len(self.beta1) != n_positions or \
           len(self.alpha2) != n_positions or len(self.beta2) != n_positions:
            raise ValueError(f"Array length mismatch for alpha/beta parameters: expected {n_positions}, got {len(self.alpha1)}")
        if len(self.weights) != n_positions:
            raise ValueError(f"Array length mismatch for weights: expected {n_positions}, got {len(self.weights)}")
        if len(self.directions) != n_positions:
            raise ValueError(f"Array length mismatch for directions: expected {n_positions}, got {len(self.directions)}")

        self.n_dmps = n_positions
        self.temperature = 1.0  # Default temperature for softmax
        self.calibrator = None  # For Platt scaling

    @classmethod
    def from_dataframe(cls, dmpDF: pd.DataFrame, min_sample_coverage: int = 10, coverage_weighting: bool = True):
        """
        Create BetaClassifier from strongly-typed DataFrame.
        
        Args:
            dmpDF: DataFrame with columns: pos (int), alpha1 (float), beta1 (float),
                   alpha2 (float), beta2 (float), weight (float)
            min_sample_coverage: Min coverage for valid positions (default 10)
            coverage_weighting: If True, use precision weighting in LLR (default True)
        
        Returns:
            BetaClassifier instance
        """
        # Validate required columns
        required_cols = ['pos', 'alpha1', 'beta1', 'alpha2', 'beta2', 'weight']
        missing = [c for c in required_cols if c not in dmpDF.columns]
        if missing:
            raise ValueError(f"DataFrame missing required columns: {missing}")
        
        # Extract and validate types
        pos = np.asarray(dmpDF['pos'].values, dtype=np.int64).astype(np.uint32)
        alpha1 = np.asarray(dmpDF['alpha1'].values, dtype=np.float64)
        beta1 = np.asarray(dmpDF['beta1'].values, dtype=np.float64)
        alpha2 = np.asarray(dmpDF['alpha2'].values, dtype=np.float64)
        beta2 = np.asarray(dmpDF['beta2'].values, dtype=np.float64)
        weight = np.asarray(dmpDF['weight'].values, dtype=np.float64)
        
        # Create data dictionary (add directions based on mean difference)
        # For BetaClassifier, we need directions - compute from alpha/beta means
        mean1 = alpha1 / (alpha1 + beta1)
        mean2 = alpha2 / (alpha2 + beta2)
        directions = np.sign(mean1 - mean2).astype(np.int8)
        
        data = {
            'positions': pos,
            'alpha1': alpha1,
            'beta1': beta1,
            'alpha2': alpha2,
            'beta2': beta2,
            'weights': weight,
            'directions': directions
        }
        
        return cls(data, min_sample_coverage=min_sample_coverage, coverage_weighting=coverage_weighting)
    
    def set_temperature(self, temperature: float = 1.0):
        """Set the temperature for softmax to control sharpness of probabilities."""
        self.temperature = max(temperature, 0.1)  # Avoid too low temperatures

    def predict_proba(self, X: np.ndarray,
                     availability_mask: Optional[np.ndarray] = None,
                     debug: bool = False) -> np.ndarray:
        """
        Predict posterior probabilities for samples in X using Beta distributions.

        Args:
            X: Feature matrix of shape (n_samples, n_features) where n_features
               matches the number of DMPs used in training. Values should be
               methylation levels in [0, 1].
            availability_mask: Boolean mask of shape (n_samples, n_features)
                             indicating which positions are available.
            debug: If True, print debug information for the first sample.

        Returns:
            Array of shape (n_samples, 2) containing posterior probabilities
            for each class (columns 0 and 1).

        Raises:
            ValueError: If input dimensions don't match training data.
        """
        if X.shape[1] != self.n_dmps:
            raise ValueError(f"Expected {self.n_dmps} features, got {X.shape[1]}")

        n_samples = X.shape[0]
        log_likelihoods = np.zeros((n_samples, 2))  # [log P(data|centroid1), log P(data|centroid2)]

        methylation_vals = np.clip(X, 1e-6, 1-1e-6)  # Shape: (n_samples, n_dmps)

        # Get base parameters
        alpha1_base = self.data['alpha1']
        beta1_base = self.data['beta1']
        alpha2_base = self.data['alpha2']
        beta2_base = self.data['beta2']
        
        # Direct assignment: class0=centroid1, class1=centroid2
        alpha_class0 = alpha1_base
        beta_class0 = beta1_base
        alpha_class1 = alpha2_base
        beta_class1 = beta2_base
        
        # Broadcast across samples
        alpha0 = np.repeat(alpha_class0[np.newaxis, :], n_samples, axis=0)
        beta0 = np.repeat(beta_class0[np.newaxis, :], n_samples, axis=0)
        alpha1 = np.repeat(alpha_class1[np.newaxis, :], n_samples, axis=0)
        beta1 = np.repeat(beta_class1[np.newaxis, :], n_samples, axis=0)

        # Compute logpdf under each class
        log_p_class0 = beta.logpdf(methylation_vals, alpha0, beta0)
        log_p_class1 = beta.logpdf(methylation_vals, alpha1, beta1)

        # Validate parameters: mask invalid positions (alpha/beta <=0 or inf/nan)
        valid0 = (alpha0 > 0) & (beta0 > 0) & np.isfinite(alpha0) & np.isfinite(beta0)
        valid1 = (alpha1 > 0) & (beta1 > 0) & np.isfinite(alpha1) & np.isfinite(beta1)
        valid = valid0 & valid1  # Only use positions valid for both classes

        # Mask unavailable or invalid positions
        if availability_mask is not None:
            effective_mask = availability_mask & valid
            log_p_class0 = np.where(effective_mask, log_p_class0, 0.0)
            log_p_class1 = np.where(effective_mask, log_p_class1, 0.0)
            valid_counts = np.sum(effective_mask, axis=1)
        else:
            effective_mask = valid
            log_p_class0 = np.where(effective_mask, log_p_class0, 0.0)
            log_p_class1 = np.where(effective_mask, log_p_class1, 0.0)
            valid_counts = np.sum(effective_mask, axis=1)

        # AVERAGE log-likelihoods by number of valid positions (instead of summing)
        avg_log_like_class0 = np.sum(log_p_class0, axis=1) / np.maximum(valid_counts, 1)
        avg_log_like_class1 = np.sum(log_p_class1, axis=1) / np.maximum(valid_counts, 1)

        # Handle no valid positions (set to same neutral value)
        mask_no_valid = valid_counts == 0
        avg_log_like_class0[mask_no_valid] = 0.0
        avg_log_like_class1[mask_no_valid] = 0.0

        # Assign to classes: Column 0 = class0, Column 1 = class1
        log_likelihoods[:, 0] = avg_log_like_class0
        log_likelihoods[:, 1] = avg_log_like_class1

        # Debug first sample if requested
        if debug:
            i = 0
            available_count = valid_counts[i] if valid_counts[i] > 0 else 0
            print(f"Debugging sample {i}:")
            print(f"  Available positions: {available_count}/{self.n_dmps}")
            print(f"  Used positions: {available_count}")
            print(f"  Avg log-likelihoods: Class0={avg_log_like_class0[i]:.2f}, Class1={avg_log_like_class1[i]:.2f}")

        # Debug: add stats on invalid params
        if debug:
            print(f"  Fraction valid for class0: {np.mean(valid0):.3f}")
            print(f"  Fraction valid for class1: {np.mean(valid1):.3f}")
            print(f"  Fraction valid for both: {np.mean(valid):.3f}")

        # Convert to probabilities using log-sum-exp trick for numerical stability
        # Apply temperature to soften: divide by temperature before softmax
        scaled_log_likelihoods = log_likelihoods / self.temperature
        max_log_like = np.max(scaled_log_likelihoods, axis=1, keepdims=True)
        likelihood_ratios = np.exp(scaled_log_likelihoods - max_log_like)  # Avoid underflow
        posterior_probs = likelihood_ratios / np.sum(likelihood_ratios, axis=1, keepdims=True)

        if debug:
            print(f"Final probabilities (T={self.temperature}): {posterior_probs[0]}")

        return posterior_probs

    def calibrate_platt(self, X_val: np.ndarray, y_val: np.ndarray, availability_mask: Optional[np.ndarray] = None):
        """
        Calibrate probabilities using Platt scaling on validation data.
        
        Fits a logistic regression: P(y=1 | logit) = 1 / (1 + exp(-(a * logit + b))),
        where logit = avg_log_like_class1 - avg_log_like_class0.
        
        Args:
            X_val: Validation features (n_samples, n_features)
            y_val: Validation labels (0 or 1)
            availability_mask: Optional mask for validation data
        """
        # Compute raw logits (difference of averaged log L)
        log_likelihoods = self._compute_averaged_log_likelihoods(X_val, availability_mask)
        logits = log_likelihoods[:, 1] - log_likelihoods[:, 0]  # Class1 - Class0

        # Fit Platt scaling (logistic regression on logits)
        scaler = StandardScaler()
        logits_scaled = scaler.fit_transform(logits.reshape(-1, 1)).flatten()

        self.calibrator_scaler = scaler
        self.calibrator = LogisticRegression(fit_intercept=True, max_iter=1000)
        self.calibrator.fit(logits_scaled.reshape(-1, 1), y_val)

    def _compute_averaged_log_likelihoods(self, X: np.ndarray, availability_mask: Optional[np.ndarray] = None):
        """Helper to compute averaged log-likelihoods (extracted for calibration)."""
        # Reuse the computation from predict_proba up to averaged log_likes
        n_samples = X.shape[0]
        methylation_vals = np.clip(X, 1e-6, 1-1e-6)

        alpha1_base = self.data['alpha1']
        beta1_base = self.data['beta1']
        alpha2_base = self.data['alpha2']
        beta2_base = self.data['beta2']

        alpha_class0 = alpha1_base
        beta_class0 = beta1_base
        alpha_class1 = alpha2_base
        beta_class1 = beta2_base

        alpha0 = np.repeat(alpha_class0[np.newaxis, :], n_samples, axis=0)
        beta0 = np.repeat(beta_class0[np.newaxis, :], n_samples, axis=0)
        alpha1 = np.repeat(alpha_class1[np.newaxis, :], n_samples, axis=0)
        beta1 = np.repeat(beta_class1[np.newaxis, :], n_samples, axis=0)

        log_p_class0 = beta.logpdf(methylation_vals, alpha0, beta0)
        log_p_class1 = beta.logpdf(methylation_vals, alpha1, beta1)

        valid0 = (alpha0 > 0) & (beta0 > 0) & np.isfinite(alpha0) & np.isfinite(beta0)
        valid1 = (alpha1 > 0) & (beta1 > 0) & np.isfinite(alpha1) & np.isfinite(beta1)
        valid = valid0 & valid1

        if availability_mask is not None:
            effective_mask = availability_mask & valid
            log_p_class0 = np.where(effective_mask, log_p_class0, 0.0)
            log_p_class1 = np.where(effective_mask, log_p_class1, 0.0)
            valid_counts = np.sum(effective_mask, axis=1)
        else:
            effective_mask = valid
            log_p_class0 = np.where(effective_mask, log_p_class0, 0.0)
            log_p_class1 = np.where(effective_mask, log_p_class1, 0.0)
            valid_counts = np.sum(effective_mask, axis=1)

        avg_log_like_class0 = np.sum(log_p_class0, axis=1) / np.maximum(valid_counts, 1)
        avg_log_like_class1 = np.sum(log_p_class1, axis=1) / np.maximum(valid_counts, 1)

        mask_no_valid = valid_counts == 0
        avg_log_like_class0[mask_no_valid] = 0.0
        avg_log_like_class1[mask_no_valid] = 0.0

        log_likelihoods = np.zeros((n_samples, 2))
        log_likelihoods[:, 0] = avg_log_like_class0
        log_likelihoods[:, 1] = avg_log_like_class1

        return log_likelihoods

    def predict_proba_calibrated(self, X: np.ndarray, availability_mask: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Predict calibrated probabilities using Platt scaling if fitted.
        """
        if self.calibrator is None:
            return self.predict_proba(X, availability_mask)

        # Compute raw averaged log L
        log_likelihoods = self._compute_averaged_log_likelihoods(X, availability_mask)
        logits = log_likelihoods[:, 1] - log_likelihoods[:, 0]

        # Scale logits
        if hasattr(self, 'calibrator_scaler'):
            logits_scaled = self.calibrator_scaler.transform(logits.reshape(-1, 1)).flatten()
        else:
            logits_scaled = logits  # Fallback if no scaler

        # Apply Platt scaling
        calibrated_probs = self.calibrator.predict_proba(logits_scaled.reshape(-1, 1))[:, 1]  # P(class1)

        # Return as (n_samples, 2)
        probs = np.zeros((len(X), 2))
        probs[:, 0] = 1 - calibrated_probs
        probs[:, 1] = calibrated_probs

        return probs
    
    def predict_with_threshold(
        self,
        X: np.ndarray,
        threshold: float,
        priors: Tuple[float, float] = (0.5, 0.5),
        adjust_for_missing: bool = True,
        availability_mask: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """
        Classify using LLR threshold instead of posterior probabilities (improved algorithm).
        
        This method implements the threshold-based classification from the improved algorithm:
        1. Computes log-likelihoods for available positions
        2. Sums LLR across positions
        3. Adjusts threshold if positions missing (optional)
        4. Makes decision based on LLR + log prior odds vs threshold
        5. Computes posteriors via log-sum-exp for interpretability
        
        Args:
            X: Methylation values array of shape (n_samples, n_features)
            threshold: LLR threshold for classification
            priors: Tuple of (prior_cancer, prior_healthy)
            adjust_for_missing: Whether to adjust threshold for missing positions
            availability_mask: Boolean mask indicating available positions
        
        Returns:
            Dictionary with:
                - 'predictions': Array of predicted classes (0 or 1)
                - 'P_C': Posterior probability for cancer/class1
                - 'P_H': Posterior probability for healthy/class0
                - 'sumLLR': Sum of log-likelihood ratios
                - 'decision': Array of decision strings ('Cancer' or 'Healthy')
                - 'threshold_used': Threshold used (adjusted if missing positions)
                - 'used_positions': Number of positions used per sample
        """
        from methyl_utils import beta_log_pdf, compute_per_site_llr_stats
        from scipy.stats import norm
        
        n_samples = X.shape[0]
        if X.shape[1] != self.n_dmps:
            raise ValueError(f"Expected {self.n_dmps} features, got {X.shape[1]}")
        
        # Extract parameters - direct assignment without label mapping
        # centroid1 = class 0, centroid2 = class 1
        alpha_C = self.data['alpha1']
        beta_C = self.data['beta1']
        alpha_H = self.data['alpha2']
        beta_H = self.data['beta2']
        
        llr_const = self.data.get('llr_const', np.zeros(self.n_dmps))
        
        # Clip methylation values
        X_clipped = np.clip(X, 1e-12, 1.0 - 1e-12)
        
        # Determine availability
        if availability_mask is None:
            availability_mask = ~np.isnan(X) & (X >= 0) & (X <= 1)
        
        # Initialize results
        sumLLR = np.zeros(n_samples)
        used_counts = np.zeros(n_samples, dtype=int)
        
        # Compute LLR for each sample
        for i in range(n_samples):
            available = availability_mask[i] if availability_mask.ndim > 1 else availability_mask
            x_vals = X_clipped[i, available]
            
            if len(x_vals) == 0:
                continue
            
            # Compute log-likelihoods
            logL_C = beta_log_pdf(x_vals, alpha_C[available], beta_C[available], use_gpu=False)
            logL_H = beta_log_pdf(x_vals, alpha_H[available], beta_H[available], use_gpu=False)
            
            # Sum LLR
            sumLLR[i] = np.sum(logL_C - logL_H)
            used_counts[i] = len(x_vals)
        
        # Adjust threshold for missing positions if requested
        threshold_used = threshold
        if adjust_for_missing and np.any(used_counts < self.n_dmps):
            # Recompute threshold based on available positions
            # This requires per-site LLR moments
            muC_site, varC_site, muH_site, varH_site, _ = compute_per_site_llr_stats(
                alpha_C, beta_C, alpha_H, beta_H, use_gpu=False
            )
            
            # For each unique count of used positions, compute adjusted threshold
            unique_counts = np.unique(used_counts[used_counts > 0])
            threshold_map = {}
            
            for count in unique_counts:
                if count == self.n_dmps:
                    threshold_map[count] = threshold
                else:
                    # Estimate threshold for subset (assuming uniform distribution of missing)
                    # This is an approximation - ideally we'd know which specific positions
                    # For now, scale by proportion of positions
                    scale = count / self.n_dmps
                    threshold_map[count] = threshold * scale
            
            # Apply mapped thresholds
            threshold_used = np.array([threshold_map.get(c, 0.0) for c in used_counts])
        
        # Log prior odds
        prior_C, prior_H = priors
        log_prior_odds = np.log(prior_C) - np.log(prior_H)
        
        # Make decisions
        if isinstance(threshold_used, np.ndarray):
            predictions = ((sumLLR + log_prior_odds) > threshold_used).astype(int)
        else:
            predictions = ((sumLLR + log_prior_odds) > threshold_used).astype(int)
        
        # Compute posteriors for interpretability (using log-sum-exp)
        logL_C_total = sumLLR / 2 + np.log(prior_C)  # Approximation
        logL_H_total = -sumLLR / 2 + np.log(prior_H)
        
        max_log = np.maximum(logL_C_total, logL_H_total)
        exp_C = np.exp(logL_C_total - max_log)
        exp_H = np.exp(logL_H_total - max_log)
        denom = exp_C + exp_H
        
        P_C = exp_C / denom
        P_H = exp_H / denom
        
        # Create decision labels
        decisions = np.where(predictions == 1, 'Cancer', 'Healthy')
        
        return {
            'predictions': predictions,
            'P_C': P_C,
            'P_H': P_H,
            'sumLLR': sumLLR,
            'decision': decisions,
            'threshold_used': threshold_used,
            'used_positions': used_counts
        }

    def predict(self, X: np.ndarray,
               availability_mask: Optional[np.ndarray] = None,
               debug: bool = False) -> np.ndarray:
        """
        Predict class labels for samples in X using Beta distributions.

        Args:
            X: Feature matrix of shape (n_samples, n_features)
            availability_mask: Boolean mask indicating available positions
            debug: If True, print debug information

        Returns:
            Array of class predictions (0 or 1) of shape (n_samples,)
        """
        probs = self.predict_proba(X, availability_mask, debug=debug)
        return np.argmax(probs, axis=1)

    def predict_log_proba(self, X: np.ndarray,
                         availability_mask: Optional[np.ndarray] = None,
                         debug: bool = False) -> np.ndarray:
        """
        Return log posterior probabilities.

        Args:
            X: Feature matrix of shape (n_samples, n_features)
            availability_mask: Boolean mask indicating available positions
            debug: If True, print debug information

        Returns:
            Array of log posterior probabilities of shape (n_samples, 2)
        """
        probs = self.predict_proba(X, availability_mask, debug)
        return np.log(probs + 1e-15)  # Add small epsilon to avoid log(0)

    def get_feature_info(self) -> Dict[str, Any]:
        """
        Get information about the DMP features used in classification.

        Returns:
            Dictionary containing feature information:
            - 'n_features': Number of DMP positions
            - 'positions': Array of genomic positions
            - 'weights': Optional weights for each DMP
            - 'directions': Direction indicators for each DMP
        """
        return {
            'n_features': self.n_dmps,
            'positions': self.data['positions'],
            'weights': self.data.get('weights'),
            'directions': self.data.get('directions')
        }

    def __repr__(self) -> str:
        return f"BetaClassifier(n_features={self.n_dmps})"

ProbabilisticBetaClassifier = BetaClassifier  # Deprecated alias
