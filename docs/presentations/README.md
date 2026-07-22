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
  - Focus: commercial / regulatory product positioning (pillars, open-core packaging, GTM, roadmap).
  - Source narrative: `docs/regulatory/Regulatory-Ready Platform for Multiomics Diagnostics.md`.
  - Shareable outputs: self-contained `.html` (live talk) and `.pdf` (email attach).

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

This script uses Marp's `bare` template, then
[`scripts/embed_marp_mermaid.mjs`](../../scripts/embed_marp_mermaid.mjs) embeds a
Mermaid runtime so fenced Mermaid diagrams render in the HTML and in the printed PDF.
Outputs are offline/`file://` friendly.

```bash
./scripts/render_presentations.sh
# or one deck:
marp --template bare "docs/presentations/regulatory-ready-platform-multiomics.md" --html \
  -o "docs/presentations/regulatory-ready-platform-multiomics.html"
node scripts/embed_marp_mermaid.mjs \
  "docs/presentations/regulatory-ready-platform-multiomics.html" \
  --pdf "docs/presentations/regulatory-ready-platform-multiomics.pdf"
```

### Option B: Quarto revealjs (quick wrapper)

Create a tiny wrapper `.qmd` that includes each deck body, then:

```bash
quarto render your-wrapper.qmd --to revealjs
```

## Usage Guidance

- Keep command examples synchronized with `packages/methylvalidation/docs/USAGE.md`.
- Keep configuration defaults synchronized with `docs/reference/configuration-reference.qmd`.
- If workflow semantics change, update both decks in the same PR.
