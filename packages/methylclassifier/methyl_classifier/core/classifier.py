"""
Core classification functionality for MethylClassifier
"""

import pickle
import sys
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import numpy as np

# Module mapping for pickle compatibility
import importlib

# Import from parent package
from methyl_utils import ProbabilisticBetaClassifier
from ..models.config import ClassifierConfig

# Create a mapping for old module names to new ones
MODULE_MAPPING = {
    'methyl_detector': 'methyl_utils',
    'methyl_detector.classifiers': 'methyl_utils.probabilistic_beta_classifier',
    'methyl_detector.classifiers.classifier': 'methyl_utils.probabilistic_beta_classifier',
    'methyl_detector.probabilistic_beta_classifier': 'methyl_utils.probabilistic_beta_classifier',
    'methyl_detector.methyl_sample': 'methyl_utils.methyl_sample',
    'methyl_utils.classifiers': 'methyl_utils.probabilistic_beta_classifier',
    'methyl_utils.classifiers.probabilistic_beta_classifier': 'methyl_utils.probabilistic_beta_classifier',
    # Handle numpy version compatibility issues
    'numpy._core': 'numpy.core',
    'numpy._core.multiarray': 'numpy.core.multiarray',
    'numpy._core.numeric': 'numpy.core.numeric',
    'numpy._core.umath': 'numpy.core.umath',
}


class CustomUnpickler(pickle.Unpickler):
    """Custom unpickler that maps old module names to new ones."""

    def find_class(self, module, name):
        # Map old module names to new ones
        if module in MODULE_MAPPING:
            module = MODULE_MAPPING[module]

        # Handle nested module mappings
        for old_module, new_module in MODULE_MAPPING.items():
            if module.startswith(old_module + '.'):
                module = module.replace(old_module, new_module, 1)
                break

        return super().find_class(module, name)


