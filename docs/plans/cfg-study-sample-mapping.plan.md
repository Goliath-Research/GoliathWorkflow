---
name: cfg study sample mapping
overview: Make study group membership a first-class `cfg` concern that references `portal.Samples` (import registry from institutions/labs), then materialize the existing CSV lists under `/work` so workers keep their current contract.
azure_devops:
  type: Feature
  title: "cfg study membership from portal.Samples"
  work_item_id: 570
  epic_id: 413
todos:
  - id: ddl-study-groups
    content: Add cfg.study_group + cfg.study_group_member (MSSQL/PG) with FKs to cfg.study, portal.Samples, portal.LabSamples
    status: completed
    work_item_id: 571
  - id: procs-materialize
    content: "Repo procs + methyl-cfg materialize: write CSVs and sync study document_json sample_paths"
    status: completed
    work_item_id: 572
  - id: cli-portal-api
    content: CLI/store + portal API to enroll/remove members from portal.Samples/LabSamples
    status: completed
    work_item_id: 573
  - id: docs-user-manual
    content: Fix How to define samples.md + config-registry.md for portal→cfg→CSV flow
    status: completed
    work_item_id: 574
---

> **Status: Implemented**

# cfg study membership from portal.Samples

## Problem

[`docs/user-manual/How to define samples.md`](../user-manual/How to define samples.md) correctly says the **study** owns which samples are in which analysis group, but incorrectly treated CSVs as the source of truth and dismissed `portal.Samples`.

Reality:

| Layer | What it is |
|-------|------------|
| **`portal.Samples`** | Clinical/import registry (institutions → patients → samples) |
| **`portal.LabSamples`** | Lab run row; `Sample varchar(128)` is the filesystem/processing ID (`BC-H-001`) |
| **`portal.Groups` / `GroupSamples`** | Portal **customer UI** cohorts — **not** study `controls`/`diseases` arms |
| **Study CSV lists** | Worker-facing materialization only |

## Design

**`cfg` owns analysis membership; `portal` owns sample identity; `/work` CSVs are derived.**

Tables: `cfg.study_group`, `cfg.study_group_member` (MSSQL FKs to portal; PG soft refs).

CLI: `methyl-cfg set-study-group`, `set-study-group-members`, `materialize-study-lists` / `materialize`.

Portal: `portal.sp_set_study_group`, `sp_set_study_group_members`, `sp_list_samples_for_study_enrollment`.
