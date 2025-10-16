"""
Command-line interface for MethylClassifier
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import Optional
import numpy as np

from .classifier import MethylClassifier
from .data_loader import DataLoader
from .utils import setup_logging, extract_chrom_context_from_classifier


def classify_samples(classifier: MethylClassifier,
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
        # Load single sample
        sample = DataLoader.load_sample(h5_path)
        sample_name = h5_path.parent.name
        samples = [(sample_name, sample)]
    elif h5_path.is_dir():
        samples = DataLoader.load_samples_from_directory(h5_path, chrom, context)
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

    print("\n🤖 Classifying samples...")
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
            positions = sample.positions
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
            'total_positions': len(samples[i][1].positions),
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
  # Classify a single sample
  methyl_classifier --model classifier.pkl --input sample.h5

  # Classify all samples in a directory
  methyl_classifier --model classifier.pkl --input samples/ --output results.csv

  # Classify with debug output
  methyl_classifier --model classifier.pkl --input sample.h5 --debug
        """
    )

    parser.add_argument(
        '--model', '-m',
        required=True,
        type=Path,
        help='Path to trained classifier model (.pkl file)'
    )

    parser.add_argument(
        '--input', '-i',
        required=True,
        type=Path,
        help='Path to input .h5 file or directory containing .h5 files'
    )

    parser.add_argument(
        '--output', '-o',
        type=Path,
        help='Optional output CSV file for classification results'
    )

    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        default=False,
        help='Enable debug output for first sample'
    )

    parser.add_argument(
        '--no-filter',
        action='store_true',
        help='Process all .h5 files without chromosome/context filtering'
    )

    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default='INFO',
        help='Set logging level (default: INFO)'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)

    # Load classifier
    classifier = MethylClassifier()
    classifier.load_classifier(args.model)

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
        classify_samples(
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
