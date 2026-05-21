# MethylPipeline Deployment Guide

This guide covers supported execution environments and installation patterns for the monorepo.

## Supported Platforms

- Linux (primary target)
- macOS (development-friendly)
- Windows via WSL2 (best effort, not official)

## Recommended: Host `.venv` Setup

From repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

Install packages in editable mode (minimum + common pipeline stack):

```bash
pip install -e packages/methylutils
pip install -e packages/methylcentroid
pip install -e packages/methyldetector
pip install -e packages/methylclassifier
pip install -e packages/methylpredictor
pip install -e packages/methylmapper
pip install -e packages/methylenricher
pip install -e packages/methyldiseaseprogression
pip install -e packages/methylalignmentqc
pip install -e packages/methylvalidation
```

Smoke check:

```bash
methyl-validation --help
methyl-stability-freeze-readiness --help
```

### Rule: always use `.venv`

Run tests and CLI tools from the local virtual environment:

```bash
source .venv/bin/activate
pytest
```

or one-shot:

```bash
./.venv/bin/python -m pytest
```

## Docker Deployment

Use containerized execution when you need strict environment reproducibility or GPU runtime isolation.

- Compose-based flows are available under `docker/`.
- Ensure mounted paths match paths referenced in project configs.
- Run CLI commands inside container with the repo mount as working directory.

Example:

```bash
cd docker
docker compose up -d
docker exec -w /workspace methylpipeline methyl-validation --help
```

## Documentation Contract

Each package should provide:

- `README.md` (entrypoint)
- `docs/USAGE.md` (operational usage)
- `docs/IMPLEMENTATION.md` (code/architecture notes)
- `docs/THEORY.md` (method summary + theory-book pointer)

Canonical index for documentation map:

- [`docs/index.md`](index.md)
