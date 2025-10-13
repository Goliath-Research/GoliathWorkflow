#!/usr/bin/env python3
"""
Example usage of the ProbabilisticBetaClassifier after loading from pickle.

This script demonstrates how to use a trained ProbabilisticBetaClassifier for sample classification.
It can load methylation samples from .h5 files and classify them using the Bayesian classifier.

Usage:
    python example_usage.py <model_path> <h5_path> [--test-random [N]]

Arguments:
    model_path: Path to the saved classifier pickle file (chromosome/context extracted automatically)
    h5_path: Path to .h5 file or directory containing .h5 files (searched recursively, filtered by classifier's chromosome/context)
    --test-random [N]: Also test with N random samples (default: 3)

Examples:
    # Classify all .h5 files in a directory (recursive search)
    python example_usage.py classifier_model.pkl /path/to/samples/

    # Classify a single .h5 file
    python example_usage.py classifier_model.pkl sample.h5

    # Classify .h5 files and also test with 5 random samples
    python example_usage.py classifier_model.pkl /path/to/samples/ --test-random 5

The script will:
1. Load the trained ProbabilisticBetaClassifier from the pickle file
2. Extract chromosome/context information from the classifier path
3. Load methylation data from .h5 files matching the classifier's chromosome/context (recursive search)
4. Extract methylation values at the DMP positions used by the classifier
5. Classify each sample using Bayesian inference with Beta distributions
6. Display classification results with probabilities

File Types Supported:
- Individual samples (N=1): Use mC/uC data for precise methylation calls
- Basic centroids (N>1): Use aggregated statistics (Sx/N) for mean methylation
- Extended centroids: Use sufficient statistics when available

File Naming Requirements:
- Files must be named exactly `{chrom}-{context}.h5` (e.g., `1-CG.h5`, `10-CHG.h5`)
- The classifier automatically filters for matching chromosome and context
- All files use the same .h5 format - the N field distinguishes sample type:
  - N = 1: Individual biological sample
  - N > 1: Centroid aggregated from N samples

Requirements:
- methyl_utils package for .h5 file loading
- Trained classifier pickle file from MethylDetector

Output shows:
- Sample filename
- Predicted class (0=Centroid1, 1=Centroid2)
- Posterior probabilities for each class
- Summary statistics
"""

import pickle
import numpy as np
from pathlib import Path
from typing import List, Tuple

# Import for .h5 file handling
try:
    from methyl_utils import MethylSample
    METHYL_UTILS_AVAILABLE = True
except ImportError:
    METHYL_UTILS_AVAILABLE = False
    print("Warning: methyl_utils not available - .h5 file loading disabled")

def load_classifier(model_path):
    """
    Load a saved classifier model from pickle file.
    
    Note: Classifiers are now trained using MethylTrainer and loaded
    using MethylClassifier. This is a legacy example for reference only.
    """
    with open(model_path, 'rb') as f:
        classifier = pickle.load(f)
    return classifier

# Note: ProbabilisticBetaClassifier is now in MethylUtils
# For training: use MethylTrainer CLI tool
# For classification: use MethylClassifier CLI tool
# from methyl_utils import ProbabilisticBetaClassifier

