# MethylPipeline Deployment Guide

This guide covers supported execution environments and installation patterns for the monorepo.

## Supported Platforms

- Linux (primary target)
- macOS (development-friendly)
- Windows via WSL2 (best effort, not official)

## Recommended: Host `.venv` Setup

From repository root (canonical):

```bash
bash scripts/setup_host.sh --system-deps --with-deps
source .venv/bin/activate
```

This creates `.venv`, installs editable packages from `scripts/packages.list`, and optional pipeline/GPU dependency sets.

Alternative (manual):

```bash
python3.12 -m venv .venv
source .venv/bin/activate
bash scripts/install_all.sh
# optional: bash scripts/install_all.sh --pipeline-reqs --gpu-reqs
```

Smoke check (canonical orchestration first):

```bash
methyl-workflow-run --help
methyl-stability-freeze-readiness --help
methyl-validation --help   # legacy / transitional only
```

### Presentation tooling (Marp)

Presentation decks under `docs/presentations/` use Marp-compatible Markdown.
Install Marp CLI with Node.js/npm:

```bash
npm install -g @marp-team/marp-cli
marp --version
```

Then render decks, for example:

```bash
marp "docs/presentations/methylpipeline-theory-implementation.md" --html
marp "docs/presentations/methylpipeline-workflows-model-prediction.md" --html
```

### Rule: always use `.venv`

Run tests and CLI tools from the local virtual environment:

```bash
source .venv/bin/activate
make test
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
docker exec -w /workspace methylpipeline methyl-workflow-run --help
docker exec -w /workspace methylpipeline marp --version
```

## Documentation Contract

Each package should provide:

- `README.md` (entrypoint)
- `docs/USAGE.md` (operational usage)
- `docs/IMPLEMENTATION.md` (code/architecture notes)
- `docs/THEORY.md` (method summary + theory-book pointer)

Canonical index for documentation map:

- [`docs/index.md`](index.md)
