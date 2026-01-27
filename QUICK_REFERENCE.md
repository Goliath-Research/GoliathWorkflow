# MethylPipeline Quick Reference

Quick reference for common commands and workflows.

## Container Management

### Development Container

```bash
# Setup (first time)
cd /home/ubuntu/MethylPipeline
bash scripts/setup_dev.sh

# Start
./scripts/run_container.sh dev start

# Stop
./scripts/run_container.sh dev stop

# Restart
./scripts/run_container.sh dev restart

# Open shell
./scripts/run_container.sh dev shell

# View logs
./scripts/run_container.sh dev logs
```

### Production Container

```bash
# Setup (first time)
cd /home/ubuntu/MethylPipeline
bash scripts/setup_prod.sh

# Start
./scripts/run_container.sh prod start

# Stop
./scripts/run_container.sh prod stop

# Open shell
docker exec -it methylpipeline-prod bash
```

## Package Management

### Install All Packages (Inside Container)

```bash
bash /workspace/scripts/install_all.sh
```

### Install Single Package (Inside Container)

```bash
cd /workspace/packages/methylutils
pip install -e .
```

### Test Imports (Inside Container)

```bash
python -c "from methyl_utils import get_logger; print('OK')"
python -c "from methyl_detector import MethylDetector; print('OK')"
python -c "from methyl_classifier import MethylClassifier; print('OK')"
```

## Testing

```bash
# All tests
pytest /workspace/packages/

# Specific package
pytest /workspace/packages/methylutils/tests/

# With coverage
pytest --cov=/workspace/packages/ /workspace/packages/

# GPU tests only
pytest -m gpu /workspace/packages/

# Parallel execution
pytest -n auto /workspace/packages/
```

## GPU Monitoring

```bash
# Check GPU
nvidia-smi

# Watch GPU usage
watch -n 1 nvidia-smi

# Check CUDA
python -c "import cupy; print(cupy.cuda.runtime.getDeviceCount())"

# GPU memory info
python -c "from methyl_utils.gpu_utils import check_gpu_memory; print(check_gpu_memory())"
```

## Docker Commands

### Development

```bash
cd /home/ubuntu/MethylPipeline/docker

# Build
docker compose build

# Start
docker compose up -d

# Stop
docker compose down

# Logs
docker compose logs -f

# Exec command
docker exec methylpipeline <command>

# Shell
docker exec -it methylpipeline bash
```

### Production

```bash
cd /home/ubuntu/MethylPipeline/docker

# Build
docker compose -f docker-compose.production.yml build

# Start
docker compose -f docker-compose.production.yml up -d

# Stop
docker compose -f docker-compose.production.yml down
```

## File Paths

### Host Machine

```
/home/ubuntu/MethylPipeline/
├── packages/          # Source code
├── docker/           # Container configs
├── scripts/          # Utility scripts
└── docs/            # Documentation
```

### Inside Container (Development)

```
/workspace/
├── packages/         # Mounted, editable
├── scripts/         # Scripts
└── docs/           # Docs
```

### Inside Container (Production)

```
/opt/methylpipeline/  # Python environment
/home/ubuntu/         # Working directory
```

## Environment Variables (Inside Container)

```bash
echo $PYTHONPATH
# /workspace/packages/methylutils:/workspace/packages/methylcentroid:/workspace/packages/methylcluster:/workspace/packages/methyldetector:/workspace/packages/methylclassifier:/workspace/packages/methylmapper:/workspace/packages/methylenricher

echo $METHYL_UTILS_PATH
# /workspace/packages/methylutils

echo $CUDA_VISIBLE_DEVICES
# 0

echo $CUPY_CACHE_DIR
# /home/ubuntu/.cupy/kernel_cache
```

## Common Workflows

### Development Workflow

```bash
# 1. Start container
./scripts/run_container.sh dev start

# 2. Attach
docker exec -it methylpipeline bash

# 3. Make changes (on host)
# Edit files in /home/ubuntu/MethylPipeline/packages/

# 4. Test changes (in container)
pytest /workspace/packages/methylutils/tests/

# 5. Commit changes (on host)
git add .
git commit -m "Description"
```

### Run Analysis

```bash
# Inside container
python -m methyl_detector.cli config.json
```

### Debugging

```bash
# Inside container with ipdb
pip install ipdb

# Add to code:
import ipdb; ipdb.set_trace()

# Run script
python script.py
```

## Package Versions

Check installed versions:

```bash
pip list | grep -E "(cupy|numpy|pandas|methylutils)"
```

## Troubleshooting

### Container won't start

```bash
docker compose logs
nvidia-smi
docker ps -a
```

### Import errors

```bash
docker exec methylpipeline bash /workspace/scripts/install_all.sh
```

### Permission errors

```bash
# On host
sudo chown -R ubuntu:ubuntu /home/ubuntu/MethylPipeline
```

### GPU errors

```bash
nvidia-smi
docker exec methylpipeline python -c "import cupy; print(cupy.__version__)"
```

## Quick Links

- [Full README](README.md)
- [Development Guide](docs/DEVELOPMENT.md)
- [Production Guide](docs/PRODUCTION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Migration Guide](MIGRATION_GUIDE.md)

## Package CLI Commands

### MethylClassifier

```bash
methylclassifier --config config.yaml
```

Build multi-class model:

```bash
python packages/methylclassifier/build_multiclass_model.py \
  packages/methylclassifier/configs/example_multiclass_model.json
```

### MethylDetector

```bash
python -m methyl_detector.cli --help
```

### MethylMapper (Bedtools, Recommended)

```bash
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" --enrich-disease
```

### MethylMapper (Azure SQL)

```bash
python -m methylmapper --config config.json
```

### MethylEnricher

```bash
methyl_enricher --input mapped_features/all-gene_name-combined.csv \
               --gene-column gene_name \
               --top 200
```

## System Requirements

- GPU: NVIDIA GH200 (96GB) or compatible
- CUDA: 12.8+
- Docker: with nvidia-docker2
- Python: 3.10
- Storage: NVMe SSD recommended

## Support

- Documentation: `/home/ubuntu/MethylPipeline/docs/`
- Issues: Open on repository
- Logs: `docker compose logs`

