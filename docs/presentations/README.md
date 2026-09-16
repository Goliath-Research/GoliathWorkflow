# MethylPipeline Presentations

This folder contains two Markdown slide decks for a mixed scientific and technical audience.

## Decks

- `methylpipeline-theory-implementation.md`
  - Focus: theoretical rationale and implementation across core packages.
- `methylpipeline-workflows-model-prediction.md`
  - Focus: practical workflows for model creation, selection, and prediction.
- `methylpipeline-theory-implementation-executive.md`
  - Focus: executive summary of theory + implementation (8-10 slides).
- `methylpipeline-workflows-model-prediction-executive.md`
  - Focus: executive summary of workflows + governance checkpoints (8-10 slides).
- `regulatory-ready-platform-multiomics.md`
  - Focus: **sales** briefing — colorful interactive Marp theme (`themes/goliath-sales.css`), DomainProgram / distributed-worker diagrams, packs roadmap, open-core GTM.
  - Source narrative: `docs/regulatory/Regulatory-Ready Platform for Multiomics Diagnostics.md`.
  - Shareable outputs: self-contained `.html` (bespoke: keyboard, OSC, progress, `P` presenter) and `.pdf` (email attach).

## Source Basis

Slides are aligned with the updated documentation in:

- `docs/theory/chapters/`
- `docs/usage/`
- `packages/methylvalidation/docs/`
- selected package `docs/IMPLEMENTATION.md` and `docs/THEORY.md`

## Rendering Notes

The decks use standard Markdown slide separators (`---`) and can be rendered by common slide engines.

### Option A: Marp

`scripts/install_all.sh` now installs Marp CLI by default (use `--skip-marp` to opt out).
If `marp` is still not found, add npm global bin to `PATH`:

```bash
export PATH="$(npm config get prefix)/bin:$PATH"
```

Recommended rendering command:

```bash
./scripts/render_presentations.sh
```

Decks with `marp: true` (sales) render with the **bespoke** template + optional
theme CSS under `themes/`. Other decks keep **bare** for maximal `file://`
compatibility. [`scripts/embed_marp_mermaid.mjs`](../../scripts/embed_marp_mermaid.mjs)
embeds a Mermaid runtime (teal sales palette) so diagrams render in HTML and PDF.

**Interactive diagrams:** put `%% mp:interactive` on the first line of a Mermaid
fence (or any diagram that overflows the slide) to get pan / zoom / Fit / Expand
controls in the HTML deck. Wheel-zoom and drag do not advance slides. PDF keeps a
fitted static snapshot.

```bash
./scripts/render_presentations.sh
# or one sales deck:
marp --template bespoke --theme-set docs/presentations/themes/goliath-sales.css \
  --bespoke.progress true --html \
  "docs/presentations/regulatory-ready-platform-multiomics.md" \
  -o "docs/presentations/regulatory-ready-platform-multiomics.html"
node scripts/embed_marp_mermaid.mjs \
  "docs/presentations/regulatory-ready-platform-multiomics.html" \
  --pdf "docs/presentations/regulatory-ready-platform-multiomics.pdf"
```

## Usage Guidance

- Keep command examples synchronized with `packages/methylvalidation/docs/USAGE.md`.
- Keep configuration defaults synchronized with `docs/reference/configuration-reference.md`.
- If workflow semantics change, update both decks in the same PR.
