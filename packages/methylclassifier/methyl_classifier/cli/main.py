"""
Command-line interface for MethylClassifier
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any, Union
import numpy as np
import pandas as pd

from ..core.classifier import MethylClassifier
from ..utils.data_loader import DataLoader
from ..utils.utils import extract_chrom_context_from_classifier, setup_logging
from ..models.config_schema import ClassificationConfig
from ..models.config import ClassifierConfig
from ..project_resolver import resolve_classifier_config, resolve_classifier_config_per_cancer_group

try:
    from methyl_utils import load_project
except ImportError:
    load_project = None  # type: ignore[misc, assignment]


def _remap_centroid_path(path: str, path_remap: Optional[Dict[str, str]], sample_root: Optional[Path]) -> str:
    """Apply path_remap (prefix replacement) or sample_root/basename. path_remap takes precedence."""
    if path_remap:
        # Longest matching prefix so /a/b/c matches /a/b before /a
        best_old: Optional[str] = None
        for old_prefix in path_remap:
            if path.startswith(old_prefix) and (best_old is None or len(old_prefix) > len(best_old)):
                best_old = old_prefix
        if best_old is not None:
            new_prefix = path_remap[best_old]
            rest = path[len(best_old):].lstrip("/")
            return f"{new_prefix.rstrip('/')}/{rest}" if rest else new_prefix.rstrip("/")
    if sample_root is not None:
        return str(sample_root / Path(path).name)
    return path


def _read_samples_used_from_centroid_dir(
    centroid_dir: Path,
    sample_root: Optional[Union[str, Path]] = None,
    path_remap: Optional[Dict[str, str]] = None
) -> List[str]:
    """
    Read union of 'samples_used' from all H5 files in a centroid output directory.
    Each centroid file (e.g. per chromosome/context) may list a subset; we return
    the deduplicated union so all samples that contributed to any centroid are included.
    Remapping (when data moved to NAS): if path_remap is set, replace longest matching
    old_prefix with new_prefix; else if sample_root is set, use sample_root / basename(path).
    """
    import h5py
    seen = set()
    result = []
    root = Path(sample_root) if sample_root else None
    for h5_path in sorted(centroid_dir.glob("*.h5")):
        try:
            with h5py.File(h5_path, "r") as f:
                raw = f.attrs.get("samples_used")
                if raw is None:
                    continue
                if isinstance(raw, (bytes, str)):
                    raw = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                    raw = json.loads(raw)
                for p in raw:
                    path = p if isinstance(p, str) else str(p)
                    if not path:
                        continue
                    path = _remap_centroid_path(path, path_remap, root)
                    if path not in seen:
                        seen.add(path)
                        result.append(path)
        except Exception:
            continue
    return result


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

    if not samples:
        raise ValueError("No samples loaded. Check that input path contains .h5 files and that paths are correct.")

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
    dmp_positions_by_chrom: Optional[Union[Dict[str, np.ndarray], pd.DataFrame]] = None,
    expected_classes: Optional[List[int]] = None
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
        expected_classes: Optional list of expected class (0/1) per sample; when set, CSV gets expected_class column and a summary is printed (centroid validation).
    """
    print(f"\n🔍 Loading {len(samples_list)} samples from directories...")
    
    # Use DataFrame directly from classifier if available (faster than building dict)
    # Otherwise build from classifiers for backward compatibility
    if dmp_positions_by_chrom is None:
        if hasattr(classifier, 'dmp_positions_df') and len(classifier.dmp_positions_df) > 0:
            # Use DataFrame directly (optimized format)
            dmp_positions_by_chrom = classifier.dmp_positions_df
        else:
            # Fallback: build dictionary (legacy)
            dmp_positions_by_chrom = {}
            if classifier.is_multi_chromosome:
                for chrom, chrom_classifier in classifier.classifiers.items():
                    feature_info = chrom_classifier.get_feature_info()
                    dmp_positions_by_chrom[chrom] = feature_info['positions']
            else:
                if classifier.classifier is not None:
                    feature_info = classifier.classifier.get_feature_info()
                    # For single chromosome, use classifier's chromosome
                    chrom = classifier.chromosome if classifier.chromosome != 'unknown' else '1'
                    dmp_positions_by_chrom[chrom] = feature_info['positions']
    
    # When model is CG-only (e.g. MethylDetector with contexts: ["CG"]), load only CG to match training
    contexts_to_load = getattr(classifier, 'model_contexts', None)
    if contexts_to_load == ['CG']:
        print("📌 Model is CG-only: loading only CG context from samples (no CHG/CHH merge)", flush=True)

    # Load samples (merged contexts per chromosome, or single context when model is CG-only)
    loaded_samples = DataLoader.load_samples_from_list(
        samples_list, debug=debug, required_chromosomes=required_chromosomes,
        positions=positions, dmp_positions_by_chrom=dmp_positions_by_chrom,
        contexts_to_load=contexts_to_load
    )
    
    if not loaded_samples:
        raise ValueError("No samples loaded from provided paths")
    
    if classifier.is_multi_chromosome:
        # Multi-chromosome mode: extract features per chromosome and combine
        _classify_multi_chromosome_samples(
            classifier, loaded_samples, output_file, debug,
            expected_classes=expected_classes
        )
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
            availability_mask, dmp_positions, output_file,
            expected_classes=expected_classes
        )
        if expected_classes is not None and len(expected_classes) == len(sample_names):
            _print_validation_report(classifier, sample_names, predictions, probabilities, expected_classes)


