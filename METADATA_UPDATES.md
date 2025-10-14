# Metadata Support in MethylCentroid

## Overview
This update adds comprehensive metadata support to the MethylCentroid package, allowing important provenance information to be validated in the configuration and saved directly within the centroid H5 files.

## Environment Setup

Before using the examples and scripts, set up the MethylPipeline environment:

```bash
cd /home/ubuntu/MethylPipeline
source setup_env.sh
```

This sets the `METHYLPIPELINE` environment variable which all projects use to locate resources. See `ENV_SETUP.md` for details.

## Changes Made

### 1. Updated Pydantic Configuration Model (`config.py`)

#### MethylCentroidConfig
Added required metadata fields:
- `laboratory`: Laboratory or institution name
- `disease`: Disease or condition being studied
- `group`: Sample group identifier (e.g., 'cancer', 'control')
- `batch`: Batch identifier for sample processing

These fields are validated by Pydantic and must be provided when creating a configuration.

Added `get_metadata()` method:
- Extracts metadata fields from the config
- Returns a dictionary ready to be saved to H5 files
- Includes both metadata fields and key processing parameters

#### BatchProcessingConfig
No changes to metadata fields - metadata is only specified once in the `base_config` (MethylCentroidConfig).
This avoids redundancy since all batch centroids use the same metadata from `base_config`.

### 2. Updated MethylSample (`methyl_utils/methyl_sample.py`)

Enhanced `save_to_h5()` method:
- Added optional `metadata` parameter (Dict[str, Any])
- Saves metadata as HDF5 file-level attributes
- Handles various data types:
  - Strings, integers, floats, booleans: stored directly
  - Lists of strings: stored as JSON
  - Other types: converted to JSON strings
  - None values: skipped

Enhanced `load_from_h5()` method:
- Automatically loads metadata from HDF5 file attributes
- Stores metadata in `_metadata` field

Added metadata properties for easy access (read-write):
- `laboratory` - Get/set laboratory name
- `disease` - Get/set disease name
- `group` - Get/set group identifier
- `batch` - Get/set batch identifier
- `chromosome` - Get/set chromosome
- `context` - Get/set methylation context
- `metadata` - Get/set all metadata as dictionary

These properties are **read-write**, making it easy to modify metadata:
```python
centroid.laboratory = "psomagen"
centroid.disease = "prostate cancer"
```

Updated `from_centroid_data()` method:
- Added optional `metadata` parameter to attach metadata when creating from centroid data

### 3. Updated MethylCentroid (`methyl_centroid.py`)

#### __init__ method
Added metadata parameters:
- `laboratory` (Optional[str])
- `disease` (Optional[str])
- `group` (Optional[str])
- `batch` (Optional[str])

#### from_config method
Updated to extract and pass metadata fields from config to constructor

#### get_config method
Updated to include metadata fields when reconstructing config

#### save_centroid method
Enhanced to prepare and pass metadata to `MethylSample.save_to_h5()`:
- Includes all metadata fields
- Adds chromosome, context, and sample list
- Includes key processing parameters (min_coverage, alpha, distance_metrics, etc.)

### 4. Updated CLI (`cli.py`)

#### Command-line Arguments
Added new metadata argument group:
- `--laboratory`: Laboratory or institution name
- `--disease`: Disease or condition being studied
- `--group`: Sample group identifier
- `--batch`: Batch identifier

#### create_config_from_args
Updated to require and use metadata fields when creating config from command-line arguments

#### run_batch_processing
Uses metadata from `base_config` for all chromosome/context combinations

### 5. Updated Configuration Files

#### pb-cancer_batch_config.json
Added required metadata fields to `base_config`

#### pb-cancer_batch12_config.json
Added required metadata fields to `base_config`

## Metadata Stored in H5 Files

When a centroid is saved, the following metadata is stored as HDF5 attributes:

### Required Metadata
1. `laboratory` - Laboratory or institution name
2. `disease` - Disease or condition being studied
3. `group` - Sample group identifier
4. `batch` - Batch identifier for sample processing

### Additional Information
5. `chromosome` - Chromosome identifier
6. `context` - Methylation context (CG, CHG, CHH)
7. `samples` - JSON list of sample paths used to build the centroid
8. `min_coverage` - Minimum coverage threshold used
9. `alpha` - Significance level for outlier detection
10. `distance_metrics` - List of distance metrics used
11. `max_iterations` - Maximum outlier removal iterations

## Usage Examples

### Using Configuration Files

