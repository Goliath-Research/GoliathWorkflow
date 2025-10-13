# Production Deployment Guide

This guide covers deploying MethylPipeline in production environments.

## Overview

Production deployment differs from development in several key ways:

- Packages are installed **inside the container** (not mounted as volumes)
- Packages are installed as **regular packages** (not editable)
- **Version pinning** ensures reproducible deployments
- **Health checks** monitor container status
- **Restart policies** ensure availability

## Production Setup

### Prerequisites

- Docker with GPU support
- NVIDIA Driver 525.60.13+
- CUDA 12.8+
- Sufficient disk space for container images

### Build Production Container

```bash
cd /home/ubuntu/MethylPipeline
bash scripts/setup_prod.sh
```

This will:
1. Build production container with all packages installed
2. Start the container
3. Verify installation

### Manual Production Build

If you need more control:

```bash
cd /home/ubuntu/MethylPipeline/docker

# Build production image
docker compose -f docker-compose.production.yml build

# Start production container
docker compose -f docker-compose.production.yml up -d

# Verify
docker exec methylpipeline-prod python3 -c "from methyl_utils import get_logger; print('OK')"
```

## Container Management

### Start/Stop Container

```bash
# Start
./scripts/run_container.sh prod start

# Stop
./scripts/run_container.sh prod stop

# Restart
./scripts/run_container.sh prod restart
```

### View Logs

```bash
./scripts/run_container.sh prod logs
```

### Execute Commands

```bash
# Open shell
docker exec -it methylpipeline-prod bash

# Run Python script
docker exec methylpipeline-prod python3 /path/to/script.py

# Run specific command
docker exec methylpipeline-prod methylclassifier --help
```

## Version Management

### Tagging Releases

Production containers should be tagged with version numbers:

```bash
# Tag production image
docker tag methylpipeline-gpu-env:production methylpipeline-gpu-env:v1.0.0

# Push to registry (if using)
docker push methylpipeline-gpu-env:v1.0.0
```

### Version Pinning

All package versions should be pinned in `requirements.txt` files:

```txt
# Good
numpy==1.24.0
scipy==1.11.0

# Bad
numpy
scipy>=1.11.0
```

## Health Monitoring

### Container Health Check

The production container includes a health check:

```bash
# Check container health
docker inspect methylpipeline-prod --format='{{.State.Health.Status}}'
```

### GPU Monitoring

Monitor GPU usage in production:

```bash
# Inside container
nvidia-smi

# Watch GPU usage
watch -n 1 nvidia-smi

# Use nvidia-ml-py
python3 -c "import pynvml; pynvml.nvmlInit(); print(pynvml.nvmlDeviceGetName(pynvml.nvmlDeviceGetHandleByIndex(0)))"
```

### Application Monitoring

Implement monitoring in your applications:

```python
from methyl_utils.monitoring import GPUMonitor, MemoryMonitor

# Monitor GPU
gpu_monitor = GPUMonitor()
metrics = gpu_monitor.get_metrics()
print(f"GPU Utilization: {metrics['utilization']}%")

# Monitor memory
memory_monitor = MemoryMonitor()
memory_info = memory_monitor.get_memory_info()
print(f"Available Memory: {memory_info['available_gb']} GB")
```

## Performance Optimization

### Container Resources

Adjust container resources in `docker-compose.production.yml`:

```yaml
deploy:
  resources:
    limits:
      cpus: '16'
      memory: 128G
    reservations:
      cpus: '8'
      memory: 64G
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu]
```

### Shared Memory

For large GPU workloads, increase shared memory:

```yaml
shm_size: '32gb'  # Increase if needed
```

### Environment Variables

Optimize via environment variables:

```yaml
environment:
  - CUDA_VISIBLE_DEVICES=0
  - OMP_NUM_THREADS=16
  - MKL_NUM_THREADS=16
  - CUPY_CACHE_DIR=/home/ubuntu/.cupy/kernel_cache
  - PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
```

## Backup and Recovery

### Backup Container Configuration

```bash
# Export container configuration
docker inspect methylpipeline-prod > container-config.json

# Export image
docker save methylpipeline-gpu-env:production -o methylpipeline-prod.tar
```

### Backup Data

Backup mounted volumes:

```bash
# Backup working directory
tar -czf working_dir_backup.tar.gz /home/ubuntu/working_dir
```

### Restore from Backup

```bash
# Load image
docker load -i methylpipeline-prod.tar

# Restore data
tar -xzf working_dir_backup.tar.gz -C /
```

## Security

### User Permissions

The container runs as user `ubuntu` (UID 999):

```yaml
user: "999:999"
```

### Network Security

Production containers should use secure networks:

```yaml
networks:
  methylpipeline_net:
    driver: bridge
    internal: true  # No external access if not needed
```

### Secrets Management

Never hardcode secrets. Use Docker secrets or environment files:

```bash
# Create secret
echo "my_secret_key" | docker secret create db_password -

# Use in compose
secrets:
  db_password:
    external: true
```

## Troubleshooting

### Container Crashes

```bash
# Check logs
docker compose -f docker/docker-compose.production.yml logs

# Check exit code
docker inspect methylpipeline-prod --format='{{.State.ExitCode}}'

# Restart
docker compose -f docker/docker-compose.production.yml restart
```

### GPU Errors

```bash
# Verify GPU access
docker exec methylpipeline-prod nvidia-smi

# Check CUDA
docker exec methylpipeline-prod python3 -c "import cupy; print(cupy.cuda.runtime.getDeviceCount())"
```

### Performance Issues

```bash
# Check resource usage
docker stats methylpipeline-prod

# Profile application
docker exec methylpipeline-prod python3 -m cProfile script.py
```

## Deployment Checklist

- [ ] All tests pass
- [ ] Versions pinned in requirements.txt
- [ ] Container builds successfully
- [ ] Health checks pass
- [ ] GPU access verified
- [ ] Monitoring configured
- [ ] Backup strategy in place
- [ ] Documentation updated
- [ ] Production configuration reviewed
- [ ] Security settings verified

## Scaling

### Multi-VM Deployment

For distributed deployments:

1. **Shared Storage**: Mount shared NFS/GlusterFS volumes
2. **Load Balancing**: Use nginx or HAProxy
3. **Job Queue**: Use Celery or RQ for distributed tasks
4. **Container Orchestration**: Consider Kubernetes for large deployments

### Kubernetes Deployment

For Kubernetes, create appropriate manifests:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: methylpipeline
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: methylpipeline
        image: methylpipeline-gpu-env:production
        resources:
          limits:
            nvidia.com/gpu: 1
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Build Production

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Build production image
        run: |
          cd docker
          docker compose -f docker-compose.production.yml build
      - name: Push to registry
        run: docker push methylpipeline-gpu-env:production
```

## Support

For production issues, please contact the development team or open a critical issue on the repository.

