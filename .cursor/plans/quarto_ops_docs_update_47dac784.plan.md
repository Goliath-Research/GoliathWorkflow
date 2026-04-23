---
name: Quarto ops docs update
overview: Add distributed MethylValidation queue execution (shared `/work` storage) and optional pipeline hyperparameter search to the theory book (as new sections in the existing model/validation chapter) and the user manual (two new Part III chapters plus index/cross-links), drawing from the canonical package docs without duplicating them in full.
todos: []
isProject: false
---

# Add distributed queue and hyperparameter search to Quarto manuals

## Source of truth (do not replace)

Implementation and CLI details live in the package and should be **summarized** in the books with **pointers** to:

- [packages/methylvalidation/docs/DISTRIBUTED_QUEUE.md](packages/methylvalidation/docs/DISTRIBUTED_QUEUE.md) — `plan-runs` → `export-queue` → `run-task` → `aggregate-results`, `queue/` layout, `/work` pattern
- [packages/methylvalidation/docs/HYPERPARAMETER_SEARCH.md](packages/methylvalidation/docs/HYPERPARAMETER_SEARCH.md) — objective \(J(\theta)\), `objective_from_monte_carlo_artifacts`, `methyl-hyperparam-search`, constraints via rollout, dry-run

## Theory book ([docs/theory/](docs/theory/))

**Rationale:** Avoid adding a new top-level chapter (would disturb cross-references across an already long book). The right home is the existing validation lifecycle chapter.

**Edits to** [docs/theory/chapters/15-model-creation-and-validation.qmd](docs/theory/chapters/15-model-creation-and-validation.qmd):

- After the final tuning list (or after **Outputs to Review**), add two new level-2 sections:
  1. **Distributed Monte Carlo on shared storage** — One paragraph: why (wall time at fixed iteration count), requirement (all workers R/W the same `output_base` tree, e.g. NFS at `/work/...`), **four-phase** mental model (plan → optional export → per-run workers → aggregate + optional `--stability`), note that the monolithic `methyl-validation` loop remains valid. Point to `DISTRIBUTED_QUEUE.md` for path table and exact commands.
  2. **Optional pipeline hyperparameter search** — Short description: outer loop over candidate `MonteCarloConfig` (or project) settings; scalar \(J\) from `metrics_summary.json` (+ optional stability); rollout-style **constraints** vs **primary** score; `methyl-hyperparam-search` as a small **grid** driver; why sklearn CV is not used; two-stage search caveat (discovery vs calibration); progression multi-stage as future (per `HYPERPARAMETER_SEARCH.md`). Link to that file for formulas and flags.

**Optional one-line cross-link** in [docs/theory/chapters/12-two-workflows.qmd](docs/theory/chapters/12-two-workflows.qmd) under **Stage A — Stability**: when many iterations are needed, execution can be **sharded** across machines on shared storage; see § in ch. 15 (use a concrete `@sec-...` anchor on the new section you add in ch. 15).

**Anchor:** Add explicit `{#sec-...}` labels on the two new sections in ch. 15 for crossrefs from ch. 12 and the user manual.

## User manual ([docs/user-manual/](docs/user-manual/))

**New chapters in Part III (Operations and Reliability),** after the command cookbook:

1. **`12-distributed-methyl-validation.qmd`** (working title: _Distributed MethylValidation on shared storage_)

   - Purpose: run discovery MC with **queue** subcommands when one host is too slow
   - Prerequisites: shared `output_base` visible to all workers, same venv/CLIs
   - Condensed table or bullet list: `queue/mc_config.json`, `plan_runs.json`, `tasks/`, `aggregate-results`, `queue_task_status.json` (one line each)
   - **Command sequence** (copy-pastable) mirroring the package doc: `plan-runs` → `export-queue` (optional) → `run-task` (repeat) → `aggregate-results` (with note about `--stability` parity)
   - `/work` example path consistent with other chapters (e.g. `project_Healthy_vs_PCa1-4-CG.json`)
   - Recovery: re-run failed task, partial aggregate
   - **See also:** `DISTRIBUTED_QUEUE.md`, and pointer to new theory § in ch. 15 (if a stable anchor exists)

2. **`13-optional-hyperparameter-search.qmd`** (working title: _Optional hyperparameter search_)

   - When: tuning Tier A (and later B/C) knobs after baseline workflow is understood
   - What: `methyl-hyperparam-search` writes isolated `work-dir/trial_*/` configs; `search_summary.json`
   - **Minimal** formula line + pointer to `HYPERPARAMETER_SEARCH` for full \(J\) and weights
   - Example `bash` line matching the package doc (grid JSON, `--stability` passthrough, `/work` work dir)
   - `--dry-run`, optional `--baseline-summary` for constraints
   - Pitfalls: discovery vs calibration, `n_iterations` as budget
   - **See also:** `HYPERPARAMETER_SEARCH.md`, `rollout` / ROLLOUT (for promotion thinking), theory ch. 15

**Edits to** [docs/user-manual/_quarto.yml](docs/user-manual/_quarto.yml):

- Under **Part III**, append the two new `.qmd` files in order (after `11-command-cookbook.qmd`).

**Edits to** [docs/user-manual/index.qmd](docs/user-manual/index.qmd):

- **Reading paths:** e.g. add a bullet for “Scaling MC across machines / optional tuning” → chapters 12–13
- **Canonical references:** add `DISTRIBUTED_QUEUE.md` and `HYPERPARAMETER_SEARCH.md` next to `USAGE.md`

**Light cross-links (optional but recommended):**

- [docs/user-manual/04-stage-stability.qmd](docs/user-manual/04-stage-stability.qmd): in **See also**, add a line: if iterations are sharded across hosts, use ch. 12
- [docs/user-manual/11-command-cookbook.qmd](docs/user-manual/11-command-cookbook.qmd): add a small subsection or two one-liner blocks for `plan-runs` and `methyl-hyperparam-search` pointing to ch. 12–13 (avoids duplicating long blocks)

## Verification

- `quarto render` for `docs/user-manual` and `docs/theory` (PDF and/or HTML) to catch broken internal links and LaTeX issues; fix any unescaped special characters in new markdown.

## Out of scope

- Editing the attached plan file in `.cursor/plans/`
- Duplicating the full path tables or Python API in the Quarto books (keep that in the package docs)
