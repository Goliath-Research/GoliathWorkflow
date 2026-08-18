# Cursor Canvases (versioned)

Interactive architecture and documentation hubs built with [Cursor Canvas](https://cursor.com) (`cursor/canvas` React components). **This directory is the git source of truth.**

`.canvas.tsx` files are **not** part of the MkDocs HTML/PDF site (the browser cannot run Cursor canvases). Use this page as the index; open canvases in the Cursor IDE after syncing.

| Canvas | Purpose |
|--------|---------|
| [Docs hub](#methylpipeline-docs) | Documentation pillar navigation |
| [Platform overview](#methylpipeline-platform-overview) | Quick platform + SaMD overview companion |
| [Architecture](#methylpipeline-architecture) | Config layers, local vs gateway, DB contract |
| [Portal IA](#portal-ia) | Study pipeline, monitor/retry, Admin RBAC + contract packs |
| [DB runbook](#methylpipeline-db-runbook) | Operator DB / workflow runbook |
| [Analyte comparison](#analyte-comparison) | Analyte comparison explorer |
| [H PCa good MC](#h-pca-good-mc-analysis) | H PCa good MC analysis |
| [PCa detection fitness](#pca-detection-fitness) | PCa Detection doc × MethylPipeline fitness |
| [Buffy M-value residualization](#buffy-mvalue-residualization) | Confounder-aware DMP calling (opt-in procedure) |

## Open in Cursor

Canvases only auto-discover under the IDE-managed folder (not under `docs/canvas/`):

`~/.cursor/projects/<workspace-slug>/canvases/`

From the repo root after clone or when canvases change on `main`:

```bash
bash scripts/sync_cursor_canvases.sh
```

Then open the synced `.canvas.tsx` from Cursor’s canvas picker (or from that `canvases/` folder).

Override the destination when needed:

```bash
CURSOR_CANVASES_DIR="$HOME/.cursor/projects/my-workspace/canvases" \
  bash scripts/sync_cursor_canvases.sh
```

## Catalog

### Docs hub {#methylpipeline-docs}

- **Source:** `docs/canvas/methylpipeline-docs.canvas.tsx`
- **Purpose:** Documentation pillar navigation

### Platform overview {#methylpipeline-platform-overview}

- **Source:** `docs/canvas/methylpipeline-platform-overview.canvas.tsx`
- **Purpose:** Quick platform + SaMD overview companion
- **Markdown companion:** [Platform overview](../overview/methylpipeline-platform-overview.md)

### Architecture {#methylpipeline-architecture}

- **Source:** `docs/canvas/methylpipeline-architecture.canvas.tsx`
- **Purpose:** Config layers, local vs gateway, DB contract
- **Markdown companion:** [Architecture index](../architecture/index.md)

### Portal IA {#portal-ia}

- **Source:** `docs/canvas/portal-ia.canvas.tsx`
- **Purpose:** EpiPortal study pipeline workspace, instance monitor + retry, Admin RBAC and contract process packs (SQL contract spec for the other repo)
- **Markdown companion:** [Portal information architecture](../architecture/portal-ia.md)

### DB runbook {#methylpipeline-db-runbook}

- **Source:** `docs/canvas/methylpipeline-db-runbook.canvas.tsx`
- **Purpose:** Operator DB / workflow runbook
- **Markdown companion:** [Operator journey](../deployment/operator-journey.md)

### Analyte comparison {#analyte-comparison}

- **Source:** `docs/canvas/analyte-comparison.canvas.tsx`
- **Purpose:** Buffy vs plasma MC comparison explorer

### H PCa good MC analysis {#h-pca-good-mc-analysis}

- **Source:** `docs/canvas/h-pca-good-mc-analysis.canvas.tsx`
- **Purpose:** H PCa good MC analysis

### PCa detection fitness {#pca-detection-fitness}

- **Source:** `docs/canvas/pca-detection-fitness.canvas.tsx`
- **Purpose:** PCa Detection doc × MethylPipeline fitness

### Buffy M-value residualization {#buffy-mvalue-residualization}

- **Source:** `docs/canvas/buffy-mvalue-residualization.canvas.tsx`
- **Purpose:** Leakage rules, M-value formulas, isolation contract, and Ω-as-confounder caveat for the opt-in buffy residual procedure
- **Markdown companion:** [Buffy M-value residualization](../research/buffy-mvalue-residualization.md)

## Edit workflow

1. Edit the `.canvas.tsx` (and optional `.canvas.data.json` sidecar) **here** in `docs/canvas/`.
2. Commit to git.
3. Run `scripts/sync_cursor_canvases.sh` locally so the IDE-managed copy stays in sync.
4. Open the canvas beside chat in Cursor to preview.

Sidecar `*.canvas.data.json` files hold persisted canvas UI state (filters, expansion); commit them when they carry meaningful defaults for the team.

## Typecheck (optional)

`tsconfig.json` is for editor diagnostics only. Canvases import from `cursor/canvas`, which is provided by the IDE at runtime — not an npm package in this repo.