def load_methylation_sample(h5_path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """
    Load methylation data from a single .h5 file.

    Automatically detects file type based on N field:
    - N = 1: Individual sample (use mC/uC data)
    - N > 1: Centroid (use aggregated statistics)

    Args:
        h5_path: Path to the .h5 file

    Returns:
        Tuple of (positions, methylation_levels)
    """
    if not METHYL_UTILS_AVAILABLE:
        raise ImportError("methyl_utils not available - cannot load .h5 files")

    try:
        # Load the .h5 file (all MethylSample files use load_from_h5)
        sample: MethylSample = MethylSample.load_from_h5(str(h5_path))

        if sample.is_centroid:
            # Use mean methylation: Sx/N
            methylation_levels = sample.Sx / sample.N
            methylation_levels = np.clip(methylation_levels, 0.0, 1.0)
        else:
            # Use methylation counts
            total_reads = sample.mC + sample.uC
            methylation_levels = np.divide(
                sample.mC, 
                total_reads,
                out=np.zeros_like(sample.mC, dtype=float),
                where=total_reads != 0
            )

        return sample.pos, methylation_levels

    except Exception as e:
        raise ValueError(f"Failed to load {h5_path}: {e}")

def extract_chrom_context_from_classifier(classifier_path: Path) -> Tuple[str, str]:
    """
    Extract chromosome and context from classifier path.

    Expected format: .../{prefix}-{chrom}-{context}/classifier_model.pkl
    Examples: pb-ch-1-CG, pb-ch-10-CHG, etc.

    Args:
        classifier_path: Path to the classifier file

    Returns:
        Tuple of (chromosome, context)
    """
    # Try to extract from parent directory name
    parent_dir = classifier_path.parent.name

    # Look for pattern like "pb-ch-1-CG" or similar
    parts = parent_dir.split('-')
    if len(parts) >= 3 and parts[-2].isdigit():
        # Last part is context (CG, CHG, CHH)
        context = parts[-1]
        # Second to last is chromosome number
        chrom = parts[-2]
        return chrom, context
    else:
        # Fallback: try to extract from filename or ask user
        raise ValueError(f"Cannot determine chromosome and context from classifier path: {classifier_path}. "
                        f"Expected format: .../{prefix}-{chrom}-{context}/classifier_model.pkl")

def filter_h5_files_by_chrom_context(h5_files: List[Path], chrom: str, context: str) -> List[Path]:
    """
    Filter .h5 files to only include those matching the specified chromosome and context.
    Expects files to be named {chrom}-{context}.h5 (exact chromosome match).

    Args:
        h5_files: List of .h5 file paths
        chrom: Chromosome number (e.g., "1", "10")
        context: Methylation context (e.g., "CG", "CHG", "CHH")

    Returns:
        Filtered list of .h5 files
    """
    expected_pattern = f"{chrom}-{context}.h5"
    filtered_files = []

    for h5_file in h5_files:
        # Check if filename exactly matches the pattern
        # This prevents "11-CG.h5" from matching when chrom="1"
        if h5_file.name == expected_pattern:
            filtered_files.append(h5_file)

    return filtered_files

def load_samples_from_directory(h5_dir: Path, chrom: str = None, context: str = None) -> List[Tuple[str, np.ndarray, np.ndarray]]:
    """
    Load all .h5 samples from a directory (recursively).

    Args:
        h5_dir: Directory containing .h5 files (searched recursively)

    Returns:
        List of tuples: (relative_path, positions, methylation_levels)
    """
    if not h5_dir.exists():
        raise FileNotFoundError(f"Directory not found: {h5_dir}")

    samples = []
    all_h5_files = list(h5_dir.rglob("*.h5"))

    if not all_h5_files:
        raise FileNotFoundError(f"No .h5 files found in {h5_dir} or its subdirectories")

    # Filter by chromosome and context if specified
    if chrom and context:
        h5_files = filter_h5_files_by_chrom_context(all_h5_files, chrom, context)
        print(f"Found {len(all_h5_files)} total .h5 files, {len(h5_files)} match {chrom}-{context}")
    else:
        h5_files = all_h5_files
        print(f"Found {len(h5_files)} .h5 files")

    if not h5_files:
        filter_msg = f" matching {chrom}-{context}" if chrom and context else ""
        raise FileNotFoundError(f"No .h5 files{filter_msg} found in {h5_dir} or its subdirectories")

    for h5_file in sorted(h5_files):
        try:
            positions, methylation_levels = load_methylation_sample(h5_file)
            # Use relative path from the root directory for cleaner display
            relative_path = h5_file.relative_to(h5_dir)
            samples.append((str(relative_path), positions, methylation_levels))
        except Exception as e:
            relative_path = h5_file.relative_to(h5_dir)
            print(f"  ✗ Failed to load {relative_path}: {e}")

    if not samples:
        raise ValueError(f"No valid .h5 files could be loaded from {h5_dir}")

    return samples

def extract_dmp_features(classifier, samples: List[Tuple[str, np.ndarray, np.ndarray]]) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """
    Extract methylation features for the DMP positions used by the classifier.

    Args:
        classifier: Trained ProbabilisticBetaClassifier
        samples: List of (filename, positions, methylation_levels)

    Returns:
        Tuple of (feature_matrix, availability_mask, sample_names)
        feature_matrix: shape (n_samples, n_dmps) with 0.5 for missing positions
        availability_mask: shape (n_samples, n_dmps) with True for available positions
    """
    feature_info = classifier.get_feature_info()
    n_dmps = feature_info['n_features']

    print(f"Classifier uses {n_dmps} DMP positions")

    feature_matrix = []
    availability_mask = []
    sample_names = []

    for sample_name, positions, methylation_levels in samples:
        # Create position to methylation mapping
        pos_to_methylation = dict(zip(positions, methylation_levels))

        # Extract methylation values for DMP positions
        sample_features = []
        sample_mask = []
        missing_positions = 0

        for dmp_pos in feature_info['positions']:
            if dmp_pos in pos_to_methylation:
                methylation = pos_to_methylation[dmp_pos]
                # Ensure methylation is in valid range [0, 1]
                methylation = np.clip(methylation, 0.0, 1.0)
                sample_features.append(methylation)
                sample_mask.append(True)
            else:
                # Position not found in sample - use 0.5 (neutral) but mark as unavailable
                sample_features.append(0.5)
                sample_mask.append(False)
                missing_positions += 1

        feature_matrix.append(sample_features)
        availability_mask.append(sample_mask)
        sample_names.append(sample_name)

        if missing_positions > 0:
            print(f"  ⚠️ {sample_name}: {missing_positions}/{n_dmps} DMP positions missing")

    return np.array(feature_matrix), np.array(availability_mask), sample_names

def classify_samples_from_h5(classifier, h5_path: Path, chrom: str = None, context: str = None) -> None:
    """
    Load samples from .h5 files and classify them using the trained classifier.

    Args:
        classifier: Trained ProbabilisticBetaClassifier
        h5_path: Path to .h5 file or directory containing .h5 files
        chrom: Chromosome filter (optional)
        context: Context filter (optional)
    """
    filter_info = f" ({chrom}-{context})" if chrom and context else ""
    print(f"\n🔍 Loading samples from: {h5_path}{filter_info}")

    # Handle both single file and directory
    if h5_path.is_file():
        if h5_path.suffix.lower() != '.h5':
            raise ValueError(f"Not an .h5 file: {h5_path}")
        # Check if single file matches the expected chromosome/context
        if chrom and context:
            expected_pattern = f"{chrom}-{context}.h5"
            if h5_path.name != expected_pattern:
                raise ValueError(f"File {h5_path.name} does not match expected pattern {expected_pattern}")
        samples = [load_methylation_sample(h5_path)]
        samples = [(h5_path.name, samples[0][0], samples[0][1])]
    elif h5_path.is_dir():
        samples = load_samples_from_directory(h5_path, chrom, context)
    else:
        raise FileNotFoundError(f"Path not found: {h5_path}")

    print(f"\n📊 Extracting features for {len(samples)} samples...")
    feature_matrix, availability_mask, sample_names = extract_dmp_features(classifier, samples)

    print("\n🤖 Classifying samples...")
    predictions, probabilities = classify_sample(classifier, feature_matrix, availability_mask)

    # Display results
    print("\n📋 Classification Results:")
    print("-" * 60)
    print(f"{'Sample':<30} {'Predicted':<10} {'Prob_Cancer':<12} {'Prob_Healthy':<12}")
    print("-" * 60)

    class_counts = {0: 0, 1: 0}
    for name, pred, prob in zip(sample_names, predictions, probabilities):
        predicted_label = "Cancer" if pred == 0 else "Healthy"
        class_counts[pred] += 1
        print(f"{name:<30} {predicted_label:<10} {prob[0]:<12.4f} {prob[1]:<12.4f}")

    print("-" * 60)
    print(f"Total samples: {len(samples)}")
    print(f"Cancer (Class 0): {class_counts[0]} samples")
    print(f"Healthy (Class 1): {class_counts[1]} samples")

def classify_sample(classifier, methylation_data, availability_mask=None, debug=False):
    """
    Classify a sample using the probabilistic classifier.

    Args:
        classifier: Loaded ProbabilisticBetaClassifier
        methylation_data: Array of methylation values for the DMP positions
                         Shape should be (n_samples, n_features) where n_features
                         matches the number of DMPs used in training
        availability_mask: Boolean mask indicating which positions are available
        debug: If True, enable debug output

    Returns:
        predictions: Class predictions (0 or 1)
        probabilities: Posterior probabilities for each class
    """
    # Ensure methylation_data is the right shape
    if methylation_data.ndim == 1:
        methylation_data = methylation_data.reshape(1, -1)
        if availability_mask is not None:
            availability_mask = availability_mask.reshape(1, -1)

    # Get predictions and probabilities
    predictions = classifier.predict(methylation_data, availability_mask, debug)
    probabilities = classifier.predict_proba(methylation_data, availability_mask, debug)

    return predictions, probabilities

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Classify methylation samples using a trained ProbabilisticBetaClassifier")
    parser.add_argument("model_path", help="Path to the saved classifier pickle file")
    parser.add_argument("h5_path", help="Path to .h5 file or directory containing .h5 files")
    parser.add_argument("--test-random", type=int, nargs='?', const=3,
                       help="Also test with N random samples (default: 3)")

    args = parser.parse_args()

    try:
        # Load the classifier
        model_path = Path(args.model_path)
        print(f"🔍 Loading classifier from: {model_path}")
        classifier = load_classifier(model_path)
        print(f"✅ Loaded classifier: {classifier}")

        # Extract chromosome and context from classifier path
        try:
            chrom, context = extract_chrom_context_from_classifier(model_path)
            print(f"📋 Classifier trained on chromosome {chrom}, context {context}")
        except ValueError as e:
            print(f"⚠️ {e}")
            print("Will load all .h5 files (not recommended for mixed datasets)")
            chrom, context = None, None

        # Get feature information
        feature_info = classifier.get_feature_info()
        print(f"📊 Classifier uses {feature_info['n_features']} DMP positions")
        print(f"🎯 First 5 DMP positions: {feature_info['positions'][:5]}")

        # Classify samples from .h5 files
        h5_path = Path(args.h5_path)
        classify_samples_from_h5(classifier, h5_path, chrom, context)

        # Optionally test with random data
        if args.test_random:
            print(f"\n🎲 Testing with {args.test_random} random samples...")
            n_samples = args.test_random
            methylation_data = np.random.beta(2, 2, (n_samples, feature_info['n_features']))

            predictions, probabilities = classify_sample(classifier, methylation_data)

            print("\n📋 Random Sample Test Results:")
            print("-" * 60)
            print(f"{'Sample':<10} {'Class':<8} {'Prob_Class0':<12} {'Prob_Class1':<12}")
            print("-" * 60)

            for i in range(n_samples):
                pred = predictions[i]
                prob = probabilities[i]
                print(f"Random_{i+1:<3} {pred:<8} {prob[0]:<12.4f} {prob[1]:<12.4f}")

            print("-" * 60)

    except FileNotFoundError as e:
        print(f"❌ File not found: {e}")
        print("Make sure the model file exists and the .h5 path contains methylation data files")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure methyl_utils is available for .h5 file loading")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
