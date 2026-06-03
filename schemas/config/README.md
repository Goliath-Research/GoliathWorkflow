# Pipeline config JSON Schemas

Committed JSON Schema artifacts generated from Pydantic config models (source of truth).

Note: `validation.schema.json` and `progression.schema.json` are editor-facing step aliases used for
`project_config.step_config` key resolution.

## Regenerate

From the repository root with `.venv` activated:

```bash
methyl-export-config-schemas
# or
./scripts/export_config_schemas.sh
```

## Drift check (CI / pre-commit)

Fails when models changed but schemas were not regenerated:

```bash
methyl-export-config-schemas --check
```

Pytest also enforces this: `packages/methylvalidation/tests/test_config_schema_export.py`.

## Layout

| File | Pydantic model |
|------|----------------|
| `project_config.schema.json` | `methyl_utils.pipeline_config.ProjectConfig` |
| `validation_monte_carlo.schema.json` | `methyl_validation.config.MonteCarloConfig` |
| `validation.schema.json` | Editor alias for `step_config.validation` (validation step root) |
| `validation_regulatory.schema.json` | `RegulatoryLifecycleConfig` |
| `validation_feature_selection.schema.json` | `FeatureSelectionConfig` |
| `validation_partitions.schema.json` | `ValidationPartitionContract` |
| `validation_backend_profiles.schema.json` | `BackendProfilesConfig` |
| `detection.schema.json` | `MethylDetectorConfig` |
| `mapper.schema.json` | `MapperStepConfig` |
| `enricher.schema.json` | `EnricherStepConfig` |
| `classifier.schema.json` | `ClassificationConfig` |
| `predictor.schema.json` | `PredictorConfig` |
| `alignment_qc.schema.json` | `AlignmentQCConfig` |
| `centroid.schema.json` | `MethylCentroidConfig` |
| `progression.schema.json` | Schema for `step_config.progression` (methyl-disease-progression) |
| `queue_discovery_task_v1.schema.json` | `DiscoveryRunTaskV1` |
| `alignment_qc/exported_sample_qc*.schema.json` | AlignmentQC export payloads |

Registry: `packages/methylvalidation/methyl_validation/config_schema_registry.py`.