def _classify_multi_chromosome_samples(
    classifier: MethylClassifier,
    loaded_samples: List[Tuple[str, Dict[str, Any]]],
    output_file: Optional[Path] = None,
    debug: bool = False,
    expected_classes: Optional[List[int]] = None
) -> None:
    """
    Classify samples using multi-chromosome classifier.

    Extracts features per chromosome from merged samples and combines predictions.
    Optionally saves per-chromosome probabilities to a matrix file.
    When expected_classes is provided (centroid validation), adds expected_class column and prints summary.
    """
    print(f"\n📊 Extracting features per chromosome for {len(loaded_samples)} samples...")
    
    # Get all chromosomes from classifier
    classifier_chroms = sorted(classifier.classifiers.keys())
    
    # Collect features per chromosome
    chrom_features = {chrom: [] for chrom in classifier_chroms}
    chrom_masks = {chrom: [] for chrom in classifier_chroms}
    sample_names = []
    
    # Use DataFrame directly from classifier if available (faster)
    if hasattr(classifier, 'dmp_positions_df') and len(classifier.dmp_positions_df) > 0:
        dmp_positions_by_chrom = classifier.dmp_positions_df
    else:
        # Fallback: build dictionary (legacy)
        dmp_positions_by_chrom = {}
        for chrom in classifier_chroms:
            chrom_classifier = classifier.classifiers[chrom]
            feature_info = chrom_classifier.get_feature_info()
            dmp_positions_by_chrom[chrom] = feature_info['positions']
    
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
    
    # If weight_method is a fitted method and we have validation labels, fit weights from per-chromosome probas
    weight_method = getattr(classifier.config, "weight_method", None)
    fitted_methods = ("linear_fitted", "logistic_fitted", "elasticnet_fitted")
    if (
        weight_method in fitted_methods
        and expected_classes is not None
        and len(expected_classes) == len(loaded_samples)
        and len(loaded_samples) >= 2
    ):
        n_samples = len(loaded_samples)
        chrom_proba_matrix = np.zeros((n_samples, len(classifier_chroms)), dtype=np.float64)
        for i, chrom in enumerate(classifier_chroms):
            chrom_classifier = classifier.classifiers[chrom]
            chrom_probas = chrom_classifier.predict_proba(
                chrom_features[chrom], chrom_masks[chrom], debug=False
            )
            # P(class1) for binary; column index 1
            chrom_proba_matrix[:, i] = chrom_probas[:, 1] if chrom_probas.shape[1] > 1 else chrom_probas[:, 0]
        reg = getattr(classifier.config, "weight_fit_regularization", None) or "none"
        alpha = getattr(classifier.config, "weight_fit_alpha", 1.0)
        l1_ratio = getattr(classifier.config, "weight_fit_l1_ratio", 0.5)
        method = "linear" if weight_method == "linear_fitted" else ("logistic" if weight_method == "logistic_fitted" else "elasticnet")
        classifier.fit_chromosome_weights(
            chrom_proba_matrix,
            np.array(expected_classes, dtype=np.float64),
            method=method,
            regularization=reg,
            alpha=alpha,
            l1_ratio=l1_ratio,
        )
    
    # Get combined predictions from multi-chromosome classifier
    # We need to concatenate all chromosome features for the classifier
    # But the current implementation expects concatenated data, which is complex
    # Let's use a simpler approach: run each chromosome classifier separately and combine
    
    print(f"\n🤖 Classifying using {len(classifier_chroms)} chromosome classifier(s)...")
    
    n_samples = len(sample_names)
    n_classes = classifier.n_classes
    
    # Initialize weighted probability sum
    weighted_probas = np.zeros((n_samples, n_classes))

    # Initialize chromosome probability matrix if requested
    chrom_proba_matrix = None
    chromosome_matrix_file = None
    if classifier.config.chromosome_matrix_path is not None:
        chromosome_matrix_file = Path(classifier.config.chromosome_matrix_path)
        chrom_proba_matrix = np.zeros((n_samples, len(classifier_chroms)))

    for i, chrom in enumerate(classifier_chroms):
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

            # Store per-chromosome probabilities for matrix (using class 0 probability)
            if chrom_proba_matrix is not None:
                chrom_proba_matrix[:, i] = chrom_probas[:, 0]

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

    # Diagnostic summary (helps spot collapse to one class)
    prob_c0 = probabilities[:, 0]
    prob_c1 = probabilities[:, 1]
    n_uncertain = np.sum((prob_c1 > 0.05) & (prob_c1 < 0.95))
    print(f"\n📈 Probability summary: P(class0) mean={prob_c0.mean():.3f} min={prob_c0.min():.3f} max={prob_c0.max():.3f} | "
          f"P(class1) mean={prob_c1.mean():.3f} min={prob_c1.min():.3f} max={prob_c1.max():.3f} | "
          f"Samples with 0.05<P(class1)<0.95: {n_uncertain}/{n_samples}")
    if n_uncertain < 0.05 * n_samples and n_samples > 10:
        print("   ⚠️ Most predictions are near 0 or 1. If unexpected, check: DMP coverage (dmps_used in CSV), "
              "temperature in config, or run with --debug.")

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
        multi_chromosome=True, chromosomes=classifier_chroms,
        expected_classes=expected_classes
    )

    # Centroid validation summary (binary or multiclass)
    if expected_classes is not None and len(expected_classes) == n_samples:
        _print_validation_report(classifier, sample_names, predictions, probabilities, expected_classes)
        # Multi-chromosome binary debug: mean methylation vs centroid means
        if debug and classifier.n_classes == 2 and hasattr(classifier, 'model_packages') and classifier_chroms:
            expected_classes_arr = np.array(expected_classes)
            first_chrom = classifier_chroms[0]
            pkg = classifier.model_packages.get(first_chrom, {})
            dmpDF = pkg.get('dmpDF')
            if dmpDF is not None and isinstance(dmpDF, pd.DataFrame) and 'alpha1' in dmpDF.columns:
                a1, b1 = dmpDF['alpha1'].values, dmpDF['beta1'].values
                a2, b2 = dmpDF['alpha2'].values, dmpDF['beta2'].values
                cent_mean0 = np.mean(np.clip(a1 / (a1 + b1), 0, 1))
                cent_mean1 = np.mean(np.clip(a2 / (a2 + b2), 0, 1))
                idx0 = next((i for i in range(n_samples) if expected_classes_arr[i] == 0), None)
                idx1 = next((i for i in range(n_samples) if expected_classes_arr[i] == 1), None)
                for idx, label in [(idx0, "expected class 0"), (idx1, "expected class 1")]:
                    if idx is not None and first_chrom in chrom_features and first_chrom in chrom_masks:
                        feats = chrom_features[first_chrom][idx]
                        mask = chrom_masks[first_chrom][idx]
                        if np.any(mask):
                            sample_mean = np.mean(feats[mask])
                            print(f"   Diagnostic ({first_chrom}): first {label} sample mean methylation = {sample_mean:.3f}")
                print(f"   Diagnostic ({first_chrom}): centroid1 (class0) mean = {cent_mean0:.3f}, centroid2 (class1) mean = {cent_mean1:.3f}")

    # Save chromosome probability matrix if requested
    if chrom_proba_matrix is not None:
        _save_chromosome_probability_matrix(
            sample_names, classifier_chroms, chrom_proba_matrix, chromosome_matrix_file
        )


