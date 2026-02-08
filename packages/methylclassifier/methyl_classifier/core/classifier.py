"""
Core classification functionality for MethylClassifier
"""

import pickle
import sys
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import numpy as np
import pandas as pd

# Module mapping for pickle compatibility
import importlib

# Import from parent package
from methyl_utils import ProbabilisticBetaClassifier
from ..models.config import ClassifierConfig

# Create a mapping for old module names to new ones
MODULE_MAPPING = {
    'methyl_detector': 'methyl_utils',
    'methyl_modeler': 'methyl_utils',
    'methyl_detector.classifiers': 'methyl_utils.probabilistic_beta_classifier',
    'methyl_modeler.classifiers': 'methyl_utils.probabilistic_beta_classifier',
    'methyl_detector.classifiers.classifier': 'methyl_utils.probabilistic_beta_classifier',
    'methyl_modeler.classifiers.classifier': 'methyl_utils.probabilistic_beta_classifier',
    'methyl_detector.probabilistic_beta_classifier': 'methyl_utils.probabilistic_beta_classifier',
    'methyl_modeler.probabilistic_beta_classifier': 'methyl_utils.probabilistic_beta_classifier',
    'methyl_detector.methyl_sample': 'methyl_utils.methyl_sample',
    'methyl_modeler.methyl_sample': 'methyl_utils.methyl_sample',
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
        self.classifier = None  # Single classifier (legacy mode)
        self.classifiers = {}  # Dict of {chromosome: classifier} for multi-chromosome mode
        self.chromosome_weights = {}  # Dict of {chromosome: weight} for multi-chromosome weighting
        self.is_multi_chromosome = False
        self.chromosome = None
        self.context_metadata = None
        self.n_classes = None
        self.class_names = None
        self.metadata = {}
        
        # Determine if we're loading a directory or single file
        model_path_str = self.config.model_dir or self.config.model_path
        if model_path_str is None:
            raise ValueError("Either model_path or model_dir must be provided")
        
        model_path = Path(model_path_str)
        
        if model_path.is_dir():
            # Multi-chromosome mode: load all classifiers from directory
            self.is_multi_chromosome = True
            self.load_classifiers_from_directory(model_path)
        elif model_path.is_file():
            # Single-file mode: load one classifier (backward compatible)
            self.is_multi_chromosome = False
            self.load_classifier(model_path)
        else:
            raise FileNotFoundError(f"Model path not found: {model_path}")

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
                self.context_metadata = self.metadata.get('context', 'unknown')

                # Multi-class aware configuration
                if hasattr(self.classifier, 'n_classes'):
                    self.n_classes = int(getattr(self.classifier, 'n_classes'))
                else:
                    self.n_classes = int(self.metadata.get('n_classes', 2))

                if hasattr(self.classifier, 'class_names') and self.classifier.class_names:
                    self.class_names = list(self.classifier.class_names)
                elif 'class_names' in self.metadata:
                    self.class_names = list(self.metadata.get('class_names'))
                else:
                    self.class_names = [
                        self.metadata.get('centroid1_name', 'centroid1'),
                        self.metadata.get('centroid2_name', 'centroid2')
                    ]
                
                # Display metadata
                print(f"📍 Classifier context: {self.chromosome}-{self.context}")
                print(f"📊 Training date: {self.metadata.get('training_date', 'unknown')}")
                print(f"📊 Classifier uses {self.metadata.get('n_dmps', 'unknown')} DMPs")
                if self.class_names is not None and len(self.class_names) >= 2:
                    print(f"📊 Class names: {self.class_names[0]} vs {self.class_names[1]}")
                else:
                    print(f"📊 Class names: {self.class_names}")
                
                # Display validation results if available
                if 'validation' in self.metadata:
                    val = self.metadata['validation']
                    print(f"✅ Validation accuracy: {val.get('overall_accuracy', 0):.1%}")
                    
                # Load pre-fitted calibrator if available (from MethylDetector when enable_platt_calibration was used)
                if 'platt_calibrator' in self.metadata and self.config.enable_platt_calibration:
                    import pickle
                    self.classifier.calibrator = pickle.loads(self.metadata['platt_calibrator'])
                    if 'platt_calibrator_scaler' in self.metadata:
                        self.classifier.calibrator_scaler = pickle.loads(self.metadata['platt_calibrator_scaler'])
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
                    self.chromosome, self.context_metadata = extract_chrom_context_from_classifier(model_path)
                    print(f"📋 Classifier trained on chromosome {self.chromosome}, context {self.context}")
                except ValueError as e:
                    print(f"⚠️ Could not extract chromosome/context: {e}")

                # Extract classifier metadata
                self._extract_classifier_metadata()

        except Exception as e:
            print(f"❌ Failed to load classifier from {model_path}: {e}")
            sys.exit(1)
        
        # Set temperature if classifier is loaded
        if self.classifier is not None:
            self.classifier.set_temperature(self.config.temperature)

    def load_classifiers_from_directory(self, model_dir: Path) -> None:
        """
        Load all chromosome classifiers from a directory.
        
        Looks for files matching pattern: classifier-{chrom}.pkl
        Extracts chromosome number from filename and loads each classifier.
        Computes weights based on trimmed-mean effect_size from selected_dmps_df.
        
        Args:
            model_dir: Path to directory containing classifier files
        """
        if not model_dir.is_dir():
            raise ValueError(f"Model directory does not exist: {model_dir}")
        
        # Find all classifier files matching pattern classifier-{chrom}.pkl
        pattern = re.compile(r'^classifier-(.+)\.pkl$')
        classifier_files = {}
        
        for file_path in model_dir.glob('classifier-*.pkl'):
            match = pattern.match(file_path.name)
            if match:
                chrom = match.group(1)
                classifier_files[chrom] = file_path
        
        if not classifier_files:
            raise ValueError(f"No classifier files found in {model_dir} matching pattern 'classifier-{{chrom}}.pkl'")
        
        print(f"\n📂 Loading {len(classifier_files)} chromosome classifier(s) from {model_dir}")
        
        # Store model packages for weight calculation and DMP position extraction
        model_packages = {}
        self.model_packages = model_packages  # Store for position extraction
        any_platt_loaded = False

        # Load each classifier
        for chrom, file_path in sorted(classifier_files.items()):
            try:
                with open(file_path, 'rb') as f:
                    model_package = CustomUnpickler(f).load()
                
                # Extract classifier from package
                if isinstance(model_package, dict):
                    # Check if classifier exists, otherwise create from dmpDF
                    if 'classifier' in model_package:
                        classifier = model_package['classifier']
                        classifier.set_temperature(self.config.temperature)
                        metadata = model_package.get('metadata', {})
                        if 'platt_calibrator' in metadata and self.config.enable_platt_calibration:
                            import pickle
                            classifier.calibrator = pickle.loads(metadata['platt_calibrator'])
                            if 'platt_calibrator_scaler' in metadata:
                                classifier.calibrator_scaler = pickle.loads(metadata['platt_calibrator_scaler'])
                            any_platt_loaded = True
                        self.classifiers[chrom] = classifier
                        model_packages[chrom] = model_package
                        print(f"✅ Loaded classifier for chromosome {chrom}")
                    elif 'dmpDF' in model_package:
                        # Create BetaClassifier from dmpDF
                        from methyl_utils import BetaClassifier
                        dmpDF = model_package['dmpDF']
                        classifier = BetaClassifier.from_dataframe(dmpDF)
                        classifier.set_temperature(self.config.temperature)
                        metadata = model_package.get('metadata', {})
                        if 'platt_calibrator' in metadata and self.config.enable_platt_calibration:
                            import pickle
                            classifier.calibrator = pickle.loads(metadata['platt_calibrator'])
                            if 'platt_calibrator_scaler' in metadata:
                                classifier.calibrator_scaler = pickle.loads(metadata['platt_calibrator_scaler'])
                            any_platt_loaded = True
                        self.classifiers[chrom] = classifier
                        model_packages[chrom] = model_package
                        print(f"✅ Created BetaClassifier from dmpDF for chromosome {chrom}")
                    else:
                        raise ValueError(f"No classifier or dmpDF found in model package for chromosome {chrom}")
                else:
                    # Legacy format - assume it's a classifier directly
                    classifier = model_package
                    classifier.set_temperature(self.config.temperature)
                    self.classifiers[chrom] = classifier
                    model_packages[chrom] = {'classifier': classifier}
                    print(f"✅ Loaded classifier for chromosome {chrom} (legacy format)")
                    
            except Exception as e:
                print(f"⚠️ Failed to load classifier from {file_path}: {e}")
                continue
        
        if not self.classifiers:
            raise ValueError(f"No valid classifiers loaded from {model_dir}")
        
        # Compute or use predefined weights
        if self.config.chromosome_weights:
            # Use predefined weights
            print(f"\n⚖️ Using predefined chromosome weights")
            self.chromosome_weights = self.config.chromosome_weights.copy()
            
            # Normalize to sum to 1
            total_weight = sum(self.chromosome_weights.values())
            if total_weight > 0:
                self.chromosome_weights = {k: v / total_weight for k, v in self.chromosome_weights.items()}
            else:
                # Fallback to equal weights
                n_chrom = len(self.classifiers)
                self.chromosome_weights = {chrom: 1.0 / n_chrom for chrom in self.classifiers.keys()}
        else:
            # Compute weights from trimmed-mean effect_size
            print(f"\n⚖️ Computing chromosome weights from asymmetric trimmed-mean effect_size")
            print(f"   (removing bottom {self.config.trimmed_percentile_low*100:.0f}% and top {self.config.trimmed_percentile_high*100:.0f}%)")
            self.chromosome_weights = self._compute_chromosome_weights(model_packages)
        
        # Display weights
        print(f"\n📊 Chromosome weights:")
        for chrom in sorted(self.chromosome_weights.keys()):
            print(f"  Chromosome {chrom}: {self.chromosome_weights[chrom]:.4f}")

        self._calibrated = any_platt_loaded
        if any_platt_loaded:
            print("Loaded pre-fitted Platt calibrator(s) from model metadata (multi-chromosome)")
        
        # Validate all classifiers have same number of classes
        n_classes_list = []
        class_names_list = []
        
        for chrom, classifier in self.classifiers.items():
            # Try to get n_classes from classifier or metadata
            if hasattr(classifier, 'n_classes'):
                n_classes_list.append(classifier.n_classes)
            else:
                # Try to infer from predict_proba
                try:
                    feature_info = classifier.get_feature_info()
                    dummy_data = np.zeros((1, feature_info['n_features']))
                    probas = classifier.predict_proba(dummy_data)
                    n_classes_list.append(probas.shape[1])
                except:
                    n_classes_list.append(2)  # Default
        
        if len(set(n_classes_list)) > 1:
            print(f"⚠️ Warning: Classifiers have different numbers of classes: {set(n_classes_list)}")
        
        # Set common values (use first classifier's values)
        first_chrom = sorted(self.classifiers.keys())[0]
        self.chromosome = first_chrom
        self.n_classes = n_classes_list[0] if n_classes_list else 2
        
        # Try to get class names from metadata
        if first_chrom in model_packages:
            metadata = model_packages[first_chrom].get('metadata', {})
            if 'class_names' in metadata:
                self.class_names = list(metadata.get('class_names'))
            else:
                self.class_names = [
                    metadata.get('centroid1_name', 'centroid1'),
                    metadata.get('centroid2_name', 'centroid2')
                ]
            self.context_metadata = metadata.get('context', 'unknown')
        
        print(f"\n✅ Multi-chromosome classifier ready: {len(self.classifiers)} chromosomes, {self.n_classes} classes")

        # Centroid self-check: each chromosome's classifier should give P(class1)≈0 for centroid1, ≈1 for centroid2
        self._run_centroid_self_check(model_packages)

        # Collect all unique DMP positions across all classifiers (for massive performance optimization)
        self._collect_all_dmp_positions()

    def _run_centroid_self_check(self, model_packages: Dict[str, Dict[str, Any]]) -> None:
        """
        Run centroid self-check: classify centroid1 and centroid2 profiles at DMP positions.
        Expect centroid1 → P(class1) ≈ 0, centroid2 → P(class1) ≈ 1. If not, the model
        may have poor separation or inverted labels (helps diagnose all-samples-one-class).
        """
        required = {'alpha1', 'beta1', 'alpha2', 'beta2'}
        bad = []
        for chrom in sorted(self.classifiers.keys()):
            package = model_packages.get(chrom, {})
            dmpDF = package.get('dmpDF')
            if dmpDF is None or not isinstance(dmpDF, pd.DataFrame) or not required.issubset(dmpDF.columns):
                continue
            clf = self.classifiers[chrom]
            a1, b1 = dmpDF['alpha1'].values.astype(np.float64), dmpDF['beta1'].values.astype(np.float64)
            a2, b2 = dmpDF['alpha2'].values.astype(np.float64), dmpDF['beta2'].values.astype(np.float64)
            mean1 = np.clip(a1 / (a1 + b1), 1e-6, 1.0 - 1e-6)
            mean2 = np.clip(a2 / (a2 + b2), 1e-6, 1.0 - 1e-6)
            profile_c1 = mean1.reshape(1, -1)
            profile_c2 = mean2.reshape(1, -1)
            avail = np.ones((1, len(mean1)), dtype=bool)
            try:
                p_c1 = clf.predict_proba(profile_c1, avail, debug=False)[0, 1]
                p_c2 = clf.predict_proba(profile_c2, avail, debug=False)[0, 1]
            except Exception:
                continue
            if p_c1 > 0.5 or p_c2 < 0.5:
                bad.append((chrom, p_c1, p_c2))
        if not bad:
            print("🔬 Centroid self-check: OK (centroid1→class0, centroid2→class1 on all chromosomes)")
            return
        print("🔬 Centroid self-check: some chromosomes show poor or inverted separation:")
        for chrom, p_c1, p_c2 in bad[:10]:
            print(f"   Chromosome {chrom}: centroid1→P(class1)={p_c1:.3f}, centroid2→P(class1)={p_c2:.3f} (expect ~0 and ~1)")
        if len(bad) > 10:
            print(f"   ... and {len(bad) - 10} more. Try enable_platt_calibration: false or re-train detector with better separation.")

    def _collect_all_dmp_positions(self) -> None:
        """
        Collect all unique DMP positions across all classifiers for massive performance optimization.
        This allows loading only the positions needed for classification instead of entire chromosomes.
        
        Uses a binary-optimized DataFrame for memory efficiency with categorical chromosome encoding.
        Extracts positions directly from dmpDF when available (faster than get_feature_info).
        
        Note: If the classifier was trained on merged contexts (CG+CHG+CHH), the dmpDF contains
        positions from all contexts. We extract ALL positions from the 'pos' column, which will
        be used to load matching positions from each context file (CG.h5, CHG.h5, CHH.h5) when
        classifying samples. Positions are already sorted in dmpDF.
        """
        # Build DataFrame for efficient storage and binary optimization
        positions_data = []
        
        for chrom, classifier in self.classifiers.items():
            try:
                # First, try to get positions directly from dmpDF (fastest - already sorted)
                # dmpDF contains all selected DMPs, including all contexts if model was trained on merged contexts
                positions = None
                context_info = None
                if hasattr(self, 'model_packages') and chrom in self.model_packages:
                    model_package = self.model_packages[chrom]
                    dmpDF = model_package.get('dmpDF')
                    if dmpDF is not None and isinstance(dmpDF, pd.DataFrame) and 'pos' in dmpDF.columns:
                        # Extract positions directly from dmpDF (already sorted!)
                        # If model includes all contexts, dmpDF['pos'] contains positions from all contexts
                        positions = dmpDF['pos'].values.astype(np.uint32)
                        
                        # Log context distribution if available (for debugging)
                        if 'context' in dmpDF.columns:
                            context_counts = dmpDF['context'].value_counts()
                            context_info = f" (contexts: {dict(context_counts)})"
                
                # Fallback: get from classifier feature_info
                if positions is None or len(positions) == 0:
                    feature_info = classifier.get_feature_info()
                    positions = feature_info.get('positions', [])
                    if len(positions) > 0:
                        positions = np.array(positions, dtype=np.uint32)
                
                if len(positions) > 0:
                    # Store as list of (chromosome, position) tuples
                    # Positions are already sorted from dmpDF, so we maintain that order
                    positions_data.extend([(chrom, int(pos)) for pos in positions])
                    if context_info:
                        print(f"📊 Chromosome {chrom}: Extracted {len(positions):,} DMP positions{context_info}")
            except Exception as e:
                print(f"⚠️ Warning: Could not get DMP positions for chromosome {chrom}: {e}")
        
        # Create optimized DataFrame
        if positions_data:
            self.dmp_positions_df = pd.DataFrame(positions_data, columns=['chromosome', 'position'])
            # Use categorical dtype for chromosome (memory efficient)
            self.dmp_positions_df['chromosome'] = self.dmp_positions_df['chromosome'].astype('category')
            # Use uint32 for positions (memory efficient)
            self.dmp_positions_df['position'] = self.dmp_positions_df['position'].astype(np.uint32)
            # Sort for efficient lookups (positions from dmpDF are already sorted, but we sort by chromosome too)
            self.dmp_positions_df = self.dmp_positions_df.sort_values(['chromosome', 'position']).reset_index(drop=True)
            
            # Verify positions are sorted per chromosome (critical for hyperslice binary search optimization)
            for chrom in self.dmp_positions_df['chromosome'].cat.categories:
                chrom_positions = self.dmp_positions_df[
                    self.dmp_positions_df['chromosome'] == chrom
                ]['position'].values
                if len(chrom_positions) > 1:
                    assert np.all(np.diff(chrom_positions) >= 0), f"Positions for {chrom} are not sorted!"
        else:
            self.dmp_positions_df = pd.DataFrame(columns=['chromosome', 'position'])
            self.dmp_positions_df['chromosome'] = self.dmp_positions_df['chromosome'].astype('category')
            self.dmp_positions_df['position'] = self.dmp_positions_df['position'].astype(np.uint32)
        
        # Calculate all unique positions (using DataFrame for efficiency)
        self.all_dmp_positions = np.array(sorted(self.dmp_positions_df['position'].unique()), dtype=np.uint32) if len(self.dmp_positions_df) > 0 else np.array([], dtype=np.uint32)
        
        # Build dictionary cache for fast lookups (optimized - only build what's needed)
        # Use dict comprehension for speed
        if len(self.dmp_positions_df) > 0:
            self._dmp_positions_dict_cache = {
                chrom: self.dmp_positions_df[
                    self.dmp_positions_df['chromosome'] == chrom
                ]['position'].values.astype(np.uint32)
                for chrom in self.dmp_positions_df['chromosome'].cat.categories
            }
        else:
            self._dmp_positions_dict_cache = {}
        
        # Calculate per-chromosome DMP statistics
        chrom_counts = self.dmp_positions_df.groupby('chromosome', observed=True).size()
        for chrom in sorted(self.classifiers.keys()):
            if chrom in chrom_counts.index:
                count = chrom_counts[chrom]
                print(f"💎 {chrom}: {count} DMPs")
            else:
                print(f"⚠️ {chrom}: No DMPs found")

        print(f"🚀 Collected {len(self.all_dmp_positions)} unique DMP positions across all classifiers")
    
    @property
    def model_contexts(self) -> Optional[List[str]]:
        """
        Return the list of contexts the model was trained on (e.g. ['CG'] or ['CG','CHG','CHH']).
        Used to load only those contexts when classifying (e.g. CG-only to match MethylDetector).
        """
        if not hasattr(self, 'model_packages') or not self.model_packages:
            return None
        for _chrom, pkg in sorted(self.model_packages.items()):
            meta = pkg.get('metadata') or {}
            config = meta.get('config') or {}
            ctx = config.get('contexts')
            if ctx is not None and isinstance(ctx, (list, tuple)) and len(ctx) > 0:
                return list(ctx)
        return None

    @property
    def dmp_positions_by_chrom(self) -> Dict[str, np.ndarray]:
        """
        Dictionary interface for DMP positions (backward compatibility).
        Returns chromosome -> positions array mapping.
        
        Note: The dictionary is built from the optimized DataFrame on initialization.
        This provides O(1) lookup performance while using memory-efficient DataFrame storage.
        """
        # Return cached dictionary (built during _collect_all_dmp_positions)
        if not hasattr(self, '_dmp_positions_dict_cache'):
            self._dmp_positions_dict_cache = {}
        return self._dmp_positions_dict_cache

    def _compute_chromosome_weights(self, model_packages: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
        """
        Compute chromosome weights from trimmed-mean effect_size of selected DMPs.
        
        Args:
            model_packages: Dict of {chromosome: model_package} containing classifier and metadata
            
        Returns:
            Dict of {chromosome: normalized_weight} with weights summing to 1.0
        """
        raw_weights = {}
        
        for chrom, package in model_packages.items():
            # Try to get selected_dmps_df or dmpDF from package
            selected_dmps_df = package.get('selected_dmps_df')
            dmpDF = package.get('dmpDF')
            
            # Use dmpDF if selected_dmps_df is not available
            if selected_dmps_df is None or not isinstance(selected_dmps_df, pd.DataFrame):
                if dmpDF is not None and isinstance(dmpDF, pd.DataFrame):
                    # dmpDF has 'weight' column which can be used
                    selected_dmps_df = dmpDF
                else:
                    print(f"⚠️ Chromosome {chrom}: No selected_dmps_df or dmpDF found, using equal weight")
                    raw_weights[chrom] = 1.0
                    continue
            
            # Check for effect_size or weight column
            if 'effect_size' in selected_dmps_df.columns:
                effect_sizes = selected_dmps_df['effect_size'].dropna().values
            elif 'weight' in selected_dmps_df.columns:
                # Use weight column from dmpDF
                effect_sizes = selected_dmps_df['weight'].dropna().values
            else:
                print(f"⚠️ Chromosome {chrom}: No effect_size or weight column found, using equal weight")
                raw_weights[chrom] = 1.0
                continue
            
            # Compute trimmed mean
            if len(effect_sizes) == 0:
                print(f"⚠️ Chromosome {chrom}: No valid effect_size/weight values, using equal weight")
                raw_weights[chrom] = 1.0
                continue
            
            # Calculate asymmetric trimmed percentiles
            # Remove more from bottom (low effect sizes) and less from top (high effect sizes are important)
            qlo = self.config.trimmed_percentile_low
            qhi = 1.0 - self.config.trimmed_percentile_high
            
            q_low, q_high = np.quantile(effect_sizes, [qlo, qhi])
            
            # Trim values
            trimmed_effect_sizes = effect_sizes[(effect_sizes >= q_low) & (effect_sizes <= q_high)]
            
            # Compute mean (fallback to full mean if trimmed is empty)
            if len(trimmed_effect_sizes) > 0:
                trimmed_mean = np.mean(trimmed_effect_sizes)
            else:
                trimmed_mean = np.mean(effect_sizes) if len(effect_sizes) > 0 else 1.0
            
            raw_weights[chrom] = trimmed_mean
            print(f"  Chromosome {chrom}: trimmed-mean effect_size = {trimmed_mean:.4f}")
        
        # Normalize weights to sum to 1.0
        total_weight = sum(raw_weights.values())
        if total_weight > 0:
            normalized_weights = {k: v / total_weight for k, v in raw_weights.items()}
        else:
            # Fallback to equal weights if all are zero
            n_chrom = len(raw_weights)
            normalized_weights = {chrom: 1.0 / n_chrom for chrom in raw_weights.keys()}
            print(f"⚠️ All weights were zero, using equal weights")
        
        return normalized_weights

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
        if self.is_multi_chromosome:
            # Return feature info from first classifier (or combine info from all)
            if not self.classifiers:
                raise RuntimeError("No classifiers loaded")
            first_chrom = sorted(self.classifiers.keys())[0]
            return self.classifiers[first_chrom].get_feature_info()
        else:
            if self.classifier is None:
                raise RuntimeError("No classifier loaded")
            return self.classifier.get_feature_info()
    
    def predict(self, methylation_data: np.ndarray,
                availability_mask: Optional[np.ndarray] = None,
                debug: bool = False) -> np.ndarray:
        """
        Predict classes for methylation data using Beta distributions.

        Args:
            methylation_data: Array of methylation values (n_samples, n_positions)
            availability_mask: Boolean mask indicating available positions
            debug: Enable debug output

        Returns:
            Array of class predictions
        """
        if self.is_multi_chromosome:
            # Multi-chromosome mode: combine predictions from all chromosomes
            probas = self.predict_proba(methylation_data, availability_mask, debug)
            return np.argmax(probas, axis=1)
        else:
            # Single classifier mode
            if self.classifier is None:
                raise RuntimeError("No classifier loaded")
            return self.classifier.predict(methylation_data, availability_mask, debug)

    def predict_proba(self, methylation_data: np.ndarray,
                     availability_mask: Optional[np.ndarray] = None,
                     debug: bool = False) -> np.ndarray:
        """
        Predict class probabilities for methylation data using Beta distributions.

        Args:
            methylation_data: Array of methylation values (n_samples, n_positions)
                For multi-chromosome mode, this should contain data for all positions
                from all chromosomes concatenated. The method will extract chromosome-specific
                positions from each classifier's feature_info.
            availability_mask: Boolean mask indicating available positions
            debug: Enable debug output

        Returns:
            Array of class probabilities (n_samples, n_classes)
        """
        if self.is_multi_chromosome:
            return self._predict_proba_multi_chromosome(methylation_data, availability_mask, debug)
        else:
            # Single classifier mode
            if self.classifier is None:
                raise RuntimeError("No classifier loaded")

            if hasattr(self, '_calibrated') and self._calibrated:
                return self.classifier.predict_proba_calibrated(methylation_data, availability_mask)
            else:
                return self.classifier.predict_proba(methylation_data, availability_mask, debug)
    
    def _predict_proba_multi_chromosome(
        self,
        methylation_data: np.ndarray,
        availability_mask: Optional[np.ndarray] = None,
        debug: bool = False
    ) -> np.ndarray:
        """
        Predict probabilities using multiple chromosome classifiers with weighted combination.
        
        Args:
            methylation_data: Array of methylation values (n_samples, n_all_positions)
                Should contain data for all DMP positions from all chromosomes
            availability_mask: Boolean mask indicating available positions
            debug: Enable debug output
            
        Returns:
            Weighted average of probabilities from all chromosome classifiers
        """
        n_samples = methylation_data.shape[0]
        n_classes = self.n_classes

        if n_samples == 0 or methylation_data.ndim < 2:
            return np.zeros((n_samples, n_classes), dtype=np.float64)
        
        # Initialize weighted probability sum
        weighted_probas = np.zeros((n_samples, n_classes))
        
        # Collect all positions from all classifiers to create mapping
        # This assumes methylation_data contains positions from all chromosomes in order
        # We need to extract chromosome-specific data for each classifier
        
        for chrom, classifier in self.classifiers.items():
            weight = self.chromosome_weights.get(chrom, 0.0)
            
            if weight == 0.0:
                continue
            
            # Get feature info for this chromosome's classifier
            feature_info = classifier.get_feature_info()
            chrom_positions = feature_info['positions']
            n_chrom_dmps = len(chrom_positions)
            
            # For now, assume methylation_data is already separated by chromosome
            # or that we can extract the relevant positions
            # TODO: This assumes methylation_data structure matches classifier expectations
            # In practice, we may need to match positions from sample to classifier positions
            
            # Extract chromosome-specific data
            # This is a simplified approach - in practice, we'd need to match positions
            if n_chrom_dmps <= methylation_data.shape[1]:
                # Try to use first n_chrom_dmps columns (this is a simplification)
                chrom_data = methylation_data[:, :n_chrom_dmps]
                chrom_mask = availability_mask[:, :n_chrom_dmps] if availability_mask is not None else None
                
                try:
                    # Get probabilities from this chromosome's classifier
                    if hasattr(classifier, 'predict_proba_calibrated') and hasattr(self, '_calibrated') and self._calibrated:
                        chrom_probas = classifier.predict_proba_calibrated(chrom_data, chrom_mask)
                    else:
                        chrom_probas = classifier.predict_proba(chrom_data, chrom_mask, debug)
                    
                    # Weight and accumulate
                    weighted_probas += weight * chrom_probas
                    
                    if debug:
                        print(f"  Chromosome {chrom}: weight={weight:.4f}, avg probas={np.mean(chrom_probas, axis=0)}")
                        
                except Exception as e:
                    if debug:
                        print(f"⚠️ Chromosome {chrom} prediction failed: {e}")
                    # Skip this chromosome
                    continue
            else:
                if debug:
                    print(f"⚠️ Chromosome {chrom}: DMP count mismatch ({n_chrom_dmps} vs {methylation_data.shape[1]})")
                continue
        
        # Normalize probabilities to sum to 1
        proba_sums = np.sum(weighted_probas, axis=1, keepdims=True)
        proba_sums = np.where(proba_sums == 0, 1.0, proba_sums)  # Avoid division by zero
        weighted_probas = weighted_probas / proba_sums
        
        return weighted_probas
    
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
