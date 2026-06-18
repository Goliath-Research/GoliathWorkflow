# Implementation plans (Azure DevOps traceability)

Plans in this folder are the **source of truth** for large features. Each plan maps to Azure DevOps work items.

## Work item mapping

| Plan file | ADO type | Suggested title | Child tasks (from plan frontmatter) |
|-----------|----------|-----------------|-------------------------------------|
| [`production-gpu-worker-layout.plan.md`](production-gpu-worker-layout.plan.md) | **Epic** | Production GPU worker layout | `define-layout`, `extractor-ci`, `pipeline-ci`, `install-release`, `gpu-node-runbook`, `docker-shared`, `worker-provision` |
| [`devops-ci-cd-release.plan.md`](devops-ci-cd-release.plan.md) | **Epic** | DevOps CI/CD release pipeline | `me-release-ci`, `mp-release-ci`, `assemble-script`, `assemble-pipeline`, `deploy-pipeline`, `docs-ci-cd` |

Create each **Task** under its Epic in Azure DevOps Boards. Copy the task title from the plan `todos[].content` field. Mark tasks **Closed** when the corresponding code is merged.

Smaller fixes (single script, doc tweak) can be a **Task** without a plan file.

## Commit message convention

Link commits to work items so Azure DevOps auto-updates state:

```
<imperative summary> (AB#<work-item-id>)

Optional body: what changed and why.
```

Examples:

```
Add assemble_release.sh and release assemble pipeline (AB#1234)

Implements devops-ci-cd-release plan task assemble-script.
Part of Epic AB#1200 (DevOps CI/CD release).
```

```
Document production release layout on /work/epimethyl (AB#1101)

Implements production-gpu-worker-layout plan task define-layout.
```

### Multiple work items

```
Refactor CI YAML per repo (AB#1234 AB#1235)
```

Or reference the Epic only when the commit completes several tasks:

```
Complete GPU worker production layout (AB#1100)
```

## Branch and PR workflow

1. Create **Task** or **Epic** in Azure DevOps (or use existing).
2. Branch: `feature/AB1234-assemble-release` or `task/1101-release-docs`.
3. Implement; reference plan file in PR description.
4. PR title: `Add assemble release pipeline (AB#1234)`.
5. Enable **Automatically link work items** in Azure DevOps repo settings (Boards → Project settings → Git → Mention tracking).
6. Close Task when PR completes; close Epic when all child tasks are done.

## Plan file format

Plans use YAML frontmatter (`name`, `overview`, `todos`) plus markdown body. The `todos` list mirrors Azure DevOps Tasks. Update `status: completed` in the plan when merging if you use plans as living records.

## Related docs

- [`../deployment/production_release.md`](../deployment/production_release.md) — operational release guide
- [`../../ci/README.md`](../../ci/README.md) — pipeline registration
