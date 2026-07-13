---
name: MethylPipeline Platform Overview
overview: Create a concise, print-friendly Markdown overview for mixed technical, product, and SaMD-review audiences, plus a companion navigable Docs Canvas. The overview will present MethylPipeline as a general schema-driven workflow platform while clearly separating implemented capabilities, extension points, and evidence needed for SaMD fitness from regulatory approval claims.
> **Status: COMPLETED** — Markdown overview + companion Docs Canvas + docs registry updates.

azure_devops:
  type: Feature
  title: "MethylPipeline Platform Overview"
  work_item_id: null
  epic_id: 413
todos:
  - id: outline-source-map
    content: Create the Markdown overview structure, source map, audience framing, and few-dozen-page print budget
    status: completed
  - id: platform-capabilities
    content: Write concise capability, workflow-authoring, configuration, scientific-process, and runtime chapters with reusable Mermaid diagrams
    status: completed
  - id: samd-evidence
    content: Write SaMD fitness, traceability, evidence-boundary, limitations, and change-control chapters without regulatory overclaiming
    status: completed
  - id: extension-example
    content: Add a domain-neutral worked example showing how typed actions become configurable, testable, deployable workflows
    status: completed
  - id: docs-canvas
    content: Create the companion navigable Cursor Docs Canvas from the overview structure and verify its diagnostics
    status: completed
  - id: verify-promote
    content: Validate Markdown, diagrams, links, and print length; register the overview and promote the approved plan into docs/plans traceability
    status: completed
---

# MethylPipeline Platform Overview

## Deliverables

- Canonical Markdown overview: [`docs/overview/methylpipeline-platform-overview.md`](../overview/methylpipeline-platform-overview.md)
- Companion canvas: [`docs/canvas/methylpipeline-platform-overview.canvas.tsx`](../canvas/methylpipeline-platform-overview.canvas.tsx)
- Registered in [`docs/index.md`](../index.md) and [`docs/DOCUMENTATION_AUDIT.md`](../DOCUMENTATION_AUDIT.md)

## Content structure

1. Executive overview
2. Capability map
3. Workflow authoring model
4. Configuration and reproducibility
5. Scientific process pack
6. Runtime, operations, and security
7. SaMD fitness framework
8. Extension guide and worked example
9. Limitations, readiness, and references
