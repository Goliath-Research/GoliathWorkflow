#!/usr/bin/env python3
"""
DMP Filtering Example Script

This script demonstrates how to use MethylDetector's advanced DMP filtering
capabilities to select highly discriminative differentially methylated positions.

Author: MethylDetector Team
"""

import sys
from pathlib import Path
import logging

# Add the package to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from methyl_detector import MethylDetector
from methyl_detector.models.config import MethylDetectorConfig
from methyl_detector.core.dmp_filter import DMPFilter, DMPFilterResult


def demonstrate_dmp_filtering():
    """Demonstrate DMP filtering functionality with sample data."""

    print("MethylDetector DMP Filtering Example")
    print("=" * 50)

    # Example configuration with DMP filtering enabled
    config = MethylDetectorConfig(
        centroid1_path=Path("/home/ubuntu/Work/output_workflows/arabidopsis/centroids/WT/1-CG.h5"),
        centroid2_path=Path("/home/ubuntu/Work/output_workflows/arabidopsis/centroids/msh1/1-CG.h5"),
        output_dir=Path("./example_results"),
        alpha=0.05,
        min_N=10,
        apply_fdr_correction=True,
        fdr_method="storey",
        global_significance_threshold=0.05,
        use_gpu=True,

        # DMP filtering parameters
        apply_dmp_filtering=True,
        dmp_filter_method="combined",
        min_overlap=0.6,
        min_delta_mean=0.2,
        min_jeffreys_divergence=0.5,
        min_cohen_d=0.8,
        min_auc=0.7,
        max_selected_dmps=100
    )

    print("Configuration:")
    print(f"  Centroid 1: {config.centroid1_path}")
    print(f"  Centroid 2: {config.centroid2_path}")
    print(f"  Filtering Method: {config.dmp_filter_method}")
    print(f"  Min Delta Mean: {config.min_delta_mean}")
    print(f"  Min Overlap: {config.min_overlap}")
    print(f"  Max Selected DMPs: {config.max_selected_dmps}")
    print()

    try:
        # Run MethylDetector with DMP filtering
        print("Running MethylDetector with DMP filtering...")
        detector = MethylDetector(config)
        result = detector.run()

        print("Analysis completed successfully!")
        print(f"Results saved to: {result.output_dir}")

        # Display filtering results if available
        if hasattr(result, 'comparisons') and result.comparisons:
            comparison = result.comparisons[0]
            print("Filtering Results:")
            print(f"  Total Positions: {comparison.total_positions}")
            print(f"  Significant Positions: {comparison.significant_count}")
            print(f"  Significant Fraction: {comparison.significant_fraction:.1%}")

            # Check if filtering statistics are available
            if hasattr(comparison, 'output_files'):
                print("Output Files:")

                for file_type, file_path in comparison.output_files.items():
                    print(f"  {file_type}: {file_path}")

    except FileNotFoundError as e:
        print(f"Error: Centroid file not found: {e}")
        print("Please update the file paths in this example script.")
    except Exception as e:
        print(f"Error running analysis: {e}")
        import traceback
        traceback.print_exc()


def demonstrate_manual_filtering():
    """Demonstrate manual DMP filtering using the DMPFilter class."""

    print("\nManual DMP Filtering Example")
    print("=" * 30)

    # Create sample DMP results for demonstration
    sample_results = [
        DMPFilterResult(
            position=i*1000,
            p_value=0.01,
            q_value=0.02,
            delta_mean=0.15 + i*0.05,  # Increasing delta means
            distribution_overlap=0.7 - i*0.1,  # Decreasing overlap
            jeffreys_divergence=0.3 + i*0.2,  # Increasing divergence
            auc_score=0.65 + i*0.05,  # Increasing AUC
            mean1=0.3 + i*0.02,
            mean2=0.5 + i*0.03,
            alpha1=2.0 + i*0.5,
            beta1=3.0 + i*0.3,
            alpha2=2.5 + i*0.4,
            beta2=2.8 + i*0.2
        ) for i in range(10)
    ]

    print(f"Sample DMPs: {len(sample_results)}")
    print("Before filtering:")
    for r in sample_results[:3]:
        print(".3f")

    # Apply filtering
    filter_obj = DMPFilter(
        min_overlap=0.6,
        min_delta_mean=0.2,
        min_jeffreys_divergence=0.5,
        min_auc=0.7,
        selection_method="combined"
    )

    filtered_results, statistics = filter_obj.filter_dmps(sample_results)

    print("After filtering:")
    print(f"Selected DMPs: {statistics['selected_dmps']}/{statistics['input_dmps']}")
    print(".1%")

    for r in filtered_results:
        if r.selected:
            print(".3f")

    print("Filtering Statistics:")
    for key, value in statistics.items():
        if isinstance(value, float):
            print(".4f")
        else:
            print(f"  {key}: {value}")


def main():
    """Main function to run examples."""

    # Set up logging
    # Use MethylUtils logging if available
    try:
        from methyl_utils.logging_utils import setup_logging
        setup_logging(verbose=False)
    except ImportError:
        # Fallback to basic logging if MethylUtils not available
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    print("MethylDetector DMP Filtering Examples")
    print("=" * 50)
    print()

    # Check if sample data exists
    centroid1_path = Path("/home/ubuntu/Work/output_workflows/arabidopsis/centroids/WT/1-CG.h5")
    centroid2_path = Path("/home/ubuntu/Work/output_workflows/arabidopsis/centroids/msh1/1-CG.h5")

    if centroid1_path.exists() and centroid2_path.exists():
        demonstrate_dmp_filtering()
    else:
        print("Sample centroid files not found.")
        print("Please update the file paths in this script or run with your own data.")
        print()

    # Always demonstrate manual filtering
    demonstrate_manual_filtering()

    print("\nFor more information, see:")
    print("- docs/DMP_FILTERING.md")
    print("- examples/config_dmp_filtering.json")
    print("- README.md section on DMP filtering")


if __name__ == "__main__":
    main()
