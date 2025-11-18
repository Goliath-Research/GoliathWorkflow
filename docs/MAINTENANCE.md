# Maintenance Notes

_Last updated: 2025-11-14_

## Documentation Realignment
- README, PROJECT_OVERVIEW, docs/index, docs/DEVELOPMENT, and docs/ARCHITECTURE now reference the current package lineup (MethylUtils, MethylCentroid, MethylCluster, MethylModeler, MethylClassifier, MethylMapper, Methylenricher).
- Quick-reference guides (`QUICK_REFERENCE*.md`) now point to the `methyl_modeler` CLI and updated wrapper scripts.
- Docker configs, install scripts, and verification tooling now install/validate `methylcluster` instead of the removed `methyltrainer` package.
- Package READMEs were refreshed where needed (e.g., MethylUtils integration matrix, MethylClassifier training workflow) to eliminate stale references.

## Suspected Orphan / Legacy Assets

### Build Artifacts & Caches
- `packages/methylmapper/{build,dist,methyl_mapper.egg-info}/`
- `packages/methylutils/methyl_utils/build/`
- Numerous `__pycache__/` folders across all packages (see `find packages -type d -name '__pycache__'` output). These should be removed or git-ignored before release packaging.

### Legacy HTML Reports
- `packages/methylutils/Analysis.html`, `packages/methylutils/MethylUtils.html`, and related narrative reports reference retired packages (`MethylDetector`, `MethylTrainer`). Convert to Markdown or delete after extracting the relevant guidance.
- `packages/methylmodeler/docs/MethylDetector*.{html,pdf,docx}`: keep for historical context, but add a note (or rename) so users do not expect a separate `MethylDetector` package.

### Ad-hoc Test Scripts
- Root-level helpers (`test_cli_args.py`, `test_enrichment.py`, `test_progress.py`) are not wired into pytest and still hard-code local paths. Either migrate them under `packages/methylmapper/tests/` with fixtures or remove them to avoid confusion during CI.

### Environment Clean-up
- Remove leftover `pyodbc`/`pymssql` config references if Azure SQL workflow is deprecated in favour of the Bedtools mapper.
- Double-check that no remaining docs mention `./packages/methylmodeler/md`; the wrapper script has been renamed to `./packages/methylmodeler/modeler`.

## Next Steps
- Delete the artifacts above (or add them to `.gitignore`) before cutting a release tag.
- Audit large comprehensive docs (`packages/*/docs/*.md`) for residual `MethylDetector` terminology so that external docs match the current package names.
- Consider generating a consolidated changelog entry outlining the rename from MethylDetector → MethylModeler for future contributors.

