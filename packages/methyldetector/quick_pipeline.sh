#!/bin/bash
#
# Quick Pipeline - Simple wrapper for common use case
# Detects DMPs and trains classifier in one command
#

if [ "$#" -lt 2 ]; then
    echo "Quick Methylation Pipeline"
    echo ""
    echo "Usage: $0 <centroid1.h5> <centroid2.h5> [output_dir]"
    echo ""
    echo "Example:"
    echo "  $0 healthy_chr1-CG.h5 disease_chr1-CG.h5 results/"
    echo ""
    echo "This will:"
    echo "  1. Detect DMPs using MethylDetector"
    echo "  2. Train classifier using MethylTrainer"
    echo "  3. Save model as classifier.pkl in output directory"
    exit 1
fi

CENTROID1="$1"
CENTROID2="$2"
OUTPUT_DIR="${3:-./output}"

# Run the full pipeline with default settings
./run_full_pipeline.sh \
    --centroid1 "$CENTROID1" \
    --centroid2 "$CENTROID2" \
    --output-dir "$OUTPUT_DIR" \
    --verbose

