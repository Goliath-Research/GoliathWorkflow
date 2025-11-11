# Per-Chromosome Centroid Creation

This tool creates chromosome-isolated centroids from real methylation sample files. Each chromosome gets its own centroid file combining all contexts (CG, CHG, CHH) for that chromosome, maintaining biological boundaries.

## Overview

The centroid creation tool consists of:
- `mc` - Executable script that runs inside the methylpipeline Docker container
- `test_centroid_creation.py` - Python script that loads real methylation samples

The scripts load methylation samples with the file naming pattern `{chrom}-{ctx}.h5` where:
- `chrom`: '1', '2', ..., '22', 'X', 'Y'
- `ctx`: 'CG', 'CHG', 'CHH'

**Memory-Efficient Algorithm**: Instead of loading all samples into memory simultaneously, the tool uses incremental centroid building:
1. Start with the first sample as the initial centroid
2. For each subsequent sample, load it individually and add it to the existing centroid
3. Only 1 centroid + 1 sample are ever in memory at the same time

This approach can handle datasets with 85+ million positions per sample efficiently.

## Prerequisites

- MethylPipeline Docker container must be running:
  ```bash
  cd /home/ubuntu/MethylPipeline/docker && docker compose up -d
  ```

## Usage

## Running with Docker (Recommended)

The easiest way to run centroid creation is using the provided `mc` script, which executes inside the methylpipeline Docker container:

### Using Hardcoded Sample List

If no arguments are provided, the script uses a hardcoded list of sample directories and creates chromosome centroids:

```bash
cd /home/ubuntu/MethylPipeline/packages/methylutils/tests
./mc
```

This creates chromosome centroids from your 15 sample directories.

### Basic Usage with Single Directory

```bash
./mc /path/to/samples
```

Creates chromosome centroids from samples in the specified directory.

### Multiple Sample Directories

```bash
./mc /path/to/samples1 /path/to/samples2 /path/to/samples3
```

Creates chromosome centroids by combining samples across multiple directories.

### With Output Directory

```bash
./mc /path/to/samples -o /path/to/output
```


### Specific Chromosomes and Contexts

```bash
# Only chromosomes 1, 2, and X
./mc /path/to/samples -c 1 2 X

# Only CG and CHG contexts
./mc /path/to/samples --contexts CG CHG

# Both specific chromosomes and contexts
./mc /path/to/samples -c 1 2 X --contexts CG CHG
```

### Test Mode (Creates Mock Samples)

```bash
# Creates mock samples and then builds centroid from them
./mc --test-mode
```

## Running Directly (Advanced)

If you need to run the script directly (not recommended), ensure the methylpipeline container is running:

### Using Hardcoded Sample List

If no arguments are provided, the script uses a hardcoded list of sample directories:

```bash
cd /home/ubuntu/MethylPipeline/packages/methylutils
PYTHONPATH=/home/ubuntu/MethylPipeline/packages/methylutils python tests/test_centroid_creation.py
```

### Basic Usage with Single Directory

```bash
python tests/test_centroid_creation.py /path/to/samples
```

### Multiple Sample Directories

```bash
python tests/test_centroid_creation.py /path/to/samples1 /path/to/samples2 /path/to/samples3
```

### With Output Directory

```bash
python tests/test_centroid_creation.py /path/to/samples -o /path/to/output
```

### Specific Chromosomes and Contexts

```bash
# Only chromosomes 1, 2, and X
python tests/test_centroid_creation.py /path/to/samples -c 1 2 X

# Only CG and CHG contexts
python tests/test_centroid_creation.py /path/to/samples --contexts CG CHG

# Both specific chromosomes and contexts
python tests/test_centroid_creation.py /path/to/samples -c 1 2 X --contexts CG CHG
```

### Test Mode (Creates Mock Samples)

```bash
# Creates mock samples and then builds centroid from them
python tests/test_centroid_creation.py --test-mode
```

## Command Line Options

- `input_directory`: Directory containing sample files (default: current directory)
- `-o, --output-directory`: Directory to save centroid (default: same as input)
- `-c, --chromosomes`: Specific chromosomes to include (default: all)
- `--contexts`: Contexts to include (default: CG CHG CHH)
- `--test-mode`: Create mock samples for testing

## Input File Format

The script expects HDF5 files with the naming pattern `{chrom}-{ctx}.h5`, where:
- `chrom` is the chromosome number/name (1, 2, ..., 22, X, Y)
- `ctx` is the methylation context (CG, CHG, CHH)

Example files:
- `1-CG.h5`, `1-CHG.h5`, `1-CHH.h5`
- `2-CG.h5`, `2-CHG.h5`, `2-CHH.h5`
- `X-CG.h5`, `X-CHG.h5`, `X-CHH.h5`

## Output

### Per-Chromosome-Context Centroids
Creates separate centroids for each chromosome-context combination:
- `1-CG.h5`, `1-CHG.h5`, `1-CHH.h5`
- `2-CG.h5`, `2-CHG.h5`, `2-CHH.h5`
- `X-CG.h5`, `X-CHG.h5`, `X-CHH.h5`
- etc.
- Same naming convention as input samples
- Allows loading individual chromosome-context combinations
- Maximizes memory efficiency by processing smaller chunks

#### Optimized Implementation

The tool uses an optimized PositionAligner approach:
- Creates one PositionAligner per chromosome-context combination
- Reuses aligner across all samples for that specific combination
- Avoids repeated centroid loading and memory allocations
- Minimizes GPU memory transfers for large datasets
- Processes smaller chunks for maximum memory efficiency

## Performance Considerations

### Memory Usage
**Before**: Loaded all samples simultaneously (potentially 15 × 85M = 1.275B positions in memory)

**After**: Incremental building with only 1 centroid + 1 sample in memory at any time:
- Peak memory: ~170M positions (1 centroid + 1 sample)
- 99.987% reduction in peak memory usage
- Scales linearly with number of samples

**Per-Chromosome Processing**: Memory efficient as it processes one chromosome at a time.

### Computational Performance

⚠️ **Performance Bottleneck**: The `MethylSample.add_sample()` method can be slow for large datasets due to:

1. **Array Copying**: Each sample addition involves copying 85M+ position arrays
2. **Memory Reallocation**: PositionAligner expands internal arrays for each new sample
3. **GPU Transfers**: Large arrays are transferred to/from GPU memory
4. **Position Alignment**: Complex alignment operations for overlapping genomic positions

**Expected Performance**: For 85M positions per sample, the optimized approach provides significant speedup by reusing PositionAligner instances.

**Technical Notes**:
- Sample indices are sequential counters (0, 1, 2...) for each addition to the centroid, not biological sample IDs
- Each context (CG, CHG, CHH) from each biological sample gets its own sequential index
- PositionAligner handles memory allocation efficiently for large genomic datasets

**Architecture Note**: PositionAligner is used across multiple MethylPipeline modules (MethylCentroid, MethylCluster) for alignment operations, so optimization benefits all components.

## Requirements

- Python 3.8+
- MethylUtils package
- HDF5 files with proper MethylSample format

## Examples

### Process all samples in current directory
```bash
python tests/test_centroid_creation.py .
```

### Process specific dataset
```bash
python tests/test_centroid_creation.py /data/methylation_samples \
  -c 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 X Y \
  --contexts CG CHG CHH \
  -o /results/centroids
```

### Test with mock data
```bash
python tests/test_centroid_creation.py --test-mode -o /tmp/test_output
```
