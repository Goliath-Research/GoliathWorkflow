---
name: ADO Boards Traceability
overview: Create Epic MethylPipeline platform (AB#413) under EpiMethyl/Development, seed Features from docs/plans rows and User Stories from plan todos, backfill AB# into plan frontmatter, leave legacy Epic #283 historical.
> **Status: COMPLETED** — 2026-07-13. Epic AB#413; 33 Features; 243 User Stories; plan IDs backfilled.

azure_devops:
  type: Feature
  title: "ADO Boards Traceability"
  work_item_id: null
  epic_id: 413
todos:
  - id: manifest
    content: Build platform_backlog.yaml from docs/plans README + frontmatter todos/status
    status: completed
  - id: seed-script
    content: Implement idempotent seed_platform_boards.py (dry-run / --apply, seed_state.json)
    status: completed
  - id: ado-create
    content: Create Epic MethylPipeline platform + Features + User Stories; Close completed; Related link to #283
    status: completed
  - id: backfill-docs
    content: Backfill azure_devops work_item_ids in plans; update docs/plans/README.md + plan-mode rule wording
    status: completed
  - id: promote-plan
    content: Promote approved plan to docs/plans/ado-boards-traceability.plan.md and README row
    status: completed
---

# MethylPipeline platform ADO traceability

## Result

| Item | Value |
|------|--------|
| Epic | [AB#413 MethylPipeline platform](https://dev.azure.com/EpiMethyl/Development/_workitems/edit/413) |
| Features | 33 (from `docs/plans`) |
| User Stories | 243 (from plan `todos`) |
| Historical | Epic [#283](https://dev.azure.com/EpiMethyl/Development/_workitems/edit/283) Related (unchanged) |
| Seed state | [`scripts/ado_traceability/seed_state.json`](../../scripts/ado_traceability/seed_state.json) |

## Tooling

```bash
source .venv/bin/activate
python scripts/ado_traceability/generate_manifest.py
python scripts/ado_traceability/seed_platform_boards.py          # dry-run
python scripts/ado_traceability/seed_platform_boards.py --apply  # idempotent
python scripts/ado_traceability/backfill_plan_ids.py
```

## Hierarchy

Epic **AB#413** → Feature (one plan) → User Story (one todo). Implemented Features/Stories are **Closed**. Open Features remain for incomplete plans (e.g. chromosome derived measures, DI assessment).
