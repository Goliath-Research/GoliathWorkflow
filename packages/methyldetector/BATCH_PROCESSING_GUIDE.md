# MethylDetector Batch Processing Guide

## Overview

The `run_all_chromosomes_contexts.py` script automates running MethylDetector across all chromosome-context combinations using Docker.

## Quick Start

### Run All Chromosomes and Contexts

```bash
cd /home/ubuntu/MethylDetector
python run_all_chromosomes_contexts.py
```

This will process:
- **Chromosomes**: 1-22, X, Y
- **Contexts**: CG, CHG, CHH
- **Total**: 72 combinations (24 chromosomes × 3 contexts)

### Dry Run (Test Without Executing)

```bash
python run_all_chromosomes_contexts.py --dry-run
```

Shows what would be executed without actually running MethylDetector.

### Check Files First

```bash
python run_all_chromosomes_contexts.py --check-files
```

Verifies centroid files exist before processing (skips missing files).

### Continue on Errors

```bash
python run_all_chromosomes_contexts.py --continue-on-error
```

Keeps processing even if some chromosomes fail.

## Selective Processing

### Specific Chromosomes

```bash
# Process only chromosomes 1, 2, 3
python run_all_chromosomes_contexts.py --chromosomes 1 2 3

# Process only X and Y
python run_all_chromosomes_contexts.py --chromosomes X Y
```

### Specific Contexts

```bash
# Process only CG context
python run_all_chromosomes_contexts.py --contexts CG

# Process CG and CHG only
python run_all_chromosomes_contexts.py --contexts CG CHG
```

### Combined

```bash
# Process chromosomes 1-5, CG context only
python run_all_chromosomes_contexts.py --chromosomes 1 2 3 4 5 --contexts CG
```

## Configuration

### Modify Base Configuration

Edit the `BASE_CONFIG_TEMPLATE` in the script to change default parameters:

```python
BASE_CONFIG_TEMPLATE = {
    "centroid1_path": "/path/to/centroids/pb-healthy/{chrom}-{ctx}.h5",
    "centroid2_path": "/path/to/centroids/pb-cancer/{chrom}-{ctx}.h5",
    "output_dir": "/path/to/output",
    "alpha": 0.01,              # Q-value threshold
    "min_delta_mean": 0.2,      # Minimum delta mean
    "max_bc": 0.6,              # Maximum Bhattacharyya Coefficient
    "target_auc": 0.95,         # Target AUC for binary search
    "min_dmps_for_export": 1000, # Minimum DMPs to export
    "gamma": 1.5,               # Effect size gamma parameter
    "use_gpu": True,
    "random_state": 42
}
```

### Modify Chromosomes/Contexts

Edit the script's global variables:

```python
CHROMOSOMES = list(range(1, 23)) + ['X', 'Y']  # Modify as needed
CONTEXTS = ['CG', 'CHG', 'CHH']                # Modify as needed
```

## Output

### Config Files

Generated in `/home/ubuntu/MethylDetector/configs/`:
- `pb-ch-1-CG_config.json`
- `pb-ch-1-CHG_config.json`
- `pb-ch-1-CHH_config.json`
- ... (one per chromosome-context combination)

### MethylDetector Results

Output directory (default: `/home/ubuntu/Work/samples/.../detection/pb-ch/`):
- `biological_dmps-1-CG.csv`
- `biological_dmps-1-CHG.csv`
- `biological_dmps-1-CHH.csv`
- ... (one per successful run)

### Summary Report

At the end of execution:
```
==========================================
SUMMARY
==========================================
✅ Successful: 68
   • 1-CG
   • 1-CHG
   ...

❌ Failed: 2
   • 22-CHH
   • Y-CHG

⚠️  Skipped: 2
   • X-CHH
   • Y-CHH
==========================================
```

## Examples

### Production Run with Error Handling

```bash
python run_all_chromosomes_contexts.py \
    --check-files \
    --continue-on-error \
    2>&1 | tee methyldetector_batch.log
```

This will:
- Check if files exist before processing
- Continue even if some fail
- Log all output to `methyldetector_batch.log`

### Quick Test on a Few Chromosomes

