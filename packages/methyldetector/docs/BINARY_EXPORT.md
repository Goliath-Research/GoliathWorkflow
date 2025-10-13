# Binary Export Functionality

MethylDetector now supports binary export of differentially methylated positions (DMPs) and differentially methylated regions (DMRs) in addition to the existing CSV format. This enables efficient data storage and fast loading for downstream analysis with tools like DuckDB.

## Overview

The binary export functionality automatically creates files with the following naming convention:
- **DMP files**: `{chr}-{ctx}-dmp.{ext}` for differentially methylated positions
- **DMR files**: `{chr}-{ctx}-dmr.{ext}` for differentially methylated regions

Where:
- `{chr}` = chromosome number (e.g., "1", "2", "3")
- `{ctx}` = methylation context (e.g., "CG", "CHG", "CHH")
- `{ext}` = file extension (`.parquet` or `.h5`)

## Supported Formats

### 1. Parquet Format (`.parquet`)
- **Compression**: Snappy compression for optimal speed/size balance
- **Advantages**: 
  - Excellent compression ratios
  - Fast read/write performance
  - Column-oriented storage (great for analytical queries)
  - Native support in DuckDB, pandas, and other data tools

### 2. HDF5 Format (`.h5`)
- **Compression**: Z-standard compression (level 9) for maximum compression
- **Advantages**:
  - Smallest file sizes
  - Hierarchical structure with metadata
  - Rich metadata attributes
  - Excellent for archival storage

## File Structure

### DMP Files
Contain all significant differentially methylated positions with columns:
- `position`: Genomic position
- `test_statistic`: Likelihood ratio test statistic
- `p_value`: Raw p-value
- `q_value`: FDR-corrected p-value
- `method`: Statistical method used ("NormalApprox" or "LRT")
- `mean1`, `mean2`: Mean methylation levels for each condition
- `variance1`, `variance2`: Variance of methylation levels
- `alpha1`, `beta1`, `alpha2`, `beta2`: Beta distribution parameters
- `alpha_combined`, `beta_combined`: Combined distribution parameters
- `n1`, `n2`: Sample sizes for each condition
- `significant`: Whether position is statistically significant
- `fallback_used`: Whether fallback method was used
- `global_significant`: Whether position is globally significant

### DMR Files
Contain grouped significant regions with columns:
- `start_position`: Start of significant region
- `end_position`: End of significant region
- `region_size`: Size of region in base pairs
- `chromosome`: Chromosome identifier
- `context`: Methylation context

## Usage

### Automatic Export
Binary export happens automatically when running MethylDetector analysis. No additional configuration is needed - files are created alongside the existing CSV outputs.

```python
from methyl_detector import MethylDetector
from methyl_detector.models.config import MethylDetectorConfig

config = MethylDetectorConfig(
    centroid1_path="data/WT/1-CG.h5",
    centroid2_path="data/msh1/1-CG.h5",
    output_dir="results",
    alpha=0.05
)

detector = MethylDetector(config)
result = detector.run()

# Binary files are automatically created:
# - 1-CG-dmp.parquet
# - 1-CG-dmp.h5
# - 1-CG-dmr.parquet
# - 1-CG-dmr.h5
```

### Command Line
```bash
# Single comparison (creates binary files automatically)
methyl-detector \
    --centroid1 data/WT/1-CG.h5 \
    --centroid2 data/msh1/1-CG.h5 \
    --output-dir results

# Multiple comparisons (creates binary files for each chr-ctx combination)
methyl-detector \
    --centroid1-dir data/WT/centroids \
    --centroid2-dir data/msh1/centroids \
    --chromosomes 1,2,3,4,5 \
    --contexts CG,CHG,CHH \
    --output-dir results
```

## Loading with DuckDB

The binary files are optimized for loading with DuckDB for efficient downstream analysis:

### Loading Parquet Files
```sql
-- Load DMP data
CREATE TABLE dmps AS SELECT * FROM read_parquet('1-CG-dmp.parquet');

-- Load DMR data
CREATE TABLE dmrs AS SELECT * FROM read_parquet('1-CG-dmr.parquet');

-- Query examples
SELECT COUNT(*) FROM dmps WHERE significant = true;
SELECT AVG(test_statistic) FROM dmps WHERE q_value < 0.05;
```

### Loading HDF5 Files
```python
import h5py
import pandas as pd

# Load DMP data
with h5py.File('1-CG-dmp.h5', 'r') as f:
    dmp_group = f['dmp_data']
    
    # Get metadata
    chromosome = dmp_group.attrs['chromosome']
    context = dmp_group.attrs['context']
    total_positions = dmp_group.attrs['total_positions']
    
    # Convert to pandas DataFrame
    data = {}
    for col in dmp_group.keys():
        data[col] = dmp_group[col][:]
    
    df = pd.DataFrame(data)
    print(f"Loaded {len(df)} DMP positions from chromosome {chromosome}, context {context}")
```

## Performance Comparison

### File Sizes
Typical compression ratios compared to CSV:
- **Parquet**: 2-5x smaller than CSV
- **HDF5 (Z-standard)**: 3-8x smaller than CSV

### Loading Performance
- **Parquet**: Fastest loading, excellent for analytical queries
- **HDF5**: Fast loading with rich metadata
- **CSV**: Slowest loading, largest file sizes

## Configuration

No additional configuration is needed for binary export. The functionality is enabled by default and will:

1. Automatically detect chromosome and context from input filenames
2. Create appropriately named output files
3. Use optimal compression settings for each format
4. Maintain all statistical information from the analysis

## Error Handling

The binary export methods include robust error handling:
- Graceful fallback if pandas is not available
- Detailed logging of export operations
- Non-blocking errors (analysis continues even if export fails)
- Informative error messages for troubleshooting

## Dependencies

Binary export requires:
- `pandas` (for data manipulation and Parquet export)
- `h5py` (for HDF5 export)
- `hdf5plugin` (for Z-standard compression)

These dependencies are already included in the project requirements.

## Examples

See `examples/binary_export_example.py` for a complete demonstration of the binary export functionality.

## Troubleshooting

### Common Issues

1. **Files not created**: Check if significant results were found in the analysis
2. **Permission errors**: Ensure write access to the output directory
3. **Import errors**: Verify that pandas and h5py are properly installed
4. **File size issues**: Check available disk space for large datasets

### Debug Mode
Enable verbose logging to see detailed export information:
```bash
methyl-detector --verbose --centroid1 ... --centroid2 ...
```

## Future Enhancements

Planned improvements to the binary export functionality:
- Configurable compression levels
- Additional export formats (Arrow, Feather)
- Streaming export for very large datasets
- Custom column selection for export
- Batch export for multiple analyses