def _print_validation_report(
    classifier: MethylClassifier,
    sample_names: List[str],
    predictions: np.ndarray,
    probabilities: np.ndarray,
    expected_classes: List[int]
) -> None:
    """Print centroid validation summary: per-class and overall accuracy (binary or multiclass)."""
    n_classes = classifier.n_classes
    class_names = getattr(classifier, 'class_names', None) or [f"Class_{i}" for i in range(n_classes)]
    expected_arr = np.array(expected_classes)
    n_samples = len(expected_arr)

    if n_classes == 2:
        prob_c1 = probabilities[:, 1]
        for exp in (0, 1):
            mask = expected_arr == exp
            n_exp = int(np.sum(mask))
            if n_exp == 0:
                continue
            pred_correct = int(np.sum((expected_arr == exp) & (predictions == exp)))
            mean_p1 = float(np.mean(prob_c1[mask]))
            label = class_names[exp] if exp < len(class_names) else f"class {exp}"
            print(f"\n📊 {label}: {n_exp} samples | mean P(class1)={mean_p1:.3f} | predicted correctly: {pred_correct}/{n_exp} ({100*pred_correct/n_exp:.1f}%)")
        n_correct_0 = int(np.sum((expected_arr == 0) & (predictions == 0)))
        n_correct_1 = int(np.sum((expected_arr == 1) & (predictions == 1)))
        n_exp_0 = int(np.sum(expected_arr == 0))
        n_exp_1 = int(np.sum(expected_arr == 1))
        if (n_exp_0 > 0 and n_correct_0 == 0) or (n_exp_1 > 0 and n_correct_1 == 0):
            print("\n⚠️ Centroid validation failed: at least one expected class has 0% correct predictions.")
            print("   Possible causes: (1) DMP/context mismatch (detector used CG-only; classifier now loads CG-only when model is CG).")
            print("   (2) Very low DMP coverage (check dmps_used in CSV). (3) Try --debug to inspect per-chromosome log-likelihoods.")
            print("   (4) Temperature or calibration: try temperature > 1 for softer probabilities.")
    else:
        # Multiclass: per-class accuracy, overall, balanced accuracy, confusion matrix
        per_class_correct = []
        per_class_total = []
        for k in range(n_classes):
            mask = expected_arr == k
            n_k = int(np.sum(mask))
            correct_k = int(np.sum((expected_arr == k) & (predictions == k)))
            per_class_total.append(n_k)
            per_class_correct.append(correct_k)
        overall_correct = int(np.sum(predictions == expected_arr))
        overall_acc = 100.0 * overall_correct / n_samples if n_samples else 0.0
        acc_per_class = [100.0 * c / t if t else 0.0 for c, t in zip(per_class_correct, per_class_total)]
        balanced_acc = float(np.mean(acc_per_class)) if per_class_total else 0.0
        print("\n📊 Centroid validation (multiclass)")
        for k in range(n_classes):
            label = class_names[k] if k < len(class_names) else f"Class_{k}"
            print(f"   {label}: {per_class_correct[k]}/{per_class_total[k]} correct ({acc_per_class[k]:.1f}%)")
        print(f"   Overall accuracy: {overall_correct}/{n_samples} ({overall_acc:.1f}%)")
        print(f"   Balanced accuracy: {balanced_acc:.1f}%")
        # Compact confusion matrix (rows = expected, cols = predicted)
        print("   Confusion matrix (rows=expected, cols=predicted):")
        for k in range(n_classes):
            row = []
            for j in range(n_classes):
                count = int(np.sum((expected_arr == k) & (predictions == j)))
                row.append(str(count))
            print("     " + " ".join(f"{x:>4}" for x in row))


