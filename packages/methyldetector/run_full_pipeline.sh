#!/bin/bash
#
# Complete Methylation Analysis Pipeline
# Runs MethylDetector + MethylTrainer to get DMPs and trained classifier
#
# Usage:
#   ./run_full_pipeline.sh --centroid1 <path> --centroid2 <path> --output-dir <dir> [options]
#

set -e  # Exit on error

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
OUTPUT_DIR="./output"
CHROMOSOME=""
CONTEXT=""
MAX_DMPS=1000
MAX_Q_VALUE=0.05
MIN_JEFFREYS=0.3
MIN_AUC=0.6
ALPHA=0.05
VERBOSE=false
SKIP_DETECTOR=false
SKIP_TRAINER=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --centroid1)
            CENTROID1="$2"
            shift 2
            ;;
        --centroid2)
            CENTROID2="$2"
            shift 2
            ;;
        --output-dir|-o)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --chromosome)
            CHROMOSOME="$2"
            shift 2
            ;;
        --context)
            CONTEXT="$2"
            shift 2
            ;;
        --max-dmps)
            MAX_DMPS="$2"
            shift 2
            ;;
        --max-q-value)
            MAX_Q_VALUE="$2"
            shift 2
            ;;
        --min-jeffreys)
            MIN_JEFFREYS="$2"
            shift 2
            ;;
        --min-auc)
            MIN_AUC="$2"
            shift 2
            ;;
        --alpha)
            ALPHA="$2"
            shift 2
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --skip-detector)
            SKIP_DETECTOR=true
            shift
            ;;
        --skip-trainer)
            SKIP_TRAINER=true
            shift
            ;;
        --help|-h)
            echo "Complete Methylation Analysis Pipeline"
            echo ""
            echo "Usage: $0 --centroid1 <path> --centroid2 <path> [options]"
            echo ""
            echo "Required:"
            echo "  --centroid1 PATH       Path to first centroid HDF5 file"
            echo "  --centroid2 PATH       Path to second centroid HDF5 file"
            echo ""
            echo "Optional:"
            echo "  --output-dir DIR       Output directory (default: ./output)"
            echo "  --chromosome CHR       Chromosome identifier (e.g., chr1)"
            echo "  --context CTX          Methylation context (e.g., CG)"
            echo "  --max-dmps N           Maximum DMPs for classifier (default: 1000)"
            echo "  --max-q-value Q        Maximum q-value (default: 0.05)"
            echo "  --min-jeffreys J       Minimum Jeffreys divergence (default: 0.3)"
            echo "  --min-auc A            Minimum AUC score (default: 0.6)"
            echo "  --alpha A              Significance level (default: 0.05)"
            echo "  --verbose, -v          Enable verbose output"
            echo "  --skip-detector        Skip DMP detection (use existing DMPs)"
            echo "  --skip-trainer         Skip classifier training"
            echo "  --help, -h             Show this help message"
            echo ""
            echo "Example:"
            echo "  $0 --centroid1 healthy.h5 --centroid2 disease.h5 \\"
            echo "     --output-dir results/ --max-dmps 500 --verbose"
            exit 0
            ;;
        *)
            echo -e "${RED}Error: Unknown option $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [ -z "$CENTROID1" ] || [ -z "$CENTROID2" ]; then
    echo -e "${RED}Error: --centroid1 and --centroid2 are required${NC}"
    echo "Use --help for usage information"
    exit 1
fi

# Check if files exist
if [ ! -f "$CENTROID1" ]; then
    echo -e "${RED}Error: Centroid 1 not found: $CENTROID1${NC}"
    exit 1
fi

if [ ! -f "$CENTROID2" ]; then
    echo -e "${RED}Error: Centroid 2 not found: $CENTROID2${NC}"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Extract names from file paths
CENTROID1_NAME=$(basename "$CENTROID1" .h5)
CENTROID2_NAME=$(basename "$CENTROID2" .h5)

# Extract chromosome and context if not provided
if [ -z "$CHROMOSOME" ] || [ -z "$CONTEXT" ]; then
    # Try to extract from filename (e.g., sample_chr1-CG.h5)
    if [[ "$CENTROID1_NAME" =~ (chr[0-9XY]+)[-_]([A-Z]+) ]]; then
        [ -z "$CHROMOSOME" ] && CHROMOSOME="${BASH_REMATCH[1]}"
        [ -z "$CONTEXT" ] && CONTEXT="${BASH_REMATCH[2]}"
    fi
fi

# Set default naming
MODEL_NAME="classifier"
[ -n "$CHROMOSOME" ] && MODEL_NAME="${MODEL_NAME}_${CHROMOSOME}"
[ -n "$CONTEXT" ] && MODEL_NAME="${MODEL_NAME}-${CONTEXT}"

