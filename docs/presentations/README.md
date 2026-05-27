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

## Source Basis

Slides are aligned with the updated documentation in:

- `docs/theory/chapters/`
- `docs/user-manual/`
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

Recommended rendering command (includes Mermaid chart enablement in HTML output):

```bash
./scripts/render_presentations.sh
```

This script embeds Mermaid JS directly into each generated HTML file, so charts render from local `file://` copies without CDN/network access.

```bash
marp "docs/presentations/methylpipeline-theory-implementation.md" --html
marp "docs/presentations/methylpipeline-workflows-model-prediction.md" --html
marp "docs/presentations/methylpipeline-theory-implementation-executive.md" --html
marp "docs/presentations/methylpipeline-workflows-model-prediction-executive.md" --html
```

### Option B: Quarto revealjs (quick wrapper)

Create a tiny wrapper `.qmd` that includes each deck body, then:

```bash
quarto render your-wrapper.qmd --to revealjs
```

## Usage Guidance

- Keep command examples synchronized with `packages/methylvalidation/docs/USAGE.md`.
- Keep configuration defaults synchronized with `docs/theory/chapters/13-configuration-reference.qmd`.
- If workflow semantics change, update both decks in the same PR.
