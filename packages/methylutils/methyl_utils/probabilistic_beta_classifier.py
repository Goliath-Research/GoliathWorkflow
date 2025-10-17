"""
Probabilistic Beta Classifier for Methylation Data

This module provides a Bayesian classifier using Beta distributions for
methylation-based sample classification. It performs exact probabilistic
classification using differentially methylated positions (DMPs).

The classifier is designed for high-performance methylation analysis and
integrates seamlessly with the MethylUtils ecosystem.
"""

import numpy as np
from scipy.stats import beta
from typing import Dict, Any, Optional, Union, Tuple


class ProbabilisticBetaClassifier:
    """
    Probabilistic classifier using Beta distributions for methylation data.

    This classifier performs Bayesian classification using exact Beta likelihoods
    for differentially methylated positions (DMPs). It can handle missing data
    and provides probabilistic predictions.

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
        >>> classifier = ProbabilisticBetaClassifier(training_data)
        >>> predictions = classifier.predict(new_methylation_data)
    """

    def __init__(self, data: Dict[str, np.ndarray]):
        """
        Initialize the classifier with training data.

        Args:
            data: Dictionary containing training data with the following keys:
                - 'positions': Array of genomic positions
                - 'alpha1', 'beta1': Beta parameters for centroid 1
                - 'alpha2', 'beta2': Beta parameters for centroid 2
                - 'weights': Optional weights for each DMP (default: None)
                - 'directions': Direction indicators (1 or -1) for each DMP

        Raises:
            ValueError: If required data keys are missing or arrays have mismatched lengths
        """
        required_keys = ['positions', 'alpha1', 'beta1', 'alpha2', 'beta2']
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Missing required data key: {key}")

        # Validate array lengths
        n_positions = len(data['positions'])
        for key in ['alpha1', 'beta1', 'alpha2', 'beta2']:
            if len(data[key]) != n_positions:
                raise ValueError(f"Array length mismatch for {key}: expected {n_positions}, got {len(data[key])}")

        self.data = data
        self.n_dmps = n_positions

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

        # Get base parameters (should now be bounded from methyl_centroid_pair.py)
        # Following copilot.py: NO DIRECTIONS - directly assign centroid1=class0, centroid2=class1
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

        log_like_class0 = np.sum(log_p_class0, axis=1)
        log_like_class1 = np.sum(log_p_class1, axis=1)

        # DO NOT AVERAGE - copilot.py sums log-likelihoods
        # Handle no valid positions (set to same neutral value)
        mask_no_valid = valid_counts == 0
        log_like_class0[mask_no_valid] = 0.0
        log_like_class1[mask_no_valid] = 0.0

        # Assign to classes: Column 0 = class0, Column 1 = class1
        log_likelihoods[:, 0] = log_like_class0
        log_likelihoods[:, 1] = log_like_class1

        # Debug first sample if requested
        if debug:
            i = 0
            available_count = valid_counts[i] if valid_counts[i] > 0 else 0
            print(f"Debugging sample {i}:")
            print(f"  Available positions: {available_count}/{self.n_dmps}")
            print(f"  Used positions: {available_count}")
            print(f"  Log-likelihoods: Class0={log_like_class0[i]:.2f}, Class1={log_like_class1[i]:.2f}")

        # Debug: add stats on invalid params
        if debug:
            print(f"  Fraction valid for class0: {np.mean(valid0):.3f}")
            print(f"  Fraction valid for class1: {np.mean(valid1):.3f}")
            print(f"  Fraction valid for both: {np.mean(valid):.3f}")

        # Convert to probabilities using log-sum-exp trick for numerical stability
        # P(class|data) ∝ P(data|class) * P(class) (assuming equal priors)
        max_log_like = np.max(log_likelihoods, axis=1, keepdims=True)
        likelihood_ratios = np.exp(log_likelihoods - max_log_like)  # Avoid underflow
        posterior_probs = likelihood_ratios / np.sum(likelihood_ratios, axis=1, keepdims=True)

        if debug:
            print(f"Final probabilities: {posterior_probs[0]}")

        return posterior_probs
    
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
        
        # Extract parameters - assign based on centroid labels if available
        centroid1_label = self.data.get('centroid1_label', 'cancer').lower()
        
        if centroid1_label == 'cancer':
            # centroid1 is cancer, centroid2 is healthy
            alpha_C = self.data['alpha1']
            beta_C = self.data['beta1']
            alpha_H = self.data['alpha2']
            beta_H = self.data['beta2']
        else:
            # centroid1 is healthy, centroid2 is cancer
            alpha_C = self.data['alpha2']
            beta_C = self.data['beta2']
            alpha_H = self.data['alpha1']
            beta_H = self.data['beta1']
        
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
        return f"ProbabilisticBetaClassifier(n_features={self.n_dmps})"


# Convenience function for creating classifier from common data formats
def create_classifier_from_results(dmp_results: list,
                                 centroid1_data: Dict[str, np.ndarray],
                                 centroid2_data: Dict[str, np.ndarray]) -> ProbabilisticBetaClassifier:
    """
    Create a ProbabilisticBetaClassifier from DMP analysis results.

    This is a convenience function for integrating with methylation analysis pipelines.

    Args:
        dmp_results: List of DMP result objects with attributes like position, alpha1, beta1, etc.
        centroid1_data: Dictionary with centroid 1 Beta parameters
        centroid2_data: Dictionary with centroid 2 Beta parameters

    Returns:
        Trained ProbabilisticBetaClassifier
    """
    classifier_data = {
        'positions': np.array([r.position for r in dmp_results]),
        'alpha1': np.array([r.alpha1 for r in dmp_results]),
        'beta1': np.array([r.beta1 for r in dmp_results]),
        'alpha2': np.array([r.alpha2 for r in dmp_results]),
        'beta2': np.array([r.beta2 for r in dmp_results]),
        'weights': np.array([getattr(r, 'auc_score', 0.5) for r in dmp_results]),
        'directions': np.array([1 if r.mean1 > r.mean2 else -1 for r in dmp_results])
    }

    return ProbabilisticBetaClassifier(classifier_data)
