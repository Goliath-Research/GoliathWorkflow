#!/usr/bin/env python3
"""
Beta Classifier - Command Line Tool for Methylation-Based Sample Classification

This command-line tool provides Bayesian classification of methylation samples
using the ProbabilisticBetaClassifier. It can classify individual samples or
batch process multiple samples against trained classifiers.

Usage:
    python beta_classifier.py --model classifier.pkl --input sample.h5
    python beta_classifier.py --model classifier.pkl --input samples/ --output results.csv
    python beta_classifier.py --help

Author: MethylUtils Development Team
"""

import argparse
import pickle
import sys
from pathlib import Path
from typing import List, Tuple, Optional
import numpy as np

# Add methyl_utils to path
sys.path.insert(0, str(Path(__file__).parent))

from methyl_utils import ProbabilisticBetaClassifier, MethylSample, setup_logging

# Module mapping for pickle compatibility
import importlib

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


def load_classifier(model_path: Path) -> ProbabilisticBetaClassifier:
    """Load a trained ProbabilisticBetaClassifier from a pickle file."""
    try:
        with open(model_path, 'rb') as f:
            # Use custom unpickler to handle module mapping
            classifier = CustomUnpickler(f).load()
        print(f"✅ Loaded classifier: {classifier}")
        return classifier
    except Exception as e:
        print(f"❌ Failed to load classifier from {model_path}: {e}")
        sys.exit(1)


def extract_chrom_context_from_classifier(classifier_path: Path) -> Tuple[str, str]:
    """Extract chromosome and context from classifier filename."""
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
        if '-' in part and part.endswith('-CG') or part.endswith('-CHG') or part.endswith('-CHH'):
            parts = part.split('-')
            if len(parts) >= 2:
                chrom = parts[-2]
                context = parts[-1]
                return chrom, context

    raise ValueError(f"Could not extract chromosome and context from {classifier_path}")


def filter_h5_files_by_chrom_context(h5_files: List[Path], chrom: str, context: str) -> List[Path]:
    """
    Filter .h5 files to only include those matching the specified chromosome and context.
    Expects files to be named {prefix}-{chrom}-{context}.h5 (exact chromosome match).
    """
    expected_pattern = f"{chrom}-{context}.h5"
    filtered_files = []

    for h5_file in h5_files:
        # Check if filename exactly matches the pattern
        # This prevents "11-CG.h5" from matching when chrom="1"
        if h5_file.name == expected_pattern:
            filtered_files.append(h5_file)

    return filtered_files


def load_samples_from_directory(h5_dir: Path, chrom: str = None, context: str = None) -> List[Tuple[str, np.ndarray, np.ndarray, str, dict]]:
    """
    Load all .h5 samples from a directory (recursively).
    Returns list of tuples: (sample_name, positions, methylation_levels, sample_type, stats_info)
    """
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
            # Load the sample
            sample = MethylSample.load_from_h5(h5_file)
            
            # Use the new get_methylation_levels() method which automatically handles different sample types
            positions = sample.pos
            methylation_levels = sample.get_methylation_levels()
            
            # Handle NaN values and ensure proper range
            methylation_levels = np.nan_to_num(methylation_levels, nan=0.5)
            methylation_levels = np.clip(methylation_levels, 0.0, 1.0)
            
            # Use parent directory name as sample identifier (e.g., "DBCST-051425-111148")
            sample_name = h5_file.parent.name
            sample_type = sample.sample_type
            
            # Collect statistical information for enhanced analysis
            coverage = sample.get_coverage()
            avg_coverage = np.mean(coverage) if len(coverage) > 0 else 0
            stats_info = {
                'avg_coverage': avg_coverage,
                'total_positions': len(positions),
                'sample_type': sample_type
            }
            
            # Add statistical properties if available (for centroids)
            if sample.is_centroid:
                try:
                    alpha, beta = sample.get_beta_parameters()
                    stats_info.update({
                        'avg_alpha': np.mean(alpha),
                        'avg_beta': np.mean(beta),
                        'avg_tau': np.mean(sample.tau),
                        'avg_variance': np.mean(sample.variance)
                    })
                except Exception as e:
                    # If statistical properties can't be computed, continue without them
                    pass
            
            samples.append((sample_name, positions, methylation_levels, sample_type, stats_info))
            
            # Provide more informative loading message with sample type and coverage info
            print(f"    ✅ Loaded {sample_name} ({sample_type}, avg coverage: {avg_coverage:.1f})")

        except Exception as e:
            sample_name = h5_file.parent.name
            print(f"    ❌ Failed to load {sample_name}: {e}")

    return samples


