# Run All Chromosomes - Usage Guide

This directory contains scripts to run MethylModeler analysis for all chromosomes (4-22 and X) across all contexts (CG, CHG, CHH).

## Prerequisites

- **Container must be running**: Ensure the `methylpipeline` Docker container is running
  ```bash
  docker ps | grep methylpipeline
  ```
- **Run on host**: These scripts run on the Ubuntu host (not inside the container)
- **GPU available**: Scripts will use GPU inside the container for analysis
- **How it works**: The `md` wrapper script automatically handles running commands inside the container

## Files

- **`run_all_chromosomes.sh`**: Sequential execution (one at a time)
- **`run_all_chromosomes_parallel.sh`**: Parallel execution (multiple at once)

## Quick Start

### Sequential Execution (Safest)

Runs one analysis at a time. Slower but uses minimal GPU memory:

```bash
cd /home/ubuntu/MethylPipeline/packages/methylmodeler
./run_all_chromosomes.sh
```

**Estimated time**: ~12-24 hours (depending on chromosome size)

### Parallel Execution (Faster)

Runs multiple analyses simultaneously:

```bash
cd /home/ubuntu/MethylPipeline/packages/methylmodeler

# Run with 3 parallel jobs (default)
./run_all_chromosomes_parallel.sh

# Run with custom number of parallel jobs
./run_all_chromosomes_parallel.sh 5
```

**Estimated time**: ~4-8 hours with 3 parallel jobs

⚠️ **GPU Memory Requirements**:
- 1 job: ~5-10 GB GPU RAM
- 3 jobs: ~15-30 GB GPU RAM
- 5 jobs: ~25-50 GB GPU RAM

Adjust based on your available GPU memory (you have ~77 GB available).

## Output

### Sequential Script
- **Log file**: `run_all_YYYYMMDD_HHMMSS.log`
- All output in a single file
- Progress shown in terminal

### Parallel Script
- **Log directory**: `logs_YYYYMMDD_HHMMSS/`
- **Main log**: `logs_YYYYMMDD_HHMMSS/main.log` (summary)
- **Individual logs**: `logs_YYYYMMDD_HHMMSS/{chrom}-{ctx}.log` (per analysis)

## Monitoring Progress

### Sequential Script
```bash
# Watch progress in real-time
tail -f run_all_*.log

# Count completed analyses
grep "SUCCESS\|FAILED" run_all_*.log | wc -l
```

### Parallel Script
```bash
# Watch main log
tail -f logs_*/main.log

# Count completed/running jobs
grep "SUCCESS\|FAILED" logs_*/main.log | wc -l

# Check specific chromosome
cat logs_*/10-CG.log
```

## Analysis Details

### Scope
- **Chromosomes**: 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, X
- **Contexts**: CG, CHG, CHH
- **Total**: 60 analyses (20 chromosomes × 3 contexts)

### Configuration
Each analysis uses:
- ✅ Validation-accuracy optimization (`optimize_for_validation_accuracy: true`)
- ✅ Binary search with sampling for optimal k
- ✅ Real validation samples (35 healthy + 61 cancer)
- ✅ Target AUC: 0.9999
- ✅ Max k: 50,000 DMPs

### Expected Results
- **CG context**: ~20K-30K DMPs, 95-100% accuracy
- **CHG context**: ~5K-15K DMPs, 90-99% accuracy
- **CHH context**: ~3K-5K DMPs (limited by available DMPs), 85-95% accuracy

## Troubleshooting

### Container Not Running
```bash
# Check if container is running
docker ps | grep methylpipeline

# If not running, start it
docker start methylpipeline

# Or check container status
docker ps -a | grep methylpipeline
```

### Out of GPU Memory
```bash
# Reduce parallel jobs
./run_all_chromosomes_parallel.sh 2

# Or use sequential mode
./run_all_chromosomes.sh
```

### Restart Failed Analyses
Check which analyses failed:
```bash
grep "FAILED" logs_*/main.log
```

Run specific chromosome/context manually:
```bash
./md configs/pb-hc12-10-CG_config.json
```

### Check Specific Analysis
```bash
# View detailed log for chromosome 10, CG context
cat logs_*/10-CG.log

# Check for errors
grep -i "error\|failed" logs_*/10-CG.log
```

## Output Files

Each analysis produces:
```
/home/ubuntu/Work/samples/humans/psomagen/AN00026418/detection/pb-hc-12/
├── classifier-{chrom}-{ctx}.pkl      # Trained classifier model
├── dmps-{chrom}-{ctx}.csv            # Selected DMPs with metadata
├── dmps-{chrom}-{ctx}.h5             # DMPs in HDF5 format
└── result-{chrom}-{ctx}.json         # Analysis results summary
```

## Performance Tips

### Optimize for Speed
1. **Use parallel execution** if you have sufficient GPU memory
2. **Increase parallel jobs** if memory allows: `./run_all_chromosomes_parallel.sh 5`
3. **Run during off-hours** to avoid competition for resources

### Optimize for Memory
1. **Use sequential execution** for guaranteed completion
2. **Adjust DE parameters** (`de_max_iterations`, `de_population_size`) if needed
3. **Process large chromosomes separately** (chr 1, 2 already done)

## Estimated Completion Times

Based on chromosome 1-2 results:

| Mode | Parallel Jobs | Total Time | Time per Analysis |
|------|--------------|------------|-------------------|
| Sequential | 1 | ~15-20 hours | ~15-20 min |
| Parallel | 3 | ~5-7 hours | ~15-20 min |
| Parallel | 5 | ~3-5 hours | ~15-20 min |

*Times vary based on chromosome size and available DMPs*

## Example Session

```bash
# Navigate to directory
cd /home/ubuntu/MethylPipeline/packages/methylmodeler

# Start parallel execution with 3 jobs
./run_all_chromosomes_parallel.sh 3

# In another terminal, monitor progress
watch -n 10 'grep -c "SUCCESS\|FAILED" logs_*/main.log'

# Check results when complete
ls -lh /home/ubuntu/Work/samples/humans/psomagen/AN00026418/detection/pb-hc-12/
```

## Support

If analyses fail consistently:
1. Check individual log files in `logs_*/`
2. Verify centroid files exist and are readable
3. Check GPU memory usage: `nvidia-smi`
4. Verify config files are valid JSON

---

**Happy analyzing!** 🧬🔬