def _save_classification_results(
    classifier: MethylClassifier,
    sample_names: List[str],
    predictions: np.ndarray,
    probabilities: np.ndarray,
    availability_mask: np.ndarray,
    dmp_positions: np.ndarray,
    output_file: Optional[Path],
    multi_chromosome: bool = False,
    chromosomes: Optional[List[str]] = None,
    expected_classes: Optional[List[int]] = None
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

        if expected_classes is not None and i < len(expected_classes):
            exp = expected_classes[i]
            result_entry['expected_class'] = int(exp)
            result_entry['agrees'] = bool(pred == exp)

        results_data.append(result_entry)

    # Write CSV
    fieldnames = ['sample', 'prediction', 'predicted_class'] + \
                 [f'prob_class{i}' for i in range(classifier.n_classes)] + \
                 ['dmps_used', 'dmps_total']

    if multi_chromosome and chromosomes:
        fieldnames.append('chromosomes')
    if expected_classes is not None:
        fieldnames.extend(['expected_class', 'agrees'])

    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results_data)

    print(f"\n💾 Results saved to: {output_file}")


def _save_classifier_and_sample_list(
    classifier: MethylClassifier,
    classifier_config: ClassifierConfig,
    samples_list: Optional[List[str]],
    output_dir: Optional[Path] = None,
) -> None:
    """
    After classification, save the classifier to <project_name>-classifier.pkl and/or
    export the list of sample folders to .txt or .csv when project_name or explicit paths are set.

    output_dir: Used when deriving paths from project_name (e.g. same dir as classification output).
    """
    project_name = getattr(classifier_config, "project_name", None)
    save_classifier_path = getattr(classifier_config, "save_classifier_path", None)
    samples_list_export_path = getattr(classifier_config, "samples_list_export_path", None)
    if output_dir is None:
        output_dir = Path.cwd()

    do_save_classifier = bool(save_classifier_path or project_name)
    do_export_samples = bool(samples_list_export_path or project_name) and samples_list and len(samples_list) > 0

    if do_save_classifier:
        if save_classifier_path:
            pkl_path = Path(save_classifier_path)
        else:
            pkl_path = output_dir / f"{project_name}-classifier.pkl"
        pkl_path.parent.mkdir(parents=True, exist_ok=True)
        classifier.save(pkl_path)
        print(f"\n💾 Classifier saved to: {pkl_path}")

    if do_export_samples:
        if samples_list_export_path:
            export_path = Path(samples_list_export_path)
        else:
            export_path = output_dir / f"{project_name}-samples.txt"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        suffix = export_path.suffix.lower()
        if suffix == ".csv":
            with open(export_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["sample_path"])
                for p in samples_list:
                    writer.writerow([p])
        else:
            with open(export_path, "w") as f:
                for p in samples_list:
                    f.write(p + "\n")
        print(f"\n💾 Sample list exported to: {export_path}")


