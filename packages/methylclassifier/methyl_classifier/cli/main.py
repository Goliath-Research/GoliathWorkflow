"""
Command-line interface for MethylClassifier
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
import numpy as np
import json # Added for loading config file

from ..core.classifier import MethylClassifier
from ..utils.data_loader import DataLoader
from ..utils.utils import extract_chrom_context_from_classifier, setup_logging
from ..models.config_schema import ClassificationConfig
from ..models.config import ClassifierConfig


def classify_samples(classifier: MethylClassifier,
                    h5_path: Optional[Path] = None,
                    samples_list: Optional[List[str]] = None,
                    chrom: str = None,
                    context: str = None,
                    output_file: Optional[Path] = None,
                    debug: bool = False) -> None:
    """
    Load samples from .h5 files and classify them using the trained classifier.
    
    Supports:
    - Single .h5 file via h5_path
    - Directory of .h5 files via h5_path
    - List of sample directories (each with {chrom}-CG.h5, {chrom}-CHG.h5, {chrom}-CHH.h5) via samples_list
    """
    # Handle samples list (multi-chromosome with merged contexts)
    if samples_list:
        return classify_samples_from_list(classifier, samples_list, output_file, debug)
    
    # Legacy: single file or directory
    if h5_path is None:
        raise ValueError("Either h5_path or samples_list must be provided")
    
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
        # Load single sample
        sample = DataLoader.load_sample(h5_path, debug)
        sample_name = h5_path.parent.name
        samples = [(sample_name, sample)]
    elif h5_path.is_dir():
        samples = DataLoader.load_samples_from_directory(h5_path, chrom, context, debug)
    else:
        raise FileNotFoundError(f"Path not found: {h5_path}")

    print(f"\n📊 Extracting features for {len(samples)} samples...")

    # Get classifier feature information
    feature_info = classifier.get_feature_info()
    n_dmps = feature_info['n_features']
    dmp_positions = feature_info['positions']

    # Extract features for all samples
    feature_matrix = []
    availability_mask = []
    sample_names = []
    sample_types = []
    stats_info = []

    for sample_name, sample in samples:
        features, mask, stats = DataLoader.extract_sample_features(sample, dmp_positions)

        feature_matrix.append(features)
        availability_mask.append(mask)
        sample_names.append(sample_name)
        sample_types.append(sample.sample_type)
        stats_info.append(stats)

        missing_positions = stats['missing_positions']
        if missing_positions > 0:
            print(f"  ⚠️ {sample_name} ({sample.sample_type}): {missing_positions}/{n_dmps} DMP positions missing")

    feature_matrix = np.array(feature_matrix)
    availability_mask = np.array(availability_mask)

    # Display prediction method
    print(f"\n🤖 Classifying samples using Beta prediction method...")
    
    predictions, probabilities = classify_samples_batch(
        classifier, feature_matrix, availability_mask, debug
    )

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
    if debug:
        print(f"\n🔍 Position Alignment Debug:")
        print(f"Classifier DMP positions range: {dmp_positions.min()} to {dmp_positions.max()}")

        # Check a few individual samples to see their position ranges
        for i, (name, (_, sample)) in enumerate(zip(sample_names[:3], samples[:3])):
            positions = sample.pos
            if len(positions) > 0:
                print(f"  {name} ({sample.sample_type}): {len(positions)} positions, range {positions.min()} to {positions.max()}")
                # Check overlap with classifier DMPs
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
    if debug:
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

    # Create dynamic header based on number of classes
    prob_headers = [f"Prob_Class{i}" for i in range(classifier.n_classes)]
    header_parts = ["Sample", "Type", "Predicted"] + prob_headers + ["Coverage", "DMPs"]
    col_widths = [35, 12, 10] + [12] * classifier.n_classes + [8, 6]  # Column widths

    header_line = ""
    for part, width in zip(header_parts, col_widths):
        header_line += f"{part:<{width}} "
    header_width = len(header_line)

    print("-" * header_width)
    print(header_line)
    print("-" * header_width)

    class_counts = {i: 0 for i in range(classifier.n_classes)}
    sample_type_counts = {}
    results_data = []

    for i, (name, sample_type, pred, prob, stats) in enumerate(zip(sample_names, sample_types, predictions, probabilities, stats_info)):
        if classifier.class_names is not None and pred < len(classifier.class_names):
            predicted_label = str(classifier.class_names[pred])
        else:
            predicted_label = f"Class_{pred}"

        class_counts[pred] += 1
        sample_type_counts[sample_type] = sample_type_counts.get(sample_type, 0) + 1

        # Get coverage info for display
        coverage_str = f"{stats.get('avg_coverage', 0):.1f}" if 'avg_coverage' in stats else "N/A"

        # Get DMPs used for classification
        dmps_used = np.sum(availability_mask[i])
        dmps_str = f"{dmps_used}/{len(dmp_positions)}"

        # Format probabilities for all classes
        prob_strings = [f"{prob[j]:.4f}" for j in range(classifier.n_classes)]
        row_parts = [name, sample_type, predicted_label] + prob_strings + [coverage_str, dmps_str]

        row_line = ""
        for part, width in zip(row_parts, col_widths):
            row_line += f"{part:<{width}} "
        print(row_line)

        # Prepare results data with statistical information
        result_entry = {
            'sample': name,
            'sample_type': sample_type,
            'prediction': int(pred),
            'predicted_class': predicted_label,
            'avg_coverage': stats.get('avg_coverage', 0),
            'total_positions': len(samples[i][1].pos),
            'dmps_used': int(dmps_used),
            'dmps_total': len(dmp_positions),
            'dmp_coverage_pct': float(dmps_used / len(dmp_positions) * 100)
        }

        # Add probabilities for all classes
        for j in range(classifier.n_classes):
            result_entry[f'prob_class{j}'] = float(prob[j])

        # Add statistical properties if available
        if 'avg_alpha' in stats:
            result_entry.update({
                'avg_alpha': stats['avg_alpha'],
                'avg_beta': stats['avg_beta'],
                'avg_tau': stats['avg_tau'],
                'avg_variance': stats['avg_variance']
            })

        results_data.append(result_entry)

    print("-" * header_width)
    print(f"Total samples: {len(samples)}")
    for i in range(classifier.n_classes):
        class_name = classifier.class_names[i] if classifier.class_names is not None and i < len(classifier.class_names) else f"Class {i}"
        print(f"{class_name}: {class_counts[i]} samples")

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
    # Display classification results summary
    result_summary = []
    for i in range(classifier.n_classes):
        class_name = classifier.class_names[i] if classifier.class_names is not None and i < len(classifier.class_names) else f"Class {i}"
        result_summary.append(f"{class_counts[i]} {class_name}")
    print(f"  • Classification results: {', '.join(result_summary)}")

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
            fieldnames = ['sample', 'sample_type', 'prediction', 'predicted_class'] + [f'prob_class{i}' for i in range(classifier.n_classes)] + ['avg_coverage', 'total_positions', 'dmps_used', 'dmps_total', 'dmp_coverage_pct']

            # Add statistical fields if any sample has them
            if any('avg_alpha' in result for result in results_data):
                fieldnames.extend(['avg_alpha', 'avg_beta', 'avg_tau', 'avg_variance'])

            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results_data)
        print(f"\n💾 Results saved to: {output_file}")


def classify_samples_from_list(
    classifier: MethylClassifier,
    samples_list: List[str],
    output_file: Optional[Path] = None,
    debug: bool = False,
    required_chromosomes: Optional[List[str]] = None,
    positions: Optional[np.ndarray] = None,
    dmp_positions_by_chrom: Optional[Dict[str, np.ndarray]] = None
) -> None:
    """
    Classify samples from a list of directories, merging CG, CHG, CHH contexts.

    Each directory should contain {chrom}-CG.h5, {chrom}-CHG.h5, {chrom}-CHG.h5 files.
    Contexts are merged per chromosome before classification.

    Args:
        classifier: MethylClassifier instance (single or multi-chromosome)
        samples_list: List of sample directory paths
        output_file: Optional output CSV file
        debug: Enable debug output
        required_chromosomes: Only load these chromosomes (performance optimization)
        positions: Only load these positions (ultra-performance optimization)
        dmp_positions_by_chrom: DMP positions organized by chromosome (chromosome-specific optimization)
    """
    print(f"\n🔍 Loading {len(samples_list)} samples from directories...")
    
    # Load samples (merged contexts per chromosome)
    loaded_samples = DataLoader.load_samples_from_list(
        samples_list, debug=debug, required_chromosomes=required_chromosomes,
        positions=positions, dmp_positions_by_chrom=dmp_positions_by_chrom
    )
    
    if not loaded_samples:
        raise ValueError("No samples loaded from provided paths")
    
    if classifier.is_multi_chromosome:
        # Multi-chromosome mode: extract features per chromosome and combine
        _classify_multi_chromosome_samples(classifier, loaded_samples, output_file, debug)
    else:
        # Single chromosome mode: use first chromosome from merged samples
        # Extract chromosome from classifier
        classifier_chrom = classifier.chromosome
        
        if classifier_chrom == 'unknown':
            # Try to infer from available chromosomes
            available_chroms = set()
            for _, chrom_samples in loaded_samples:
                available_chroms.update(chrom_samples.keys())
            
            if not available_chroms:
                raise ValueError("No chromosomes found in loaded samples")
            
            classifier_chrom = sorted(available_chroms)[0]
            print(f"⚠️ Classifier chromosome unknown, using first available: {classifier_chrom}")
        
        # Convert to single-sample format
        single_samples = []
        for sample_name, chrom_samples in loaded_samples:
            if classifier_chrom in chrom_samples:
                single_samples.append((sample_name, chrom_samples[classifier_chrom]))
            else:
                print(f"⚠️ Sample {sample_name}: chromosome {classifier_chrom} not found, skipping")
        
        if not single_samples:
            raise ValueError(f"No samples found with chromosome {classifier_chrom}")
        
        # Use existing single-chromosome classification
        feature_info = classifier.get_feature_info()
        dmp_positions = feature_info['positions']
        
        feature_matrix = []
        availability_mask = []
        sample_names = []
        
        for sample_name, sample in single_samples:
            features, mask, stats = DataLoader.extract_sample_features(sample, dmp_positions)
            feature_matrix.append(features)
            availability_mask.append(mask)
            sample_names.append(sample_name)
        
        feature_matrix = np.array(feature_matrix)
        availability_mask = np.array(availability_mask)
        
        predictions, probabilities = classify_samples_batch(
            classifier, feature_matrix, availability_mask, debug
        )
        
        # Save results
        _save_classification_results(
            classifier, sample_names, predictions, probabilities, 
            availability_mask, dmp_positions, output_file
        )


def _classify_multi_chromosome_samples(
    classifier: MethylClassifier,
    loaded_samples: List[Tuple[str, Dict[str, Any]]],
    output_file: Optional[Path] = None,
    debug: bool = False
) -> None:
    """
    Classify samples using multi-chromosome classifier.
    
    Extracts features per chromosome from merged samples and combines predictions.
    """
    print(f"\n📊 Extracting features per chromosome for {len(loaded_samples)} samples...")
    
    # Get all chromosomes from classifier
    classifier_chroms = sorted(classifier.classifiers.keys())
    
    # Collect features per chromosome
    chrom_features = {chrom: [] for chrom in classifier_chroms}
    chrom_masks = {chrom: [] for chrom in classifier_chroms}
    sample_names = []
    
    for sample_name, chrom_samples in loaded_samples:
        sample_names.append(sample_name)
        
        # Extract features for each chromosome
        for chrom in classifier_chroms:
            if chrom in chrom_samples:
                # Get this chromosome's classifier feature info
                chrom_classifier = classifier.classifiers[chrom]
                feature_info = chrom_classifier.get_feature_info()
                dmp_positions = feature_info['positions']
                
                # Extract features from merged sample for this chromosome
                sample = chrom_samples[chrom]
                features, mask, _ = DataLoader.extract_sample_features(sample, dmp_positions)
                
                chrom_features[chrom].append(features)
                chrom_masks[chrom].append(mask)
            else:
                # Missing chromosome: use zeros with all unavailable
                feature_info = classifier.classifiers[chrom].get_feature_info()
                n_dmps = feature_info['n_features']
                chrom_features[chrom].append(np.zeros(n_dmps))
                chrom_masks[chrom].append(np.zeros(n_dmps, dtype=bool))
                if debug:
                    print(f"  ⚠️ Sample {sample_name}: missing chromosome {chrom}")
    
    # Convert to arrays per chromosome
    for chrom in classifier_chroms:
        chrom_features[chrom] = np.array(chrom_features[chrom])
        chrom_masks[chrom] = np.array(chrom_masks[chrom])
    
    # Get combined predictions from multi-chromosome classifier
    # We need to concatenate all chromosome features for the classifier
    # But the current implementation expects concatenated data, which is complex
    # Let's use a simpler approach: run each chromosome classifier separately and combine
    
    print(f"\n🤖 Classifying using {len(classifier_chroms)} chromosome classifier(s)...")
    
    n_samples = len(sample_names)
    n_classes = classifier.n_classes
    
    # Initialize weighted probability sum
    weighted_probas = np.zeros((n_samples, n_classes))
    
    for chrom in classifier_chroms:
        weight = classifier.chromosome_weights.get(chrom, 0.0)
        
        if weight == 0.0:
            continue
        
        chrom_classifier = classifier.classifiers[chrom]
        
        # Get probabilities from this chromosome
        try:
            chrom_probas = chrom_classifier.predict_proba(
                chrom_features[chrom],
                chrom_masks[chrom],
                debug=False
            )
            
            # Weight and accumulate
            weighted_probas += weight * chrom_probas
            
            if debug:
                print(f"  Chromosome {chrom} (weight={weight:.4f}): avg probas={np.mean(chrom_probas, axis=0)}")
        except Exception as e:
            if debug:
                print(f"  ⚠️ Chromosome {chrom} prediction failed: {e}")
            continue
    
    # Normalize probabilities
    proba_sums = np.sum(weighted_probas, axis=1, keepdims=True)
    proba_sums = np.where(proba_sums == 0, 1.0, proba_sums)
    probabilities = weighted_probas / proba_sums
    
    # Get predictions
    predictions = np.argmax(probabilities, axis=1)
    
    # Get combined feature info for output
    first_chrom = classifier_chroms[0]
    feature_info = classifier.classifiers[first_chrom].get_feature_info()
    dmp_positions = feature_info['positions']  # Just for display, actual DMPs are per-chromosome
    
    # Create combined availability mask (any chromosome available)
    combined_mask = np.zeros((n_samples, len(dmp_positions)), dtype=bool)
    for chrom in classifier_chroms:
        if chrom in chrom_masks and len(chrom_masks[chrom]) > 0:
            # Merge masks (simplified - just use first chromosome's mask structure)
            if combined_mask.shape[1] == chrom_masks[chrom].shape[1]:
                combined_mask |= chrom_masks[chrom]
    
    # Save results
    _save_classification_results(
        classifier, sample_names, predictions, probabilities,
        combined_mask, dmp_positions, output_file,
        multi_chromosome=True, chromosomes=classifier_chroms
    )


def _save_classification_results(
    classifier: MethylClassifier,
    sample_names: List[str],
    predictions: np.ndarray,
    probabilities: np.ndarray,
    availability_mask: np.ndarray,
    dmp_positions: np.ndarray,
    output_file: Optional[Path],
    multi_chromosome: bool = False,
    chromosomes: Optional[List[str]] = None
) -> None:
    """Helper to save classification results to CSV."""
    if output_file is None:
        return
    
    import csv
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Prepare results data
    results_data = []
    
    for i, (name, pred, prob) in enumerate(zip(sample_names, predictions, probabilities)):
        if classifier.class_names is not None and pred < len(classifier.class_names):
            predicted_label = str(classifier.class_names[pred])
        else:
            predicted_label = f"Class_{pred}"
        
        dmps_used = np.sum(availability_mask[i]) if i < len(availability_mask) else 0
        
        result_entry = {
            'sample': name,
            'prediction': int(pred),
            'predicted_class': predicted_label,
        }
        
        # Add probabilities for all classes
        for j in range(classifier.n_classes):
            result_entry[f'prob_class{j}'] = float(prob[j])
        
        result_entry.update({
            'dmps_used': int(dmps_used),
            'dmps_total': len(dmp_positions)
        })
        
        if multi_chromosome and chromosomes:
            result_entry['chromosomes'] = ','.join(chromosomes)
        
        results_data.append(result_entry)
    
    # Write CSV
    fieldnames = ['sample', 'prediction', 'predicted_class'] + \
                 [f'prob_class{i}' for i in range(classifier.n_classes)] + \
                 ['dmps_used', 'dmps_total']
    
    if multi_chromosome and chromosomes:
        fieldnames.append('chromosomes')
    
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results_data)
    
    print(f"\n💾 Results saved to: {output_file}")


def classify_samples_batch(classifier: MethylClassifier,
                          methylation_data: np.ndarray,
                          availability_mask: Optional[np.ndarray] = None,
                          debug: bool = False):
    """
    Classify a batch of samples using the trained classifier.

    Args:
        classifier: Trained MethylClassifier
        methylation_data: Array of methylation values for the DMP positions
                         Shape should be (n_samples, n_features)
        availability_mask: Boolean mask indicating which positions are available
        debug: If True, enable debug output

    Returns:
        predictions: Array of class predictions (0 or 1)
        probabilities: Array of posterior probabilities for each class
    """
    # Get predictions and probabilities
    predictions = classifier.predict(methylation_data, availability_mask, debug)
    probabilities = classifier.predict_proba(methylation_data, availability_mask, debug)

    return predictions, probabilities


def main():
    """Main command-line interface."""
    parser = argparse.ArgumentParser(
        description="MethylClassifier - Bayesian classification of methylation samples",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using config file (recommended)
  methyl_classifier --config classification_config.json

  # Direct arguments
  methyl_classifier --model classifier.pkl --input samples/ --output results.csv

Config fields (in JSON):
  {
    "model_path": "models/classifier-1-CG.pkl",
    "model_dir": null,
    "input_path": "samples/",
    "output_path": "results.csv",
    "temperature": 1.0,
    "enable_platt_calibration": false,
    "trimmed_percentile_low": 0.10,
    "trimmed_percentile_high": 0.01,
    "chromosome_weights": null,
    "debug": false,
    "no_filter": false,
    "log_level": "INFO"
  }
        """
    )
    
    # Required/optional args (keep existing, remove new ones)
    parser.add_argument(
        '--config', '-c',
        type=Path,
        help='Path to configuration JSON file (includes all params like temperature/calibration)'
    )
    
    parser.add_argument(
        '--model', '-m',
        type=Path,
        help='Path to trained classifier model (.pkl file) - overrides config if provided'
    )
    
    parser.add_argument(
        '--model-dir', '-M',
        type=Path,
        help='Path to directory containing classifier-{chrom}.pkl files (multi-chromosome mode)'
    )
    
    parser.add_argument(
        '--input', '-i',
        type=Path,
        help='Path to input .h5 file or directory - overrides config if provided'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=Path,
        help='Optional output CSV file - overrides config if provided'
    )
    
    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        default=False,
        help='Enable debug output'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default='INFO',
        help='Set logging level (default: INFO)'
    )
    
    # No new args for temperature/calibration - handled in config
    
    args = parser.parse_args()
    
    # Load config if provided
    if args.config:
        with open(args.config, 'r') as f:
            config_data = json.load(f)
        config = ClassificationConfig(**config_data)
        # Override with CLI args (model, model_dir, input, output, etc.)
        if args.model:
            config.model_path = str(args.model)
        if args.model_dir:
            config.model_dir = str(args.model_dir)
        if args.input:
            config.input_path = str(args.input)
        if args.output:
            config.output_path = str(args.output)
        # No overrides for temperature/calibration - use config values
    else:
        # Construct config from CLI args (existing logic)
        config = ClassificationConfig(
            model_path=str(args.model),
            input_path=str(args.input),
            output_path=str(args.output) if args.output else None,
            debug=args.debug,
            log_level=args.log_level
        )
        # Defaults for new params
        config.temperature = 1.0
        config.enable_platt_calibration = False
    
    # Setup logging
    setup_logging(config.log_level)
    
    # Convert ClassificationConfig to ClassifierConfig for MethylClassifier
    classifier_config = ClassifierConfig(
        model_path=config.model_path,
        model_dir=config.model_dir,
        temperature=config.temperature,
        enable_platt_calibration=config.enable_platt_calibration,
        trimmed_percentile_low=config.trimmed_percentile_low,
        trimmed_percentile_high=config.trimmed_percentile_high,
        chromosome_weights=config.chromosome_weights
    )
    
    # Create classifier
    classifier = MethylClassifier(classifier_config)
    
    # Extract chromosome and context from classifier path (unless disabled or multi-chromosome mode)
    chrom, context = None, None
    if not config.no_filter and not classifier.is_multi_chromosome:
        # Only try to extract chrom/context for single-file mode
        model_path_str = config.model_dir or config.model_path
        if model_path_str:
            try:
                chrom, context = extract_chrom_context_from_classifier(Path(model_path_str))
                print(f"📋 Classifier trained on chromosome {chrom}, context {context}")
            except ValueError as e:
                print(f"⚠️ {e}")
                print("Will process all .h5 files (use --no-filter to suppress this warning)")
    elif classifier.is_multi_chromosome:
        print(f"📋 Multi-chromosome classifier mode: {len(classifier.classifiers)} chromosomes")

    # Classify samples using Beta method
    try:
        # Handle samples list (with context merging)
        if config.samples:
            # For multi-chromosome classifiers, only load required chromosomes and positions for performance
            required_chromosomes = None
            positions = None
            dmp_positions_by_chrom = None
            if classifier.is_multi_chromosome:
                required_chromosomes = list(classifier.classifiers.keys())
                positions = getattr(classifier, 'all_dmp_positions', None)
                dmp_positions_by_chrom = getattr(classifier, 'dmp_positions_by_chrom', None)
                print(f"🚀 Performance optimization: only loading {len(required_chromosomes)} required chromosomes per sample")
                if positions is not None:
                    print(f"💎 DMP filtering: {len(positions)} positions will be extracted from loaded data")
            if dmp_positions_by_chrom:
                total_dmps = sum(len(positions) for positions in dmp_positions_by_chrom.values())
                print(f"📊 DMP breakdown: {dict((k, len(v)) for k, v in dmp_positions_by_chrom.items() if len(v) > 0)}")

            classify_samples_from_list(
                classifier=classifier,
                samples_list=config.samples,
                output_file=Path(config.output_path) if config.output_path else None,
                debug=config.debug,
                required_chromosomes=required_chromosomes,
                positions=positions,
                dmp_positions_by_chrom=dmp_positions_by_chrom
            )
        else:
            # Legacy: single path
            classify_samples(
                classifier=classifier,
                h5_path=Path(config.input_path) if config.input_path else None,
                chrom=chrom,
                context=context,
                output_file=Path(config.output_path) if config.output_path else None,
                debug=config.debug
            )
    except Exception as e:
        print(f"❌ Classification failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
