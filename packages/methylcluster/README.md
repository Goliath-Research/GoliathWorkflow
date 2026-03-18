# MethylCluster

MethylCluster is the optional clustering package used to split a project group into subclusters before centroid generation.

The active workflow is project-aware and writes clustering manifests that `methyl-centroid` can consume.

## Supported Usage

Project-driven run:

```bash
methyl-cluster --project /path/to/project.json --group healthy
```

Standalone config run:

```bash
methyl-cluster --config /path/to/cluster.json
```

## Current Behavior

- default method: `centroid`
- optional methods: `hdbscan`, `hierarchical`
- outputs include clustering assignments plus a manifest for downstream centroid resolution
- project outputs live under `clustering/controls/...` or `clustering/diseases/...`

## Notes

- This package is an optional side workflow, not part of the mandatory main pipeline chain.
- The older Dirichlet-process clustering module is retained only as a legacy internal surface and is not the supported CLI path.
- The shared project schema is documented in `docs/UNIFIED_PROJECT_CONFIG_GUIDE.md`.