def _save_chromosome_probability_matrix(
    sample_names: List[str],
    chromosomes: List[str],
    probability_matrix: np.ndarray,
    output_file: Path
) -> None:
    """
    Save chromosome probability matrix to CSV.

    Args:
        sample_names: List of sample names
        chromosomes: List of chromosome names
        probability_matrix: Matrix of shape (n_samples, n_chromosomes) with p1 probabilities
        output_file: Path to output CSV file
    """
    import csv

    # Create header: sample + chromosome names
    fieldnames = ['sample'] + chromosomes

    # Create data rows
    results_data = []
    for i, sample_name in enumerate(sample_names):
        row = {'sample': sample_name}
        for j, chrom in enumerate(chromosomes):
            row[chrom] = probability_matrix[i, j]
        results_data.append(row)

    # Write CSV
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results_data)

    print(f"🧬 Chromosome probability matrix saved to: {output_file}")


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


def _run_one_classification(config: ClassificationConfig, label: Optional[str] = None) -> None:
    """Run classification once with the given config (used for single run and per-cancer-group loop)."""
    classifier_config = ClassifierConfig(
        model_path=config.model_path,
        model_dir=config.model_dir,
        temperature=config.temperature,
        enable_platt_calibration=config.enable_platt_calibration,
        trimmed_percentile_low=config.trimmed_percentile_low,
        trimmed_percentile_high=config.trimmed_percentile_high,
        chromosome_weights=config.chromosome_weights,
        chromosome_matrix_path=config.chromosome_matrix_path,
        weight_method=getattr(config, "weight_method", None),
        weight_fit_regularization=getattr(config, "weight_fit_regularization", "none"),
        weight_fit_alpha=getattr(config, "weight_fit_alpha", 1.0),
        weight_fit_l1_ratio=getattr(config, "weight_fit_l1_ratio", 0.5),
        project_name=getattr(config, "project_name", None),
        save_classifier_path=getattr(config, "save_classifier_path", None),
        samples_list_export_path=getattr(config, "samples_list_export_path", None),
    )
    classifier = MethylClassifier(classifier_config)
    chrom, context = None, None
    if not config.no_filter and not classifier.is_multi_chromosome:
        model_path_str = config.model_dir or config.model_path
        if model_path_str:
            try:
                chrom, context = extract_chrom_context_from_classifier(Path(model_path_str))
                print(f"📋 Classifier trained on chromosome {chrom}, context {context}")
            except ValueError as e:
                print(f"⚠️ {e}")
    elif classifier.is_multi_chromosome:
        print(f"📋 Multi-chromosome classifier mode: {len(classifier.classifiers)} chromosomes")

    expected_classes = None
    c1_paths = getattr(config, 'centroid1_sample_paths', None)
    c2_paths = getattr(config, 'centroid2_sample_paths', None)
    c1_dir = getattr(config, 'centroid1_dir', None)
    c2_dir = getattr(config, 'centroid2_dir', None)
    if (c1_paths and c2_paths) and (len(c1_paths) > 0 and len(c2_paths) > 0):
        config.samples = list(c1_paths) + list(c2_paths)
        expected_classes = [0] * len(c1_paths) + [1] * len(c2_paths)
        print(f"📂 Centroid validation: {len(c1_paths)} centroid1 + {len(c2_paths)} centroid2 samples")
    elif c1_dir and c2_dir:
        path_remap = getattr(config, 'centroid_path_remap', None)
        sample_root = getattr(config, 'centroid_sample_root', None) if not path_remap else None
        c1_resolved = _read_samples_used_from_centroid_dir(Path(c1_dir), sample_root=sample_root, path_remap=path_remap)
        c2_resolved = _read_samples_used_from_centroid_dir(Path(c2_dir), sample_root=sample_root, path_remap=path_remap)
        if not c1_resolved or not c2_resolved:
            raise ValueError(
                f"Centroid dirs yielded no samples_used: centroid1_dir={c1_dir} -> {len(c1_resolved)} paths, "
                f"centroid2_dir={c2_dir} -> {len(c2_resolved)} paths."
            )
        config.samples = c1_resolved + c2_resolved
        expected_classes = [0] * len(c1_resolved) + [1] * len(c2_resolved)
        print(f"📂 Centroid validation (from metadata): {len(c1_resolved)} + {len(c2_resolved)} samples")
    elif getattr(config, 'centroid_dirs', None) and len(config.centroid_dirs) > 2:
        centroid_dirs = config.centroid_dirs
        path_remap = getattr(config, 'centroid_path_remap', None)
        sample_root = getattr(config, 'centroid_sample_root', None) if not path_remap else None
        all_samples = []
        expected_classes = []
        for class_idx, c_dir in enumerate(centroid_dirs):
            resolved = _read_samples_used_from_centroid_dir(Path(c_dir), sample_root=sample_root, path_remap=path_remap)
            if not resolved:
                raise ValueError(
                    f"Centroid dir for class {class_idx} yielded no samples_used: {c_dir}"
                )
            all_samples.extend(resolved)
            expected_classes.extend([class_idx] * len(resolved))
        config.samples = all_samples
        config.expected_classes = expected_classes
        print(f"📂 Multiclass centroid validation: {len(centroid_dirs)} classes, {len(all_samples)} samples")
    elif classifier.is_multi_chromosome and config.input_path and not config.samples:
        input_path = Path(config.input_path)
        if input_path.is_dir():
            sample_dirs = sorted([d for d in input_path.iterdir() if d.is_dir() and list(d.glob("*-CG.h5"))])
            if sample_dirs:
                config.samples = [str(d) for d in sample_dirs]
                print(f"📂 Using {len(sample_dirs)} sample directories under {config.input_path}")

    if config.output_path:
        Path(config.output_path).parent.mkdir(parents=True, exist_ok=True)
    if config.samples:
        required_chromosomes = None
        positions = None
        dmp_positions_by_chrom = None
        if classifier.is_multi_chromosome:
            required_chromosomes = list(classifier.classifiers.keys())
            positions = getattr(classifier, 'all_dmp_positions', None)
            dmp_positions_by_chrom = getattr(classifier, 'dmp_positions_by_chrom', None)
        classify_samples_from_list(
            classifier=classifier,
            samples_list=config.samples,
            output_file=Path(config.output_path) if config.output_path else None,
            debug=config.debug,
            required_chromosomes=required_chromosomes,
            positions=positions,
            dmp_positions_by_chrom=dmp_positions_by_chrom,
            expected_classes=expected_classes
        )
    else:
        classify_samples(
            classifier=classifier,
            h5_path=Path(config.input_path) if config.input_path else None,
            chrom=chrom,
            context=context,
            output_file=Path(config.output_path) if config.output_path else None,
            debug=config.debug
        )
    output_dir = Path(config.output_path).parent if config.output_path else Path.cwd()
    _save_classifier_and_sample_list(
        classifier, classifier_config, getattr(config, "samples", None), output_dir=output_dir
    )


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
        '--project', '-p',
        type=Path,
        metavar='JSON',
        help='Path to pipeline project config; builds config from detection/centroid/classifier dirs'
    )
    parser.add_argument(
        '--step-override',
        type=Path,
        metavar='JSON',
        help='Optional JSON overrides for classifier step when using --project'
    )
    parser.add_argument(
        '--per-cancer-group',
        action='store_true',
        help='With --project: run one classifier per disease group. '
             'Uses model from detection/<disease_label>/<group> and writes to classifier/<disease_label>/<group>/classification_results.csv '
             '(e.g. detection/cancer/pca1-1, classifier/cancer/pca1-1). Auto-enabled when project uses controls/diseases + comparisons.'
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

    # Exactly one of --config or --project or (model + input) for config source
    if args.project is not None:
        if args.config is not None:
            raise ValueError("Use either --config or --project, not both.")
        if not args.project.exists():
            raise FileNotFoundError(f"Project config not found: {args.project}")
        # Use per-comparison folder pattern (detection/cancer/{label}, classifier/cancer/{label}) when
        # project uses control/disease, so classifier follows same layout as MethylDetector/MethylMapper.
        use_per_comparison = getattr(args, 'per_cancer_group', False)
        if load_project is not None:
            project = load_project(args.project)
            if getattr(project, "uses_control_disease", lambda: False)():
                use_per_comparison = True
        if use_per_comparison:
            configs_and_labels = resolve_classifier_config_per_cancer_group(args.project, args.step_override)
            if not configs_and_labels:
                raise ValueError(
                    "Project has fewer than 2 groups; per-comparison mode requires at least one control and one disease group."
                )
            setup_logging("INFO")
            for config, label in configs_and_labels:
                print(f"\n{'='*60}\nClassifier: control vs {label}\n{'='*60}")
                try:
                    _run_one_classification(config, label=label)
                except Exception as e:
                    import traceback
                    print(f"❌ Classification failed for {label}: {e}")
                    traceback.print_exc()
                    sys.exit(1)
            print(f"\nPer-comparison classification complete: {len(configs_and_labels)} group(s)")
            for config, label in configs_and_labels:
                print(f"  {label}: {config.output_path}")
            return
        config = resolve_classifier_config(args.project, args.step_override)
        if args.model:
            config.model_path = str(args.model)
        if args.model_dir:
            config.model_dir = str(args.model_dir)
        if args.input:
            config.input_path = str(args.input)
        if args.output:
            config.output_path = str(args.output)
    elif args.config:
        with open(args.config, 'r') as f:
            config_data = json.load(f)
        config = ClassificationConfig(**config_data)
        if args.model:
            config.model_path = str(args.model)
        if args.model_dir:
            config.model_dir = str(args.model_dir)
        if args.input:
            config.input_path = str(args.input)
        if args.output:
            config.output_path = str(args.output)
    else:
        # Construct config from CLI args (existing logic)
        config = ClassificationConfig(
            model_path=str(args.model),
            input_path=str(args.input),
            output_path=str(args.output) if args.output else None,
            debug=args.debug,
            log_level=args.log_level
        )
        config.temperature = 1.0
        config.enable_platt_calibration = False
    
    # Setup logging
    setup_logging(config.log_level)

    try:
        _run_one_classification(config)
    except Exception as e:
        import traceback
        print(f"❌ Classification failed: {e}")
        print(f"   Error type: {type(e).__name__}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    import sys
    import traceback
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Interrupted by user (Ctrl+C)")
        sys.exit(130)
    except SystemExit:
        raise  # Let system exits through
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        print(f"   Error type: {type(e).__name__}")
        print("   Full traceback:")
        traceback.print_exc()
        sys.exit(1)
