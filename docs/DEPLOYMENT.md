# MethylPipeline Deployment Guide

This guide covers the deployment of the MethylPipeline solution across our supported platforms. The project is structured as a monorepo containing multiple packages, all of which share the core `MethylUtils` library.

## Supported Platforms
- **Linux** (Ubuntu 20.04+, CentOS 8+)
- **macOS** (Apple Silicon or Intel)

*Note: Windows is not officially supported, though it may work via WSL2.*

---

## 1. Virtual Environment Deployment (Host)

The recommended deployment strategy for development and local execution is using a Python virtual environment. The canonical path for this isolated environment is `MethylPipeline/.venv`.

### Step 1: Initialize the Environment
From the repository root (`MethylPipeline/`), create the environment:
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

### Step 2: Install Core Library
Because all services rely on the core mathematical and foundational utilities provided by `MethylUtils`, it must be installed first:
```bash
cd packages/methylutils
pip install -e .
cd ../../
```

### Step 3: Install Desired Packages
Each package can be installed similarly. Because of the consistent monorepo structure, every package acts as an isolated application depending on `methylutils`.
```bash
cd packages/methyldetector
pip install -e .
```

### Running tests and pipeline programs

**All** `pytest` runs, `python -m ...` invocations, and installed pipeline CLIs (`methyl-centroid`, `methyl-detector`, `methyl-classifier`, `methyl-predictor`, `methyl-validation`, etc.) must use this virtual environment—do not rely on system Python for project code.

From the repository root, with the environment active:

```bash
source .venv/bin/activate
pytest
```

Equivalent one-shot forms (no `activate` needed):

```bash
./.venv/bin/python -m pytest
./.venv/bin/methyl-centroid --help
```

The repo provides [`scripts/run_tests.sh`](../scripts/run_tests.sh), which runs `pytest` via `.venv/bin/python` and errors if `.venv` is missing.

---

## 2. Docker Container Deployment

For production, cloud orchestration, or complex multi-node batch execution, deploying via Docker container ensures that system-level dependencies (such as CUDA/cuDF for GPU acceleration) are perfectly stable.

### Step 1: Base Image
Because `MethylUtils` optimally uses GPU arrays, we recommend using an NVIDIA CUDA-enabled base image. `nvcr.io/nvidia/rapidsai/rapidsai-core` is commonly used.

### Step 2: Dockerfile Example
Create a `Dockerfile` at the root of `MethylPipeline`:
```Dockerfile
FROM nvcr.io/nvidia/rapidsai/rapidsai-core:23.08-cuda11.8-base-ubuntu22.04-py3.10

WORKDIR /app
COPY . /app

# Install MethylUtils first (Core dependency)
RUN pip install -e packages/methylutils

# Install all other packages (e.g., methyldetector, methylcentroid)
RUN pip install -e packages/methylcentroid \
    && pip install -e packages/methyldetector \
    && pip install -e packages/methylclassifier

ENV PYTHONPATH="/app"
ENTRYPOINT ["python", "-m", "methyl_detector"]
```

### Step 3: Build and Run
```bash
docker build -t methylpipeline:latest .
docker run --gpus all -v /data:/data methylpipeline:latest \
    --centroid1-dir /data/c1 --centroid2-dir /data/c2 --chromosome 1
```

---

## 3. Package Consistency
To ensure the pipeline is maintainable, all packages follow a strict structural contract:
- **`THEORY.md`**: Contains all advanced mathematical formulas and justifications (e.g., ECDF overlap, KS tests).
- **`IMPLEMENTATION.md`**: Details code structure, memory scaling, and structural decisions.
- **`USAGE.md`**: CLI arguments, Python API snippets, and configuration parameters.
- **`README.md`**: High-level functionality and routing.

All packages strictly share `MethylUtils` as their foundation for metrics, memory management, and file I/O to avoid code duplication across services.
