# Schema Index

Machine-readable contracts and generated schemas.

| Area | Location |
|------|----------|
| Project / step config | `schemas/config/*.schema.json` |
| DomainProgram | `schemas/domain/domain_program.schema.json` |
| Workflow deploy spec | `schemas/workflow/` |
| Worker task payloads | exported via `methyl-export-task-schemas` → `wf.workflow_action_schema` |
| REST API | [`contracts/openapi.yaml`](../../contracts/openapi.yaml) |

Regenerate after model changes:

```bash
source .venv/bin/activate
methyl-export-task-schemas
methyl-export-action-catalog
```

Parameter semantics vs key locations: [config-parameter-matrix.md](config-parameter-matrix.md).
