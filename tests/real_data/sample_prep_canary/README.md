# SamplePrep real-data canary fixtures

Pinned public WGBS sample for periodical SamplePrep qualification. These reads
come from the **methylGrapher / HPRC pangenome project** (GSE261315) and live in
the pangenome inventory tree — not lab `fastqStorage`.

| Field | Value |
|-------|-------|
| GEO series | GSE261315 |
| GEO sample | GSM8140413 (`WGBS-HG00621-Rep1`) |
| SRA run | SRR28293403 |
| Individual | HG00621 (HPRC) |
| Layout | paired-end Bisulfite-Seq |
| Local root | `/work/genomes/pangenome/canary/gse261315/SRR28293403/` |
| QNAP / S3 | `s3://epimethyl/genomes/pangenome/canary/gse261315/SRR28293403/` |

See [`provenance.json`](provenance.json) and [`registry.example.json`](registry.example.json).

## Provision once

```bash
source .venv/bin/activate
# Default --stage-root is /work/genomes/pangenome
bash scripts/provision_sample_prep_canary.sh --subset-pairs 2000000

# Mirror the canary subtree to myQNAPcloud (same relative path)
scripts/sync_genomes_to_s3.sh --only pangenome/canary
```

Merge `checksums.json` SHA-256 values into site `testing.sample_prep_canary`
with `fastq_storage.basePath=/work/genomes/pangenome`.

## Run

```bash
unset WORKER_STUB_EXTERNAL
bash scripts/smoke_sample_prep_real.sh --tier subset   # routine
bash scripts/smoke_sample_prep_real.sh --tier full     # after subset passes
```

Stock Giraffe (`pangenome`) is an engineering comparator only — do not require
methylation parity with linear or methylGrapher.