def extract_dmp_features(classifier: ProbabilisticBetaClassifier,
                        samples: List[Tuple[str, np.ndarray, np.ndarray, str, dict]]) -> Tuple[np.ndarray, np.ndarray, List[str], List[str], List[dict], np.ndarray]:
    """
    Extract DMP features from samples for classification.

    Returns:
        feature_matrix: Shape (n_samples, n_features)
        availability_mask: Shape (n_samples, n_features), True where position is available
        sample_names: List of sample names
        sample_types: List of sample types
        stats_info: List of statistical information dictionaries
        dmp_positions: Array of DMP positions used for classification
    """
    feature_info = classifier.get_feature_info()
    n_dmps = feature_info['n_features']
    dmp_positions = feature_info['positions']

    # Create mapping from position to index for fast lookup
    pos_to_idx = {pos: idx for idx, pos in enumerate(dmp_positions)}

    feature_matrix = []
    availability_mask = []
    sample_names = []
    sample_types = []
    stats_info = []

    for sample_name, positions, methylation_levels, sample_type, stats in samples:
        pos_to_methylation = dict(zip(positions, methylation_levels))
        sample_features = []
        sample_mask = []
        missing_positions = 0

        for dmp_pos in dmp_positions:
            if dmp_pos in pos_to_methylation:
                methylation = pos_to_methylation[dmp_pos]
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
        sample_types.append(sample_type)
        stats_info.append(stats)

        if missing_positions > 0:
            print(f"  ⚠️ {sample_name} ({sample_type}): {missing_positions}/{n_dmps} DMP positions missing")

    return np.array(feature_matrix), np.array(availability_mask), sample_names, sample_types, stats_info, dmp_positions


