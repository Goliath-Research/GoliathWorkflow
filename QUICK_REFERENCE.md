# Quick Reference

## Install

Host:

```bash
bash scripts/setup_host.sh --system-deps --gpu
```

Conda:

```bash
bash scripts/setup_host_conda.sh --install-miniforge
```

Docker:

```bash
bash scripts/setup_prod.sh
```

## Verify

```bash
bash scripts/verify_setup.sh
```

## Canonical Workflow

```bash
methyl-centroid --project project.json --group all
methyl-detector --project project.json
methyl-mapper --project project.json
methyl-enricher --project project.json
methyl-classifier --project project.json
methyl-predictor --project project.json
```

Validation:

```bash
methyl-validation --config monte_carlo.json
```

## Tests

```bash
pytest packages/
```

## Main Docs

- `README.md`
- `docs/OPERATIONS_MANUAL.md`
- `docs/UNIFIED_PROJECT_CONFIG_GUIDE.md`
- `docs/THEORY_AND_PACKAGES.md`
