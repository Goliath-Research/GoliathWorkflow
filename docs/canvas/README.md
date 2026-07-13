# Cursor Canvases (versioned)

Interactive architecture and documentation hubs built with [Cursor Canvas](https://cursor.com) (`cursor/canvas` React components). **This directory is the git source of truth.**

| Canvas | Purpose |
|--------|---------|
| [methylpipeline-docs.canvas.tsx](methylpipeline-docs.canvas.tsx) | Documentation pillar navigation |
| [methylpipeline-platform-overview.canvas.tsx](methylpipeline-platform-overview.canvas.tsx) | Quick platform + SaMD overview companion |
| [methylpipeline-architecture.canvas.tsx](methylpipeline-architecture.canvas.tsx) | Config layers, local vs gateway, DB contract |
| [methylpipeline-db-runbook.canvas.tsx](methylpipeline-db-runbook.canvas.tsx) | Operator DB / workflow runbook |
| [analyte-comparison.canvas.tsx](analyte-comparison.canvas.tsx) | Analyte comparison explorer |
| [h-pca-good-mc-analysis.canvas.tsx](h-pca-good-mc-analysis.canvas.tsx) | H PCa good MC analysis |
| [pca-detection-fitness.canvas.tsx](pca-detection-fitness.canvas.tsx) | PCa Detection doc × MethylPipeline fitness |

## Open in Cursor

1. Click any `.canvas.tsx` link in the docs (for example [architecture index](../architecture/index.md)).
2. Or run from the repo root:

```bash
bash scripts/sync_cursor_canvases.sh
```

Then open the canvas from Cursor’s canvas picker or by clicking the synced file under your workspace’s `.cursor/projects/.../canvases/` folder.

## Sync to the IDE-managed folder

Cursor only auto-discovers canvases under:

`~/.cursor/projects/<workspace-slug>/canvases/`

That path is **local and not in git**. After clone or when canvases change on `main`, sync:

```bash
bash scripts/sync_cursor_canvases.sh
```

Override the destination when needed:

```bash
CURSOR_CANVASES_DIR="$HOME/.cursor/projects/my-workspace/canvases" \
  bash scripts/sync_cursor_canvases.sh
```

## Edit workflow

1. Edit the `.canvas.tsx` (and optional `.canvas.data.json` sidecar) **here** in `docs/canvas/`.
2. Commit to git.
3. Run `scripts/sync_cursor_canvases.sh` locally so the IDE-managed copy stays in sync.
4. Open the canvas beside chat in Cursor to preview.

Sidecar `*.canvas.data.json` files hold persisted canvas UI state (filters, expansion); commit them when they carry meaningful defaults for the team.

## Typecheck (optional)

`tsconfig.json` is for editor diagnostics only. Canvases import from `cursor/canvas`, which is provided by the IDE at runtime — not an npm package in this repo.
