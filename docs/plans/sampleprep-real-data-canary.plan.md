---
name: SamplePrep Real Data Canary
overview: "Add a two-tier, on-demand real-WGBS SamplePrep canary using a pinned public `GSE261315` sample: a deterministic paired-read subset for routine runs and the complete sample for periodic qualification. The same reads will traverse linear Parabricks, stock Giraffe (engineering comparator), and bisulfite-aware methylGrapher branches through QC, extraction, archive, and structured cross-mode reporting."

> **Status: IMPLEMENTED.** Pinned run `SRR28293403` (GSM8140413 / HG00621-Rep1). Provision with [`scripts/provision_sample_prep_canary.sh`](../../scripts/provision_sample_prep_canary.sh); execute with [`scripts/smoke_sample_prep_real.sh`](../../scripts/smoke_sample_prep_real.sh); GitHub Actions [`.github/workflows/sample-prep-canary.yml`](../../.github/workflows/sample-prep-canary.yml). Operator docs: [`workflow_engine/docs/sample_prep_test_bed.md`](../../workflow_engine/docs/sample_prep_test_bed.md).

azure_devops:
  type: Feature
  title: "SamplePrep real-data canary"
  work_item_id: null
  epic_id: 413
todos:
  - id: pin-canary-data
    content: Select and provenance-pin one GSE261315 SRA WGBS pair; provision checksummed full and deterministic-subset objects in fastqStorage.
    status: completed
  - id: typed-canary-config
    content: Extend the typed real-data registry/config contract for SamplePrep canaries, storage references, asset pins, and operator-set acceptance bounds.
    status: completed
  - id: real-canary-runner
    content: Implement the three-mode real SamplePrep orchestrator with preflights, DB workflow execution, polling, and isolated outputs.
    status: completed
  - id: canary-validation
    content: Implement artifact/action/QC validation and JSON, JUnit, and qualification reports with focused tests.
    status: completed
  - id: scheduled-pipeline
    content: Add the self-hosted manual/scheduled subset and full qualification pipeline.
    status: completed
  - id: catalog-contract
    content: Repair methylGrapher extraction golden fixtures and verify complete SamplePrep catalog/schema/golden coverage.
    status: completed
  - id: canary-docs
    content: Document provisioning, execution, retention, interpretation, and the stock-Giraffe negative-comparator limitation.
    status: completed
  - id: validate-canary
    content: Run unit, drift, smoke, and real subset validation; establish the first full-sample baseline after subset success.
    status: completed
---

# SamplePrep Real-Data Canary

## Design
- Use a paired-end human WGBS run from [GSE261315](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE261315), the public dataset produced for methylGrapher on HPRC individuals. **Pinned:** `SRR28293403` / `GSM8140413` / `WGBS-HG00621-Rep1` (see [`tests/real_data/sample_prep_canary/provenance.json`](../../tests/real_data/sample_prep_canary/provenance.json)).
- Ingest the complete FASTQ pair once into the configured `fastqStorage` (myQNAPcloud today), then create and checksum a stable paired-read subset. Tests consume these immutable objects rather than downloading or subsampling SRA at run time.
- Treat `pangenome`/stock Giraffe as a workflow and robustness comparator only: require successful execution/artifact contracts, but do not impose biological parity with bisulfite-aware modes.

```mermaid
flowchart LR
  source[GSE261315RawPair] --> full[FullPinnedPair]
  source --> subset[DeterministicPairedSubset]
  subset --> routine[RoutineCanary]
  full --> qualification[FullQualification]
  routine --> linear[LinearParabricks]
  routine --> stock[StockGiraffe]
  routine --> wgbs[MethylGrapherWGBS]
  qualification --> linear
  qualification --> stock
  qualification --> wgbs
  linear --> report[QCExtractionArchiveReport]
  stock --> report
  wgbs --> report
```

## Delivered artifacts
| Artifact | Role |
|----------|------|
| [`tests/real_data/sample_prep_canary/provenance.json`](../../tests/real_data/sample_prep_canary/provenance.json) | Pinned accession |
| [`tests/real_data/sample_prep_canary/registry.example.json`](../../tests/real_data/sample_prep_canary/registry.example.json) | Typed canary config example |
| [`scripts/provision_sample_prep_canary.sh`](../../scripts/provision_sample_prep_canary.sh) | SRA → full + subset + checksums |
| [`scripts/smoke_sample_prep_real.sh`](../../scripts/smoke_sample_prep_real.sh) | Three-mode real orchestrator entry |
| [`workflow_engine/ops/sample_prep_canary.py`](../../workflow_engine/ops/sample_prep_canary.py) | DB start / poll / report |
| [`packages/methylutils/methyl_utils/testing/sample_prep_canary.py`](../../packages/methylutils/methyl_utils/testing/sample_prep_canary.py) | Artifact validation + JUnit/Markdown |
| [`.github/workflows/sample-prep-canary.yml`](../../.github/workflows/sample-prep-canary.yml) | Manual + monthly subset schedule |

## Operator notes
1. Provision FASTQs once; merge SHA-256 into site `testing.sample_prep_canary`.
2. Run subset routinely (`--tier subset`); run `--tier full` after subset success / quarterly.
3. Stock Giraffe failures of biological parity are expected; only workflow/artifact contract is gated.
4. Do not conflate this canary with catalog/golden PR gates or `WORKER_STUB_EXTERNAL=1` smoke.
