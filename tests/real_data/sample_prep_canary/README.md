# SamplePrep real-data canary fixtures

Pinned public WGBS sample for periodical SamplePrep qualification:

| Field | Value |
|-------|-------|
| GEO series | GSE261315 |
| GEO sample | GSM8140413 (`WGBS-HG00621-Rep1`) |
| SRA run | SRR28293403 |
| Individual | HG00621 (HPRC) |
| Layout | paired-end Bisulfite-Seq |

See [`provenance.json`](provenance.json) for license/citation and [`registry.example.json`](registry.example.json) for the typed config shape.

## Provision once

```bash
source .venv/bin/activate
bash scripts/provision_sample_prep_canary.sh \
  --subset-pairs 2000000 \
  --stage-root /work/fastq-storage
```

Copy/sync `canary/` into deployment `fastqStorage` (myQNAPcloud today) and merge
`checksums.json` SHA-256 values into the site `testing.sample_prep_canary` block
(or `METHYL_SAMPLE_PREP_CANARY_CONFIG`).

## Run

```bash
unset WORKER_STUB_EXTERNAL
bash scripts/smoke_sample_prep_real.sh --tier subset   # routine
bash scripts/smoke_sample_prep_real.sh --tier full     # after subset passes
```

Stock Giraffe (`pangenome`) is an engineering comparator only — do not require
methylation parity with linear or methylGrapher.
