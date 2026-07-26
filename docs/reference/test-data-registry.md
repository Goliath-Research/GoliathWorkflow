# Test data registry (real reference samples)

MethylPipeline supports testing against **real** extracted methylation data, not
only synthetic fixtures. The *test data registry* is a small, typed configuration
that identifies:

- one **reference sample per analyte** (e.g. `cfdna`, `buffy_coat`) - a directory
  of real `{chr}-{ctx}.h5` files produced by MethylExtractor, and
- named **groups of samples** (e.g. `healthy`, `PCa`) for cohort-level tests.

Tests marked `@pytest.mark.real_data` use these samples and **skip cleanly** when
the data is not mounted, so the suite stays green on hosted CI (which has no
`/work`) while real-data verification runs where the samples exist.

Model: [`TestDataRegistry`](../../packages/methylutils/methyl_utils/test_data_registry.py).
Schema: [`schemas/config/test_data_registry.schema.json`](../../schemas/config/test_data_registry.schema.json).
Helpers: [`methyl_utils.testing.real_data`](../../packages/methylutils/methyl_utils/testing/real_data.py).

## Why real data (and why tiered)

Synthetic fixtures diverge from production H5 in ways that hide bugs: real files
are Blosc-compressed (`hdf5plugin`), encode full trinucleotide `tnc`, are far
larger, and carry realistic coverage/sparsity. Real data materially exercises the
loader, centroid building, detector ECDF, derived measures, info-theory, and
clustering. See the rationale in
[`../regulatory/continuous-integration-and-regression-testing.md`](../regulatory/continuous-integration-and-regression-testing.md).

Two tiers:

| Tier | Data location | Runs on | Purpose |
|------|---------------|---------|---------|
| Committed fixture | `tests/real_data/fixtures/` (small, real-format, non-PHI) | hosted PR CI + local | fast format/regression checks |
| Designated `/work` samples | `/work/samples/...` declared in site manifest / registry | self-hosted `production-work-agents` | full-scale, cohort-level checks |

## Configuration shape

```json
{
  "committed_fixture_dir": "tests/real_data/fixtures",
  "samples": {
    "cfdna":      { "sample_id": "REF_CFDNA_01", "sample_dir": "/work/samples/__testref_cfdna__", "analyte": "cfdna",      "chromosomes": ["21"], "contexts": ["CG"], "provenance": "..." },
    "buffy_coat": { "sample_id": "REF_BUFFY_01", "sample_dir": "/work/samples/__testref_buffy__", "analyte": "buffy_coat", "chromosomes": ["21"], "contexts": ["CG"], "provenance": "..." }
  },
  "groups": {
    "healthy": { "label": "healthy", "analyte": "cfdna", "sample_dirs": ["/work/samples/h1", "/work/samples/h2"] },
    "PCa":     { "label": "PCa",     "analyte": "cfdna", "sample_dirs": ["/work/samples/p1", "/work/samples/p2"] }
  }
}
```

- `samples` are keyed by analyte or logical name; analyte aliases (`plasma`,
  `cf_dna`, `buffy`, `wbmc`, ...) normalize to canonical `cfdna`/`buffy_coat`
  (see [`analyte_profiles`](../../packages/methylutils/methyl_utils/analyte_profiles.py)).
- `sample_dir` / `sample_dirs` accept absolute paths (`/work/...`) or
  repo-relative paths (resolved from the repository root, for committed fixtures).
- A sample is considered *available* only when its directory exists and contains
  at least one `{chr}-{ctx}.h5` file.

A committed default lives at [`tests/real_data/registry.json`](../../tests/real_data/registry.json);
a fully populated example is [`tests/real_data/registry.example.json`](../../tests/real_data/registry.example.json).

## Where operators set it (precedence)

Highest wins:

1. `METHYL_TEST_DATA_CONFIG` - path to a standalone registry JSON.
2. Site manifest `testing` block (`METHYL_SITE_CONFIG` / `/work/site/methyl_site.json`).
3. Committed repo default (`tests/real_data/registry.json`).
4. Empty registry (all `real_data` tests skip).

The site manifest is the natural home for `/work`-mounted samples because those
paths are deployment-specific; the committed fixture is repo-relative and runs
everywhere. See the site schema `testing` block in
[`schemas/config/site_manifest.schema.json`](../../schemas/config/site_manifest.schema.json)
and the example [`workflow_engine/domain/profiles/site_grch38.example.json`](../../workflow_engine/domain/profiles/site_grch38.example.json).