class MethylClassifier:
    """
    Main classifier class for methylation-based sample classification.

    This class provides methods to load trained classifiers and classify
    methylation samples using Bayesian probabilistic approaches.

    Supports both binary and multi-class classification scenarios.
    """

    def __init__(self, config: ClassifierConfig):
        self.config = config
        self.classifier = ProbabilisticBetaClassifier.load(self.config.model_path)  # Assume load method
        self.classifier.set_temperature(self.config.temperature)
        self.chromosome = None
        self.context = None
        self.n_classes = None
        self.class_names = None
        self.metadata = {}

    def load_classifier(self, model_path: Path) -> None:
        """
        Load a trained classifier from a pickle file.
        
        Handles both old format (raw ProbabilisticBetaClassifier) and
        new enhanced format (dict with classifier + metadata).

        Args:
            model_path: Path to the classifier pickle file
        """
        try:
            with open(model_path, 'rb') as f:
                # Use custom unpickler to handle module mapping
                model_package = CustomUnpickler(f).load()
            
            # Handle both old and new formats
            if isinstance(model_package, dict) and 'classifier' in model_package:
                # New enhanced PKL format
                print(f"✅ Loaded enhanced model package (v{model_package.get('package_version', 'unknown')})")
                self.classifier = model_package['classifier']
                # Note: comparison_config removed (no longer used), kept for backward compatibility
                self.metadata = model_package.get('metadata', {})
                
                # Extract metadata
                self.chromosome = self.metadata.get('chromosome', 'unknown')
                self.context = self.metadata.get('context', 'unknown')
                self.n_classes = 2  # Binary classifier
                self.class_names = [
                    self.metadata.get('centroid1_name', 'centroid1'),
                    self.metadata.get('centroid2_name', 'centroid2')
                ]
                
                # Display metadata
                print(f"📍 Classifier context: {self.chromosome}-{self.context}")
                print(f"📊 Training date: {self.metadata.get('training_date', 'unknown')}")
                print(f"📊 Classifier uses {self.metadata.get('n_dmps', 'unknown')} DMPs")
                print(f"📊 Class names: {self.class_names[0]} vs {self.class_names[1]}")
                
                # Display validation results if available
                if 'validation' in self.metadata:
                    val = self.metadata['validation']
                    print(f"✅ Validation accuracy: {val.get('overall_accuracy', 0):.1%}")
                    
                # Load pre-fitted calibrator if available
                if 'platt_calibrator' in self.metadata and self.config.enable_platt_calibration:
                    import pickle
                    self.classifier.calibrator = pickle.loads(self.metadata['platt_calibrator'])
                    self._calibrated = True
                    print("Loaded pre-fitted Platt calibrator from model metadata")
                else:
                    self._calibrated = False

            else:
                # Old format: raw ProbabilisticBetaClassifier
                print(f"✅ Loaded classifier (legacy format)")
                self.classifier = model_package
                
                # Try to extract chromosome and context from filename
                try:
                    self.chromosome, self.context = extract_chrom_context_from_classifier(model_path)
                    print(f"📋 Classifier trained on chromosome {self.chromosome}, context {self.context}")
                except ValueError as e:
                    print(f"⚠️ Could not extract chromosome/context: {e}")

                # Extract classifier metadata
                self._extract_classifier_metadata()

        except Exception as e:
            print(f"❌ Failed to load classifier from {model_path}: {e}")
            sys.exit(1)

    def _extract_classifier_metadata(self) -> None:
        """Extract metadata about the classifier (number of classes, etc.)."""
        try:
            # Try to get number of classes from the classifier
            if hasattr(self.classifier, 'n_classes'):
                self.n_classes = self.classifier.n_classes
            elif hasattr(self.classifier, 'classes_'):
                self.n_classes = len(self.classifier.classes_)
                self.class_names = self.classifier.classes_
            else:
                # Fallback: try to infer from predict_proba on dummy data
                try:
                    dummy_data = np.zeros((1, self.get_feature_info()['n_features']))
                    probas = self.classifier.predict_proba(dummy_data)
                    self.n_classes = probas.shape[1]
                except:
                    self.n_classes = 2  # Default assumption

            print(f"📊 Classifier supports {self.n_classes} classes")

            if self.class_names is not None:
                print(f"📋 Class names: {list(self.class_names)}")

        except Exception as e:
            print(f"⚠️ Could not extract classifier metadata: {e}")
            self.n_classes = 2  # Default fallback

    def get_feature_info(self) -> Dict[str, Any]:
        """Get information about the classifier's features."""
        if self.classifier is None:
            raise RuntimeError("No classifier loaded")

        return self.classifier.get_feature_info()
    
    def predict(self, methylation_data: np.ndarray,
                availability_mask: Optional[np.ndarray] = None,
                debug: bool = False) -> np.ndarray:
        """
        Predict classes for methylation data using Beta distributions.

        Args:
            methylation_data: Array of methylation values
            availability_mask: Boolean mask indicating available positions
            debug: Enable debug output

        Returns:
            Array of class predictions
        """
        if self.classifier is None:
            raise RuntimeError("No classifier loaded")

        return self.classifier.predict(methylation_data, availability_mask, debug)

    def predict_proba(self, methylation_data: np.ndarray,
                     availability_mask: Optional[np.ndarray] = None,
                     debug: bool = False) -> np.ndarray:
        """
        Predict class probabilities for methylation data using Beta distributions.

        Args:
            methylation_data: Array of methylation values
            availability_mask: Boolean mask indicating available positions
            debug: Enable debug output

        Returns:
            Array of class probabilities
        """
        if self.classifier is None:
            raise RuntimeError("No classifier loaded")

        if hasattr(self, '_calibrated') and self._calibrated:
            return self.classifier.predict_proba_calibrated(methylation_data, availability_mask)
        else:
            return self.classifier.predict_proba(methylation_data, availability_mask, debug)
    
    def predict_with_threshold(
        self,
        methylation_data: np.ndarray,
        availability_mask: Optional[np.ndarray] = None,
        adjust_for_missing: bool = True,
        debug: bool = False
    ) -> Dict[str, Any]:
        """
        Predict using threshold-based classification (improved algorithm).
        
        This method uses the analytical threshold-based approach if the model
        was trained with the improved algorithm. Falls back to standard prediction
        if threshold information is not available.
        
        Args:
            methylation_data: Array of methylation values
            availability_mask: Boolean mask indicating available positions
            adjust_for_missing: Whether to adjust threshold for missing positions
            debug: Enable debug output
        
        Returns:
            Dictionary with predictions, probabilities, and diagnostic info
        """
        if self.classifier is None:
            raise RuntimeError("No classifier loaded")
        
        # Check if model has threshold (improved algorithm)
        if 'threshold' not in self.metadata or not hasattr(self.classifier, 'predict_with_threshold'):
            # Fallback to standard prediction
            if debug:
                print("⚠️ Model does not support threshold-based prediction, using standard method")
            proba = self.predict_proba(methylation_data, availability_mask, debug=debug)
            predictions = np.argmax(proba, axis=1)
            return {
                'predictions': predictions,
                'P_C': proba[:, 1],
                'P_H': proba[:, 0],
                'decision': np.where(predictions == 1, 'Cancer', 'Healthy')
            }
        
        # Use threshold-based prediction
        threshold = self.metadata['threshold']
        priors = self.metadata.get('priors', (0.5, 0.5))
        
        return self.classifier.predict_with_threshold(
            methylation_data,
            threshold=threshold,
            priors=priors,
            adjust_for_missing=adjust_for_missing,
            availability_mask=availability_mask
        )


def extract_chrom_context_from_classifier(classifier_path: Path) -> Tuple[str, str]:
    """
    Extract chromosome and context from classifier filename.

    Args:
        classifier_path: Path to classifier file

    Returns:
        Tuple of (chromosome, context)

    Raises:
        ValueError: If chromosome and context cannot be extracted
    """
    filename = classifier_path.stem  # Remove .pkl extension
    parts = filename.split('-')

    if len(parts) >= 3 and parts[-2].isdigit():
        # Format: something-chromosome-context-classifier.pkl
        chrom = parts[-2]
        context = parts[-1]
        return chrom, context

    # Fallback: try to extract from path
    path_parts = classifier_path.parts
    for part in reversed(path_parts):
        if '-' in part and (part.endswith('-CG') or part.endswith('-CHG') or part.endswith('-CHH')):
            parts = part.split('-')
            if len(parts) >= 2:
                chrom = parts[-2]
                context = parts[-1]
                return chrom, context

    raise ValueError(f"Could not extract chromosome and context from {classifier_path}")
