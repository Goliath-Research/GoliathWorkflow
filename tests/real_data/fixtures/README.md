# Committed real-format H5 fixture

This directory holds a **small, real-format** extracted methylation fixture used
by `@pytest.mark.real_data` tests so they can run on hosted CI (which does not
mount `/work`).

## What belongs here

- One (or a few) `{chr}-{ctx}.h5` files produced by the **real MethylExtractor**
  (Blosc-compressed, real trinucleotide `tnc` encoding), restricted to a small
  region or a single small chromosome so the file stays commit-safe (a few MB).
- The matching `{sampleId}.extraction_manifest.json` when available.

## Rules

- **Non-PHI only.** Use a public/consented source (e.g. a public WGBS cell line
  or a small model-organism sample). Do not commit data derived from
  identifiable human FASTQ without a documented consent basis.
- Record provenance (source, consent, MethylExtractor release, region) in the
  registry entry `provenance` field and in the validation evidence index.
- Keep it small. This is a format/regression fixture, not a cohort.

## Wiring

The committed fixture is referenced by
[`../registry.json`](../registry.json) via `committed_fixture_dir`. Point a
reference sample's `sample_dir` at this directory (relative to the repo root) to
have hosted-CI real-data tests use it. Heavier cohort tests use `/work` samples
declared in the site manifest `testing` block or `METHYL_TEST_DATA_CONFIG`.

See [`../../docs/reference/test-data-registry.md`](../../docs/reference/test-data-registry.md).