## Writing a real-data test

```python
import pytest
from methyl_utils import MethylSample
from methyl_utils.testing import require_reference_sample, require_reference_group


@pytest.mark.real_data
def test_loads_real_cfdna_chr21():
    sample = require_reference_sample("cfdna", chromosome="21", context="CG")
    ms = MethylSample.load_from_h5(sample.h5_path("21", "CG"))
    assert len(ms.pos) > 0


@pytest.mark.real_data
def test_healthy_cohort_loads():
    group = require_reference_group("healthy", min_samples=2)
    assert len(group.sample_dirs) >= 2
```

`require_reference_sample` / `require_reference_group` call `pytest.skip(...)` with
an actionable message when the sample or group is unavailable.

Current real-data tests:

- [`packages/methylutils/methyl_utils/tests/test_load_from_h5_real_sample.py`](../../packages/methylutils/methyl_utils/tests/test_load_from_h5_real_sample.py)
- [`packages/methylderivedmeasures/tests/test_genome_measures_real_sample.py`](../../packages/methylderivedmeasures/tests/test_genome_measures_real_sample.py)
- [`packages/methylcluster/tests/test_reference_group_real_data.py`](../../packages/methylcluster/tests/test_reference_group_real_data.py)

## Running

```bash
# Hosted / local: real_data tests skip unless a sample is mounted.
./scripts/run_tests_ci.sh

# Only the real-data tier (self-hosted, /work mounted):
METHYL_SITE_CONFIG=/work/site/methyl_site.json \
  .venv/bin/python -m pytest -m real_data -rs -v
```

CI: [`ci/azure-pipelines-real-data.yml`](../../ci/azure-pipelines-real-data.yml)
runs `-m real_data` on `production-work-agents`.

## Designating a sample (operator checklist)

1. Produce the H5 with the real MethylExtractor (FASTQ -> BAM -> `{chr}-{ctx}.h5`).
   For the committed fixture, restrict to a small region and a **non-PHI** source.
2. Place per-analyte reference samples under `/work/samples/` (or commit a tiny
   fixture under `tests/real_data/fixtures/`).
3. Declare them in the site manifest `testing` block (or a
   `METHYL_TEST_DATA_CONFIG` JSON).
4. Record provenance (source, consent basis, MethylExtractor release, region) in
   the `provenance` field and in the
   [validation evidence index](../regulatory/validation-evidence-index.md).

## Data governance

Reference samples must be **non-PHI**: use public/consented sources. The
`provenance` field and the regulatory evidence index record the source, consent
basis, and producing MethylExtractor release so a real-data test result is
traceable validation evidence, not just convenience.

## SamplePrep real-data canary (optional `sample_prep_canary`)

In addition to extracted-H5 reference samples, the registry may declare a
**SamplePrep canary** under `sample_prep_canary` (same site `testing` block or a
standalone `METHYL_SAMPLE_PREP_CANARY_CONFIG` JSON). This drives the on-demand
FASTQ→align→QC→extract matrix across `linear`, `pangenome` (engineering-only),
and `pangenome_wgbs`.

- Provenance pin: [`../tests/real_data/sample_prep_canary/provenance.json`](../../tests/real_data/sample_prep_canary/provenance.json)
  (`GSE261315` / `SRR28293403` / HG00621).
- Example config: [`../tests/real_data/sample_prep_canary/registry.example.json`](../../tests/real_data/sample_prep_canary/registry.example.json)
  (also embedded in [`registry.example.json`](../../tests/real_data/registry.example.json)).
- Provision: `scripts/provision_sample_prep_canary.sh` (checksummed full + subset into `fastqStorage`).
- Execute: `scripts/smoke_sample_prep_real.sh` / [`ci/azure-pipelines-sample-prep-canary.yml`](../../ci/azure-pipelines-sample-prep-canary.yml).
- Validation helpers: `methyl_utils.testing.sample_prep_canary`.

Do **not** put production FASTQ paths into golden fixtures or catalog unit tests.
Operator thresholds (`mapping_rate_delta`, etc.) are site/config values — never
Python `DEFAULT_*` constants.