def classify_sample(classifier: ProbabilisticBetaClassifier,
                   methylation_data: np.ndarray,
                   availability_mask: Optional[np.ndarray] = None,
                   debug: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    """
    Classify a single sample using the trained classifier.

    Args:
        classifier: Trained ProbabilisticBetaClassifier
        methylation_data: Array of methylation values for the DMP positions
                         Shape should be (n_samples, n_features)
        availability_mask: Boolean mask indicating which positions are available
        debug: If True, enable debug output

    Returns:
        predictions: Array of class predictions (0 or 1)
        probabilities: Array of posterior probabilities for each class
    """
    # Ensure data is 2D
    if methylation_data.ndim == 1:
        methylation_data = methylation_data.reshape(1, -1)
    if availability_mask is not None and availability_mask.ndim == 1:
        availability_mask = availability_mask.reshape(1, -1)

    # Get predictions and probabilities
    predictions = classifier.predict(methylation_data, availability_mask, debug)
    probabilities = classifier.predict_proba(methylation_data, availability_mask, debug)

    return predictions, probabilities


def classify_samples_from_h5(classifier: ProbabilisticBetaClassifier,
                           h5_path: Path,
                           chrom: str = None,
                           context: str = None,
                           output_file: Optional[Path] = None,
                           debug: bool = False) -> None:
    """
    Load samples from .h5 files and classify them using the trained classifier.
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
        # Load single sample and get sample type
        sample = MethylSample.load_from_h5(h5_path)
        positions, methylation_levels = load_methylation_sample(h5_path)
        sample_name = h5_path.parent.name
        sample_type = sample.sample_type
        
        # Collect statistical information for enhanced analysis
        coverage = sample.get_coverage()
        avg_coverage = np.mean(coverage) if len(coverage) > 0 else 0
        stats_info = {
            'avg_coverage': avg_coverage,
            'total_positions': len(positions),
            'sample_type': sample_type
        }
        
        # Add statistical properties if available (for centroids)
        if sample.is_centroid:
            try:
                alpha, beta = sample.get_beta_parameters()
                stats_info.update({
                    'avg_alpha': np.mean(alpha),
                    'avg_beta': np.mean(beta),
                    'avg_tau': np.mean(sample.tau),
                    'avg_variance': np.mean(sample.variance)
                })
            except Exception as e:
                # If statistical properties can't be computed, continue without them
                pass
        
        samples = [(sample_name, positions, methylation_levels, sample_type, stats_info)]
    elif h5_path.is_dir():
        samples = load_samples_from_directory(h5_path, chrom, context)
    else:
        raise FileNotFoundError(f"Path not found: {h5_path}")

    print(f"\n📊 Extracting features for {len(samples)} samples...")
    feature_matrix, availability_mask, sample_names, sample_types, stats_info, dmp_positions = extract_dmp_features(classifier, samples)

    print("\n🤖 Classifying samples...")
    predictions, probabilities = classify_sample(classifier, feature_matrix, availability_mask, debug)
    
    # Print classification genes (DMPs) information
    print(f"\n🧬 Classification Genes (DMPs) Information:")
    print(f"Total DMPs in classifier: {len(dmp_positions)}")
    
    # Calculate how many DMPs are actually available for classification
    available_dmps_per_sample = np.sum(availability_mask, axis=1)
    print(f"Average DMPs available per sample: {np.mean(available_dmps_per_sample):.1f}")
    print(f"Min DMPs available: {np.min(available_dmps_per_sample)}")
    print(f"Max DMPs available: {np.max(available_dmps_per_sample)}")
    
    # Show DMP positions (first 20 and last 20)
    print(f"\nFirst 20 DMP positions: {dmp_positions[:20].tolist()}")
    print(f"Last 20 DMP positions: {dmp_positions[-20:].tolist()}")
    
    # Debug position alignment issue
    print(f"\n🔍 Position Alignment Debug:")
    print(f"Classifier DMP positions range: {dmp_positions.min()} to {dmp_positions.max()}")
    
    # Check a few individual samples to see their position ranges
    for i, (name, positions, sample_type) in enumerate(zip(sample_names[:3], [s[1] for s in samples[:3]], sample_types[:3])):
        if len(positions) > 0:
            print(f"  {name} ({sample_type}): {len(positions)} positions, range {positions.min()} to {positions.max()}")
            # Check overlap with classifier DMPs
            overlap = np.intersect1d(positions, dmp_positions)
            print(f"    Overlap with classifier DMPs: {len(overlap)}/{len(dmp_positions)} ({len(overlap)/len(dmp_positions)*100:.1f}%)")
    
    # Check centroids specifically
    centroid_indices = [i for i, st in enumerate(sample_types) if st in ['basic_centroid', 'extended_centroid']]
    for i in centroid_indices:
        name = sample_names[i]
        positions = samples[i][1]  # Get positions from the sample tuple
        if len(positions) > 0:
            print(f"  {name} (centroid): {len(positions)} positions, range {positions.min()} to {positions.max()}")
            overlap = np.intersect1d(positions, dmp_positions)
            print(f"    Overlap with classifier DMPs: {len(overlap)}/{len(dmp_positions)} ({len(overlap)/len(dmp_positions)*100:.1f}%)")
    
    # Save DMP positions to file for analysis
    dmp_file = output_file.parent / "classification_dmps.txt" if output_file else Path("classification_dmps.txt")
    with open(dmp_file, 'w') as f:
        f.write("# Classification DMPs (Differentially Methylated Positions)\n")
        f.write(f"# Total DMPs: {len(dmp_positions)}\n")
        f.write(f"# Chromosome: {chrom if chrom else 'unknown'}\n")
        f.write(f"# Context: {context if context else 'unknown'}\n")
        f.write("# Format: position\n")
        for pos in dmp_positions:
            f.write(f"{pos}\n")
    print(f"💾 DMP positions saved to: {dmp_file}")
    
    # Analyze centroid vs sample classification
    print(f"\n🔍 Classification Analysis by Sample Type:")
    for i, (name, sample_type, pred, prob) in enumerate(zip(sample_names, sample_types, predictions, probabilities)):
        if sample_type in ['basic_centroid', 'extended_centroid']:
            available_dmps = np.sum(availability_mask[i])
            print(f"  {name} ({sample_type}): Class_{pred}, Available DMPs: {available_dmps}/{len(dmp_positions)}")
            
            # Debug centroid methylation levels
            sample_data = feature_matrix[i]
            available_data = sample_data[availability_mask[i]]
            print(f"    Methylation level stats: mean={np.mean(available_data):.3f}, std={np.std(available_data):.3f}")
            print(f"    Methylation level range: [{np.min(available_data):.3f}, {np.max(available_data):.3f}]")
            
            # Check if this centroid should be classified differently
            if 'pb-' in name or 'pp-' in name:
                # Correct class assignments:
                # pb-cancer = Class_0 (Prostate Cancer Buffy Coat)
                # pb-healthy = Class_1 (Healthy Buffy Coat) 
                # pp-cancer = Class_0 (Prostate Cancer Plasma) - should be cancer but model wasn't trained on plasma
                # pp-healthy = Class_1 (Healthy Plasma) - should be healthy but model wasn't trained on plasma
                if 'pb-cancer' in name:
                    expected_class = 0  # Prostate Cancer Buffy Coat
                elif 'pb-healthy' in name:
                    expected_class = 1  # Healthy Buffy Coat
                elif 'pp-cancer' in name:
                    expected_class = 0  # Prostate Cancer Plasma (but model not trained on plasma)
                elif 'pp-healthy' in name:
                    expected_class = 1  # Healthy Plasma (but model not trained on plasma)
                else:
                    expected_class = None
                
                if expected_class is not None:
                    print(f"    Expected class: {expected_class}, Predicted: {pred}, Match: {expected_class == pred}")
                    
                    # Additional debugging for centroid classification issues
                    if expected_class != pred:
                        print(f"    ⚠️ MISCLASSIFICATION: {name} should be Class {expected_class} but predicted as Class {pred}")
                        print(f"    Probabilities: Class0={prob[0]:.6f}, Class1={prob[1]:.6f}")
                        
                        # Check if this is a plasma sample (model not trained on plasma data)
                        if 'pp-' in name:
                            print(f"    Note: This is a plasma sample - model was trained on buffy coat data only")
                        elif 'pb-' in name:
                            print(f"    Note: This is a training centroid - classification may be unreliable")

    # Display results with enhanced information
    print("\n📋 Classification Results:")
    print("-" * 120)
    print(f"{'Sample':<35} {'Type':<12} {'Predicted':<10} {'Prob_Class0':<12} {'Prob_Class1':<12} {'Coverage':<8} {'DMPs':<6}")
    print("-" * 120)

    class_counts = {0: 0, 1: 0}
    sample_type_counts = {}
    results_data = []

    for i, (name, sample_type, pred, prob, stats) in enumerate(zip(sample_names, sample_types, predictions, probabilities, stats_info)):
        predicted_label = "Class_0" if pred == 0 else "Class_1"
        class_counts[pred] += 1
        sample_type_counts[sample_type] = sample_type_counts.get(sample_type, 0) + 1
        
        # Get coverage info for display
        coverage_str = f"{stats.get('avg_coverage', 0):.1f}" if 'avg_coverage' in stats else "N/A"
        
        # Get DMPs used for classification
        dmps_used = np.sum(availability_mask[i])
        dmps_str = f"{dmps_used}/{len(dmp_positions)}"
        
        print(f"{name:<35} {sample_type:<12} {predicted_label:<10} {prob[0]:<12.4f} {prob[1]:<12.4f} {coverage_str:<8} {dmps_str:<6}")

        # Prepare results data with statistical information
        result_entry = {
            'sample': name,
            'sample_type': sample_type,
            'prediction': int(pred),
            'predicted_class': predicted_label,
            'prob_class0': float(prob[0]),
            'prob_class1': float(prob[1]),
            'avg_coverage': stats.get('avg_coverage', 0),
            'total_positions': stats.get('total_positions', 0),
            'dmps_used': int(dmps_used),
            'dmps_total': len(dmp_positions),
            'dmp_coverage_pct': float(dmps_used / len(dmp_positions) * 100)
        }
        
        # Add statistical properties if available
        if 'avg_alpha' in stats:
            result_entry.update({
                'avg_alpha': stats['avg_alpha'],
                'avg_beta': stats['avg_beta'],
                'avg_tau': stats['avg_tau'],
                'avg_variance': stats['avg_variance']
            })
        
        results_data.append(result_entry)

    print("-" * 80)
    print(f"Total samples: {len(samples)}")
    print(f"Class 0: {class_counts[0]} samples")
    print(f"Class 1: {class_counts[1]} samples")
    
    # Display sample type breakdown if we have that information
    if sample_type_counts:
        print("\nSample type breakdown:")
        for sample_type, count in sample_type_counts.items():
            print(f"  {sample_type}: {count} samples")
    
    # Summary and recommendations
    print(f"\n📊 Classification Summary:")
    print(f"  • Total samples classified: {len(samples)}")
    print(f"  • DMPs used for classification: {len(dmp_positions)}")
    print(f"  • Average DMPs available per sample: {np.mean(available_dmps_per_sample):.1f} ({np.mean(available_dmps_per_sample)/len(dmp_positions)*100:.1f}%)")
    print(f"  • Min DMPs available: {np.min(available_dmps_per_sample)} ({np.min(available_dmps_per_sample)/len(dmp_positions)*100:.1f}%)")
    print(f"  • Max DMPs available: {np.max(available_dmps_per_sample)} ({np.max(available_dmps_per_sample)/len(dmp_positions)*100:.1f}%)")
    print(f"  • Classification results: {class_counts[0]} Class 0, {class_counts[1]} Class 1")
    
    # DMP usage by sample type
    print(f"\n📈 DMP Usage by Sample Type:")
    for sample_type in set(sample_types):
        type_indices = [i for i, st in enumerate(sample_types) if st == sample_type]
        type_dmps = available_dmps_per_sample[type_indices]
        print(f"  • {sample_type}: {np.mean(type_dmps):.1f} ± {np.std(type_dmps):.1f} DMPs ({np.mean(type_dmps)/len(dmp_positions)*100:.1f}% ± {np.std(type_dmps)/len(dmp_positions)*100:.1f}%)")
    
    # Check for potential issues
    centroid_samples = [i for i, st in enumerate(sample_types) if st in ['basic_centroid', 'extended_centroid']]
    if centroid_samples:
        print(f"\n⚠️  Note: {len(centroid_samples)} centroid samples detected.")
        print(f"  Centroids may represent training data and classification results should be interpreted carefully.")
        print(f"  Individual samples (not centroids) provide more reliable classification results.")
    
    # Critical issue check: Low DMP coverage
    low_coverage_samples = np.sum(available_dmps_per_sample < len(dmp_positions) * 0.5)  # Less than 50% coverage
    if low_coverage_samples > 0:
        print(f"\n🚨 CRITICAL ISSUE DETECTED:")
        print(f"  {low_coverage_samples} samples have less than 50% DMP coverage!")
        print(f"  This suggests a position alignment problem between samples and classifier.")
        print(f"  Expected: ~100% coverage for samples used to train the classifier.")
        print(f"  This could indicate:")
        print(f"    - Different chromosome/context filtering")
        print(f"    - Position range mismatches")
        print(f"    - Data loading issues")
        print(f"    - File structure problems")

    # Save results if output file specified
    if output_file:
        import csv
        
        # Create output directory if it doesn't exist
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', newline='') as csvfile:
            # Determine fieldnames based on available data
            fieldnames = ['sample', 'sample_type', 'prediction', 'predicted_class', 'prob_class0', 'prob_class1', 'avg_coverage', 'total_positions', 'dmps_used', 'dmps_total', 'dmp_coverage_pct']
            
            # Add statistical fields if any sample has them
            if any('avg_alpha' in result for result in results_data):
                fieldnames.extend(['avg_alpha', 'avg_beta', 'avg_tau', 'avg_variance'])
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results_data)
        print(f"\n💾 Results saved to: {output_file}")


def load_methylation_sample(h5_path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """Load methylation data from a single .h5 file."""
    try:
        sample = MethylSample.load_from_h5(h5_path)
        
        # Use the new get_methylation_levels() method which automatically handles different sample types
        positions = sample.pos
        methylation_levels = sample.get_methylation_levels()
        
        # Handle NaN values and ensure proper range
        methylation_levels = np.nan_to_num(methylation_levels, nan=0.5)
        methylation_levels = np.clip(methylation_levels, 0.0, 1.0)

        return positions, methylation_levels
    except Exception as e:
        raise RuntimeError(f"Failed to load {h5_path}: {e}")


def main():
    """Main command-line interface."""
    parser = argparse.ArgumentParser(
        description="Beta Classifier - Bayesian classification of methylation samples",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Classify a single sample
  python beta_classifier.py --model classifier.pkl --input sample.h5

  # Classify all samples in a directory
  python beta_classifier.py --model classifier.pkl --input samples/ --output results.csv

  # Classify with debug output
  python beta_classifier.py --model classifier.pkl --input sample.h5 --debug
        """
    )

    parser.add_argument(
        '--model', '-m',
        required=False,
        type=Path,
        default=Path('/home/ubuntu/Work/samples/humans/psomagen/AN00025834/data/detection/single/pb-ch-2-CG/methyl_detector_classifier.pkl'),       
        help='Path to trained classifier model (.pkl file)'
    )

    parser.add_argument(
        '--input', '-i',
        required=False,
        type=Path,
        default=Path('/home/ubuntu/Work/samples/humans/psomagen/AN00025834/data'),
        help='Path to input .h5 file or directory containing .h5 files'
    )

    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=Path('/home/ubuntu/Work/samples/humans/psomagen/AN00025834/data/classification/single/pb-ch-2-CG/classification_results.CSV'),
        help='Optional output CSV file for classification results'
    )

    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        default=True,
        help='Enable debug output for first sample'
    )

    parser.add_argument(
        '--no-filter',
        action='store_true',
        help='Process all .h5 files without chromosome/context filtering'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging()

    # Load classifier
    classifier = load_classifier(args.model)

    # Extract chromosome and context from classifier path (unless disabled)
    chrom, context = None, None
    if not args.no_filter:
        try:
            chrom, context = extract_chrom_context_from_classifier(args.model)
            print(f"📋 Classifier trained on chromosome {chrom}, context {context}")
        except ValueError as e:
            print(f"⚠️ {e}")
            print("Will process all .h5 files (use --no-filter to suppress this warning)")

    # Classify samples
    try:
        classify_samples_from_h5(
            classifier=classifier,
            h5_path=args.input,
            chrom=chrom,
            context=context,
            output_file=args.output,
            debug=args.debug
        )
    except Exception as e:
        print(f"❌ Classification failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
