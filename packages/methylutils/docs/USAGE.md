# MethylUtils Usage Guide

## Overview

MethylUtils is primarily a **library** used by the other MethylPipeline packages (MethylCentroid, MethylDetector, MethylClassifier, MethylPredictor). You install MethylUtils first; then you install and run those tools. There are **two ways** to have MethylUtils available:

1. **Docker container** — Use the MethylPipeline image; MethylUtils is pre-installed.
2. **Local host with virtual environment** — Create a venv, activate it, and install MethylUtils (then install any other package you need).

Use one or the other; once MethylUtils is available, the other packages use it the same way.

---

## Setup 1: Docker container

Use this when you want a single, reproducible environment (e.g. shared GPU, CI, or no local Python install).

**Prerequisites:** Docker; for GPU, NVIDIA Container Toolkit.

**1. Start the container**

From the MethylPipeline repo:

```bash
cd /path/to/MethylPipeline/docker
docker compose up -d
```

(Use the same container name as in your compose file; below assumes `methylpipeline` and the repo mounted at `/workspace`.)

**2. MethylUtils inside the container**

MethylUtils is already installed in the image. When you run MethylCentroid, MethylDetector, MethylClassifier, or MethylPredictor inside the container (e.g. via `docker exec ...`), they use this MethylUtils. You do not need to install MethylUtils separately.

**3. Optional: run MethylUtils tests**

From the host:

```bash
docker exec -w /workspace methylpipeline pytest packages/methylutils/ -v
```

Paths must be valid inside the container (e.g. `/workspace/...`).

---

## Setup 2: Local host with virtual environment

Use this when you run on the host (e.g. your laptop or a login node) and want to activate a virtual environment before running any pipeline tool.

**Prerequisites:** Python 3.10+ (repository target is `<3.13`). Optional: CuPy for GPU acceleration.

**1. Create a virtual environment**

From the **MethylPipeline repository root** (canonical directory is `.venv`):

```bash
cd /path/to/MethylPipeline
python3.12 -m venv .venv
```

**2. Activate the virtual environment**

```bash
source .venv/bin/activate
```

On Windows: `.venv\Scripts\activate`. After activation, your shell prompt usually shows `(.venv)`.

**3. Install MethylUtils first**

From the MethylPipeline repo root:

```bash
pip install -e packages/methylutils
```

Or from the package directory:

```bash
cd /path/to/MethylPipeline/packages/methylutils
pip install -e .
```

**4. Optional: GPU support**

If you have CUDA and want GPU acceleration for metrics and heavy processing:

```bash
pip install cupy-cuda12x   # adjust to your CUDA version (e.g. cupy-cuda11x)
```

**5. Install other packages as needed**

MethylCentroid, MethylDetector, MethylClassifier, and MethylPredictor **all require MethylUtils to be installed first**. After MethylUtils is installed, install any of them, for example:

```bash
pip install -e packages/methylcentroid
pip install -e packages/methyldetector
pip install -e packages/methylclassifier
pip install -e packages/methylpredictor
```

Each of those packages has its own [USAGE](../../methylcentroid/docs/USAGE.md) (or equivalent) for their CLI and options; they all assume MethylUtils is already available in the environment.

---

## Install order summary

| Order | Package | Note |
|-------|---------|------|
| 1 | **MethylUtils** | Required by all others. |
| 2 | MethylCentroid, MethylDetector, MethylClassifier, MethylPredictor | Any subset; can be installed in any order after MethylUtils. |

---

## Related documentation

- [THEORY.md](THEORY.md) — Code-backed theoretical summary and pointer to the canonical theory chapters.
- [COHORT_TREE.md](COHORT_TREE.md) — `diseases.groups[].stages` as generic strata, leaf labels, comparisons, v2 spike appendix.
- [IMPLEMENTATION.md](IMPLEMENTATION.md) — Package layout and how downstream packages use MethylUtils.
- [../../../docs/theory/README.md](../../../docs/theory/README.md) — Canonical publication-grade theory book for the repository.
