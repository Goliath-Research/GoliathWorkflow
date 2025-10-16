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
from typing import Dict, Any, Optional, Union


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
        
        # Optional sklearn model for fast prediction
        self._sklearn_model = None

    def predict_proba(self, X: np.ndarray,
                     availability_mask: Optional[np.ndarray] = None,
                     use_sklearn: bool = True,
                     debug: bool = False) -> np.ndarray:
        """
        Predict posterior probabilities for samples in X.

        Uses sklearn model (fast) if available and requested, otherwise uses
        Beta distribution method (slower, more accurate probabilistic inference).

        Args:
            X: Feature matrix of shape (n_samples, n_features) where n_features
               matches the number of DMPs used in training. Values should be
               methylation levels in [0, 1].
            availability_mask: Boolean mask of shape (n_samples, n_features)
                             indicating which positions are available. Only used
                             for Beta distribution method.
            use_sklearn: If True and sklearn model available, use it for prediction
            debug: If True, print debug information for the first sample.

        Returns:
            Array of shape (n_samples, 2) containing posterior probabilities
            for each class (columns 0 and 1).

        Raises:
            ValueError: If input dimensions don't match training data.
        """
        if X.shape[1] != self.n_dmps:
            raise ValueError(f"Expected {self.n_dmps} features, got {X.shape[1]}")
        
        # Use sklearn model if available and requested (much faster)
        if use_sklearn and self._sklearn_model is not None:
            return self._sklearn_model.predict_proba(X)

        n_samples = X.shape[0]
        log_likelihoods = np.zeros((n_samples, 2))  # [log P(data|centroid1), log P(data|centroid2)]

        for i in range(n_samples):
            sample = X[i, :]

            # Compute log-likelihood for each centroid
            log_like1 = 0.0
            log_like2 = 0.0
            valid_positions = 0

            if debug and i == 0:  # Debug first sample
                print(f"Debugging sample {i}:")
                available_count = np.sum(availability_mask[i]) if availability_mask is not None else self.n_dmps
                print(f"  Available positions: {available_count}/{self.n_dmps}")

            for j in range(self.n_dmps):
                # Skip if position is not available
                if availability_mask is not None and not availability_mask[i, j]:
                    continue

                methylation_val = sample[j]

                # Clamp to valid range [0,1] to avoid numerical issues
                methylation_val = np.clip(methylation_val, 1e-6, 1-1e-6)

                # Use directions to determine which Beta distribution corresponds to each class
                if self.data['directions'][j] == 1:
                    # Direction 1: class 0 = centroid1, class 1 = centroid2
                    a0, b0 = self.data['alpha1'][j], self.data['beta1'][j]  # Class 0
                    a1_class, b1_class = self.data['alpha2'][j], self.data['beta2'][j]  # Class 1
                else:
                    # Direction -1: class 0 = centroid2, class 1 = centroid1 (swapped)
                    a0, b0 = self.data['alpha2'][j], self.data['beta2'][j]  # Class 0
                    a1_class, b1_class = self.data['alpha1'][j], self.data['beta1'][j]  # Class 1

                log_p0 = beta.logpdf(methylation_val, a0, b0)
                log_p1_class = beta.logpdf(methylation_val, a1_class, b1_class)

                # Accumulate log-likelihoods
                log_like1 += log_p0        # Class 0 likelihood
                log_like2 += log_p1_class  # Class 1 likelihood

                valid_positions += 1

            if debug and i == 0:
                print(f"  Used positions: {valid_positions}")
                print(f"  Log-likelihoods: Class0={log_like1:.2f}, Class1={log_like2:.2f}")
                print(f"  Direction for position {j}: {self.data['directions'][j]}")

            # Store the log-likelihoods
            if valid_positions > 0:
                log_likelihoods[i, 0] = log_like1
                log_likelihoods[i, 1] = log_like2
            else:
                # If no positions are available, use neutral classification
                log_likelihoods[i, 0] = 0.0
                log_likelihoods[i, 1] = 0.0

        # Convert to probabilities using log-sum-exp trick for numerical stability
        # P(class|data) ∝ P(data|class) * P(class) (assuming equal priors)
        max_log_like = np.max(log_likelihoods, axis=1, keepdims=True)
        likelihood_ratios = np.exp(log_likelihoods - max_log_like)  # Avoid underflow
        posterior_probs = likelihood_ratios / np.sum(likelihood_ratios, axis=1, keepdims=True)

        if debug:
            print(f"Final probabilities: {posterior_probs[0]}")

        return posterior_probs

    def fit_sklearn_model(self, X: np.ndarray, y: np.ndarray):
        """
        Train a fast sklearn model from methylation values.
        
        This provides a faster prediction method that can be used when speed
        is more important than exact probabilistic inference. The Beta distribution
        parameters are still stored for probabilistic interpretation.
        
        Args:
            X: Methylation values (n_samples, n_dmps)
            y: Class labels (n_samples,)
        """
        from sklearn.linear_model import LogisticRegression
        self._sklearn_model = LogisticRegression(max_iter=1000, random_state=42)
        self._sklearn_model.fit(X, y)
    
    def predict(self, X: np.ndarray,
               availability_mask: Optional[np.ndarray] = None,
               use_sklearn: bool = True,
               debug: bool = False) -> np.ndarray:
        """
        Predict class labels for samples in X.
        
        Uses sklearn model (fast) if available and requested, otherwise falls back
        to Beta distribution method (slower, more accurate).

        Args:
            X: Feature matrix of shape (n_samples, n_features)
            availability_mask: Boolean mask indicating available positions (only for Beta method)
            use_sklearn: If True and sklearn model available, use it for prediction
            debug: If True, print debug information (only for Beta method)

        Returns:
            Array of class predictions (0 or 1) of shape (n_samples,)
        """
        if use_sklearn and self._sklearn_model is not None:
            return self._sklearn_model.predict(X)
        else:
            # Fall back to Beta distribution method
            probs = self.predict_proba(X, availability_mask, use_sklearn=False, debug=debug)
            return np.argmax(probs, axis=1)

    def predict_log_proba(self, X: np.ndarray,
                         availability_mask: Optional[np.ndarray] = None,
                         use_sklearn: bool = True,
                         debug: bool = False) -> np.ndarray:
        """
        Return log posterior probabilities.

        Args:
            X: Feature matrix of shape (n_samples, n_features)
            availability_mask: Boolean mask indicating available positions (only for Beta method)
            use_sklearn: If True and sklearn model available, use it for prediction
            debug: If True, print debug information

        Returns:
            Array of log posterior probabilities of shape (n_samples, 2)
        """
        probs = self.predict_proba(X, availability_mask, use_sklearn, debug)
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
