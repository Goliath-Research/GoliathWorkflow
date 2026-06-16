# Production study runbook

End-to-end operator checklist for real FASTQ → HDF5 → validation on `/work/epimethyl`.

## Prerequisites

- [ ] Shared storage mounted at `/work/epimethyl` on all worker nodes
- [ ] `bash scripts/verify_e2e_node.sh` passes on GPU workers
- [ ] Azure PostgreSQL schema deployed (`workflow_engine/sql_pg/deploy_azure.sh`)
- [ ] Action catalog seeded (`seed_action_catalog.py`)
- [ ] Workflow definitions deployed (`deploy_workflow_definitions.sh`)
- [ ] Workers registered and systemd units running
- [ ] Reference FASTA and project JSON on shared storage
- [ ] Portal or API client pointed at `WORKER_API_BASE`

## Stage 1 — SamplePrepPipeline

See [`workflow_engine/docs/portal_study_lifecycle.md`](../../workflow_engine/docs/portal_study_lifecycle.md).

```http
POST /v1/workflows/instances
{
  "workflow_version_id": <from workflow_versions.json SamplePrepPipeline>,
  "context_json": {
    "projectPath": "/work/epimethyl/data/project_....json",
    "primaryAnalyte": "buffy_coat",
    "isCfdna": false,
    "referenceFasta": "/work/epimethyl/data/reference.fa",
    "samples": [ ... ]
  }
}
```

Poll until **COMPLETED**. Do not start validation until all samples have per-chromosome HDF5s.

## Stage 2 — StudyValidationLifecycle

Recommended:

```http
POST /v1/studies/validation/start
{
  "projectPath": "/work/epimethyl/data/project_....json",
  "workflow_version_id": <from workflow_versions.json StudyValidationLifecycle>,
  "featureIterations": 30,
  "seed": 42
}
```

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Parabricks tasks fail | `verify_parabricks.sh`, NGC login, `nvidia-ctk` |
| Extract fails | `verify_methyl_extractor.sh`, `HDF5_PLUGIN_PATH` |
| Worker idle | `WORKER_CAPABILITY` filter vs task capability |
| FOREACH errors | `08_foreach_support.sql` applied on PostgreSQL |

Platform notes: [`platform_matrix.md`](platform_matrix.md).  
Worker env: [`worker_node.md`](worker_node.md).
