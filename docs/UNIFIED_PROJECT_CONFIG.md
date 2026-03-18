# Unified Project Config

This document is kept as a compatibility entry point.

Use [UNIFIED_PROJECT_CONFIG_GUIDE.md](UNIFIED_PROJECT_CONFIG_GUIDE.md) as the canonical guide for the current project schema and directory layout.

## Current Contract

Prefer:

- `controls`
- `diseases`
- `comparisons`
- `step_config`

Prefer the comparison-based downstream layout:

```text
detections/<control_group>/<disease_group>/
mapper/<control_group>/<disease_group>/
enricher/<control_group>/<disease_group>/
classifiers/<control_group>/<disease_group>/
predictors/<control_group>/<disease_group>/
```

Legacy `group1` / `group2`, flat `groups`, and older `.../cancer/<group>` references may still appear in code or historical docs for backward compatibility, but they are not the primary workflow for new projects.