DMP_DIR="$OUTPUT_DIR/dmps"
MODEL_PATH="$OUTPUT_DIR/${MODEL_NAME}.pkl"

# Print configuration
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         Complete Methylation Analysis Pipeline                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Configuration:${NC}"
echo "  Centroid 1:     $CENTROID1"
echo "  Centroid 2:     $CENTROID2"
echo "  Output Dir:     $OUTPUT_DIR"
echo "  DMP Dir:        $DMP_DIR"
echo "  Model Path:     $MODEL_PATH"
[ -n "$CHROMOSOME" ] && echo "  Chromosome:     $CHROMOSOME"
[ -n "$CONTEXT" ] && echo "  Context:        $CONTEXT"
echo "  Max DMPs:       $MAX_DMPS"
echo "  Max Q-value:    $MAX_Q_VALUE"
echo "  Min Jeffreys:   $MIN_JEFFREYS"
echo "  Min AUC:        $MIN_AUC"
echo "  Alpha:          $ALPHA"
echo ""

# Step 1: Run MethylDetector
if [ "$SKIP_DETECTOR" = false ]; then
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}Step 1: DMP Detection with MethylDetector${NC}"
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    
    DETECTOR_CMD="methyldetector --centroid1 $CENTROID1 --centroid2 $CENTROID2 --output $DMP_DIR --alpha $ALPHA --mode single"
    
    if [ "$VERBOSE" = true ]; then
        DETECTOR_CMD="$DETECTOR_CMD --verbose"
    fi
    
    echo -e "${BLUE}Running:${NC} $DETECTOR_CMD"
    echo ""
    
    if eval $DETECTOR_CMD; then
        echo ""
        echo -e "${GREEN}✅ DMP Detection completed successfully${NC}"
        
        # Count DMPs if CSV exists
        if [ -f "$DMP_DIR/biological_dmps.csv" ]; then
            DMP_COUNT=$(tail -n +2 "$DMP_DIR/biological_dmps.csv" | wc -l)
            echo -e "${GREEN}   Found: $DMP_COUNT DMPs${NC}"
        fi
    else
        echo -e "${RED}❌ DMP Detection failed${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⏭️  Skipping DMP detection (using existing DMPs)${NC}"
fi

echo ""

# Step 2: Run MethylTrainer
if [ "$SKIP_TRAINER" = false ]; then
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}Step 2: Classifier Training with MethylTrainer${NC}"
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    
    TRAINER_CMD="methyltrainer --centroid1 $CENTROID1 --centroid2 $CENTROID2 --output $MODEL_PATH"
    TRAINER_CMD="$TRAINER_CMD --max-dmps $MAX_DMPS --max-q-value $MAX_Q_VALUE"
    TRAINER_CMD="$TRAINER_CMD --min-jeffreys $MIN_JEFFREYS --min-auc $MIN_AUC"
    TRAINER_CMD="$TRAINER_CMD --centroid1-name $CENTROID1_NAME --centroid2-name $CENTROID2_NAME"
    
    [ -n "$CHROMOSOME" ] && TRAINER_CMD="$TRAINER_CMD --chromosome $CHROMOSOME"
    [ -n "$CONTEXT" ] && TRAINER_CMD="$TRAINER_CMD --context $CONTEXT"
    [ "$VERBOSE" = true ] && TRAINER_CMD="$TRAINER_CMD --verbose"
    
    echo -e "${BLUE}Running:${NC} $TRAINER_CMD"
    echo ""
    
    if eval $TRAINER_CMD; then
        echo ""
        echo -e "${GREEN}✅ Classifier training completed successfully${NC}"
        
        # Display model info
        if [ -f "$MODEL_PATH" ]; then
            MODEL_SIZE=$(du -h "$MODEL_PATH" | cut -f1)
            echo -e "${GREEN}   Model saved: $MODEL_PATH ($MODEL_SIZE)${NC}"
        fi
    else
        echo -e "${RED}❌ Classifier training failed${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⏭️  Skipping classifier training${NC}"
fi

echo ""

# Summary
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                      Pipeline Complete                         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}✅ Analysis complete!${NC}"
echo ""
echo "Output files:"
echo "  📁 DMPs:        $DMP_DIR/"
echo "  🤖 Classifier:  $MODEL_PATH"
echo ""
echo "Next steps:"
echo ""
echo "  1. Review DMPs:"
echo "     cat $DMP_DIR/biological_dmps_analysis_summary.json"
echo ""
echo "  2. Classify samples:"
echo "     methylclassifier --model $MODEL_PATH --input samples/ --output results.csv"
echo ""
echo "  3. Inspect model metadata:"
echo "     python -c \"import pickle; m=pickle.load(open('$MODEL_PATH','rb')); print(m.get('metadata',{}))\""
echo ""