```bash
python run_all_chromosomes_contexts.py \
    --chromosomes 21 22 \
    --contexts CG \
    --dry-run
```

### Process High-Priority Chromosomes First

```bash
# Process chromosomes with most known genes first
python run_all_chromosomes_contexts.py \
    --chromosomes 1 2 3 4 5 6 7 X \
    --check-files \
    --continue-on-error
```

## Monitoring Progress

### Watch Output in Real-Time

The script shows real-time output from MethylDetector, including:
- GPU initialization
- Processing progress
- DMP counts
- Timing information

### Check Intermediate Results

While running, you can check the output directory:

```bash
# Count completed files
ls -1 /home/ubuntu/Work/samples/.../detection/pb-ch/biological_dmps-*.csv | wc -l

# Check most recent output
ls -lt /home/ubuntu/Work/samples/.../detection/pb-ch/ | head
```

## Troubleshooting

### Permission Errors

If you see permission errors, ensure:
```bash
sudo chmod -R 777 /home/ubuntu/Work
```

### Docker Container Not Running

Start the container:
```bash
cd /home/ubuntu/Work/cuda
docker compose up -d
```

### Missing Centroid Files

Use `--check-files` to identify missing files:
```bash
python run_all_chromosomes_contexts.py --check-files --dry-run
```

### CuPy Cache Errors

Ensure `/home/ubuntu/.cupy` exists in container:
```bash
docker exec epimethyl mkdir -p /home/ubuntu/.cupy/kernel_cache
docker exec epimethyl chmod -R 777 /home/ubuntu/.cupy
```

### Memory Issues

If running out of memory, process in smaller batches:
```bash
# Process 5 chromosomes at a time
for i in {1..5} {6..10} {11..15} {16..20} {21..24}; do
    python run_all_chromosomes_contexts.py --chromosomes $i --continue-on-error
done
```

## Performance Tips

### Parallel Processing (Advanced)

For multiple GPUs or faster processing, modify the script to run contexts in parallel:

```bash
# Run each context separately in background
python run_all_chromosomes_contexts.py --contexts CG &
python run_all_chromosomes_contexts.py --contexts CHG &
python run_all_chromosomes_contexts.py --contexts CHH &
wait
```

**Warning**: Only use if you have multiple GPUs or enough memory!

### Estimate Time

Typical processing time per chromosome-context:
- Small chromosomes (21, 22): ~5-10 minutes
- Medium chromosomes (10-20): ~15-30 minutes
- Large chromosomes (1-5): ~30-60 minutes
- Total for all 72 combinations: ~20-40 hours

## Integration with Pipeline

### Complete Workflow

```bash
# 1. Run MethylDetector for all combinations
cd /home/ubuntu/MethylDetector
python run_all_chromosomes_contexts.py --check-files --continue-on-error

# 2. Map DMPs to genes (for each successful output)
cd /home/ubuntu/MethylMapper
for csv in /home/ubuntu/Work/.../detection/pb-ch/biological_dmps-*.csv; do
    basename=$(basename $csv .csv)
    methylmapper --input $csv \
                 --config db_config.json \
                 --sample-id 12345 \
                 --output-csv "${basename}_genes.csv" \
                 --output-json "${basename}_genes.json"
done

# 3. Run enrichment analysis (combine all genes)
cd /home/ubuntu/MethylEnricher
cat /path/to/*_genes.json | jq -r '.[]' | sort -u > all_genes.txt
methylenricher --input all_genes.txt --outdir enrichment_all
```

## Script Customization

The script is designed to be easily customizable. Common modifications:

1. **Change centroid paths**: Edit `BASE_CONFIG_TEMPLATE`
2. **Add custom filters**: Modify config template parameters
3. **Change chromosomes**: Edit `CHROMOSOMES` list
4. **Add logging**: Uncomment or add logging statements
5. **Change Docker settings**: Modify `DOCKER_CONTAINER` and `WORK_DIR`

## Help

View all options:
```bash
python run_all_chromosomes_contexts.py --help
```

## Exit Codes

- `0`: All successful (or dry-run)
- `1`: One or more failed (unless `--continue-on-error` used)