```json
{
  "laboratory": "psomagen",
  "disease": "prostate cancer",
  "group": "cancer",
  "batch": "AN00025834",
  "chrom": "1",
  "ctx": "CG",
  "output_dir": "/path/to/output",
  "samples": [],
  "add_samples": ["/path/to/sample1", "/path/to/sample2"],
  "min_coverage": 4,
  "α": 0.05,
  "distance_metrics": ["jensen_shannon", "wasserstein"],
  "min_metrics_agree": 0
}
```

### Using Command Line

```bash
python -m methylcentroid.cli \
  --laboratory "psomagen" \
  --disease "prostate cancer" \
  --group "cancer" \
  --batch "AN00025834" \
  --chromosome 1 \
  --context CG \
  --samples samples.csv \
  --output-dir /path/to/output
```

### Batch Processing

```json
{
  "chromosomes": ["1", "2", "3"],
  "contexts": ["CG", "CHG", "CHH"],
  "base_config": {
    "laboratory": "psomagen",
    "disease": "prostate cancer",
    "group": "cancer",
    "batch": "AN00025834",
    "chrom": "1",
    "ctx": "CG",
    "output_dir": "/path/to/output",
    "samples": [],
    "add_samples": ["/path/to/sample1", "/path/to/sample2"],
    ...
  },
  "parallel_combinations": 1,
  "continue_on_error": true
}
```

Note: Metadata fields are only specified in `base_config`, not at the batch level. This avoids redundancy.

## Reading Metadata from H5 Files

### Method 1: Using MethylSample Properties (Recommended)

The easiest way to access and modify metadata is through `MethylSample` properties:

```python
from methyl_utils import MethylSample

# Load centroid
centroid = MethylSample.load_from_h5('1-CG.h5')

# Read metadata properties
print(f"Laboratory: {centroid.laboratory}")
print(f"Disease: {centroid.disease}")
print(f"Group: {centroid.group}")
print(f"Batch: {centroid.batch}")
print(f"Chromosome: {centroid.chromosome}")
print(f"Context: {centroid.context}")

# Modify metadata properties (much cleaner than using dictionaries!)
centroid.laboratory = "new_lab"
centroid.disease = "updated_disease"
centroid.group = "control"
centroid.batch = "new_batch"

# Access all metadata
if centroid.metadata:
    print(f"All metadata: {centroid.metadata}")
    print(f"Samples: {centroid.metadata.get('samples')}")

# Save with updated metadata
centroid.save_to_h5('updated-1-CG.h5', metadata=centroid.metadata)
```

### Method 2: Using the Test Script

Use the provided test script to verify metadata in H5 files:

```bash
python methylcentroid/examples/test_metadata.py /path/to/centroid/1-CG.h5
```

Or the example script to see all metadata:

```bash
python methylcentroid/examples/example_metadata_access.py /path/to/centroid/1-CG.h5
```

### Method 3: Direct h5py Access

Or read directly using h5py:

```python
import h5py
import json

with h5py.File('1-CG.h5', 'r') as f:
    laboratory = f.attrs['laboratory']
    disease = f.attrs['disease']
    group = f.attrs['group']
    batch = f.attrs['batch']
    chromosome = f.attrs['chromosome']
    context = f.attrs['context']
    
    # Lists are stored as JSON
    samples = json.loads(f.attrs['samples'])
    distance_metrics = json.loads(f.attrs['distance_metrics'])
```

## Benefits

1. **Data Provenance**: Each centroid file is self-documenting with complete metadata
2. **Validation**: Pydantic ensures all required metadata is provided and valid
3. **Consistency**: Metadata format is standardized across all centroid files
4. **Traceability**: Easy to identify which samples contributed to which centroids
5. **Reproducibility**: All processing parameters are saved with the centroid

## Backward Compatibility

- Old code that doesn't provide metadata fields will need to be updated
- The metadata fields are now **required** in MethylCentroidConfig
- Existing H5 files without metadata will continue to work but won't have metadata attributes
- New centroids will automatically include all metadata

## Testing

Test and example scripts are provided in `methylcentroid/examples/`:

```bash
# Set up environment first
source setup_env.sh

# Test metadata reading from H5 file
python packages/methylcentroid/methylcentroid/examples/test_metadata.py /path/to/output/1-CG.h5

# Example of accessing and modifying metadata
python packages/methylcentroid/methylcentroid/examples/example_metadata_access.py /path/to/output/1-CG.h5

# Demo of R/W properties
python packages/methylcentroid/methylcentroid/examples/example_metadata_access.py --demo

# Validate configuration files
python packages/methylcentroid/methylcentroid/examples/validate_config.py
```

**Note:** All scripts require the `METHYLPIPELINE` environment variable. See `ENV_SETUP.md` for details.

