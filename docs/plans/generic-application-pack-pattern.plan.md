---
name: Generic application pack pattern
overview: "Refactor docs and naming so the reusable methylation pattern is an application pack (config overlay on an existing process), with Alzheimer cfDNA and plant abiotic stress as named instances—not Alzheimer-as-template. No DomainProgram renames; keep disease/trait directory names for the instances."
azure_devops:
  type: Feature
  title: "Generic methylation application-pack pattern"
  work_item_id: null
  epic_id: 413
todos:
  - id: app-pack-guide
    content: Add docs/usage/24-methylation-application-packs.qmd (process vs application + checklist + overlay knobs)
    status: completed
    work_item_id: null
  - id: reframe-instances
    content: Reframe Alzheimer ch.21, plant ch.23, and both example READMEs as application-pack instances
    status: completed
    work_item_id: null
  - id: hub-docs
    content: Update ANALYTE_PROFILES, SaMD examples README, ch.18, regulatory overview, platform overview taxonomy
    status: completed
    work_item_id: null
  - id: promote-plan
    content: Promote plan to docs/plans/generic-application-pack-pattern.plan.md + README row under AB#413
    status: completed
    work_item_id: null
---

# Generic methylation application-pack pattern

> **Status: Implemented** (2026-07). Docs and taxonomy now use **application pack** as the umbrella for config overlays on an existing process. Alzheimer cfDNA and plant abiotic stress remain named instances; directories and CI fixtures were not renamed.

## Naming

| Term | Meaning |
|------|---------|
| **Process pack** | New omics modality (actions / programs / QC) |
| **Application pack** | Config + cohorts + partitions + overlay on an existing process |
| Instance paths | Keep `alzheimer-cfdna/`, `plant-abiotic-stress/` |

## Implemented

- [`docs/usage/24-methylation-application-packs.qmd`](../usage/24-methylation-application-packs.md) — process vs application, artifacts, overlay knobs, checklist, pointers to instances
- Alzheimer ch.21 and plant ch.23 reframed as disease / trait application instances; example READMEs link to ch.24
- Hub updates: ANALYTE_PROFILES, SaMD examples README, usage index + ch.18, regulatory overview, platform overview
- Light terminology notes on historical Alzheimer / plant plan Framing sections

## Explicitly out of scope

- Renaming Alzheimer/plant directories, CI fixtures, or test modules
- New DomainPrograms / actions
- Changing enrichment preset names
