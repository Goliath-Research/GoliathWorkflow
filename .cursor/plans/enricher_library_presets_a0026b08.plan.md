---
name: Enricher Library Presets
overview: Add Enrichr cancer-focused library presets and support selecting them via CLI (`--library-preset`) and project config (`step_config.enricher.library_preset`) with clear precedence and docs updates.
todos:
  - id: add-presets
    content: Add LIBRARY_PRESETS and resolver in enricher core with precedence rules
    status: pending
  - id: wire-cli
    content: Add --library-preset and resolve effective libraries in CLI execution flow
    status: pending
  - id: extend-config
    content: Add EnricherStepConfig.library_preset and ensure project config propagation
    status: pending
  - id: update-docs
    content: Update theory/config docs and example config for cancer-extended preset
    status: pending
  - id: validate-behavior
    content: Validate help, preset behavior, precedence, and run sanity checks in .venv
    status: pending
isProject: false
---

# Add Enrichr Library Presets

## Goal
Introduce named Enrichr library presets (including `cancer-extended`) for MethylEnricher, make them selectable from both CLI and project config, and keep behavior backward-compatible for existing `libraries` users.

## Implementation
- Update library definitions and resolution logic in [`/home/ubuntu/MethylPipeline/packages/methylenricher/methyl_enricher/enricher.py`](/home/ubuntu/MethylPipeline/packages/methylenricher/methyl_enricher/enricher.py):
  - Keep `DEFAULT_LIBRARIES` as current fallback.
  - Add a preset map (e.g., `LIBRARY_PRESETS`) including:
    - `cancer-core`
    - `cancer-extended` (with the recommended cancer-relevant additions)
  - Add a small resolver helper that returns final libraries from `(libraries, library_preset)`.
  - Enforce precedence: explicit `libraries` > `library_preset` > `DEFAULT_LIBRARIES`.

- Add CLI support in [`/home/ubuntu/MethylPipeline/packages/methylenricher/methyl_enricher/cli.py`](/home/ubuntu/MethylPipeline/packages/methylenricher/methyl_enricher/cli.py):
  - Add `--library-preset` argument with choices from preset keys.
  - Ensure effective libraries are resolved once before calling enrichment/module pipeline.
  - Improve run logging to print preset name + resolved library list when preset is used.

- Add config property in [`/home/ubuntu/MethylPipeline/packages/methylenricher/methyl_enricher/config.py`](/home/ubuntu/MethylPipeline/packages/methylenricher/methyl_enricher/config.py):
  - Add optional `library_preset` to `EnricherStepConfig`.
  - Keep compatibility with existing `libraries` field.
  - Reuse existing config propagation path (`_apply_enricher_config_to_args`) so `step_config.enricher.library_preset` works with `--project`.

- Update docs and examples:
  - [`/home/ubuntu/MethylPipeline/docs/reference/configuration-reference.qmd`](/home/ubuntu/MethylPipeline/docs/reference/configuration-reference.qmd): document `library_preset`, precedence, and align the `libraries` default list with actual code.
  - [`/home/ubuntu/MethylPipeline/docs/theory/chapters/08-methylenricher.qmd`](/home/ubuntu/MethylPipeline/docs/theory/chapters/08-methylenricher.qmd): mention preset usage and reproducibility guidance.
  - [`/home/ubuntu/MethylPipeline/packages/methylenricher/configs/PCa_vs_Healthy_enricher_config.json`](/home/ubuntu/MethylPipeline/packages/methylenricher/configs/PCa_vs_Healthy_enricher_config.json): set `"library_preset": "cancer-extended"` (or keep explicit list plus comment-equivalent in docs if preserving strict reproducibility style).

## Validation
- Run CLI dry checks in `.venv`:
  - `methyl-enricher --help` shows `--library-preset`.
  - `methyl-enricher --list-libraries` still works.
- Run a short enrichment invocation (small input) with:
  - explicit `--libraries` only,
  - `--library-preset cancer-extended` only,
  - both together (confirm explicit list wins).
- Run lints/tests for touched files and verify no regression in project-driven `--project` flow.
