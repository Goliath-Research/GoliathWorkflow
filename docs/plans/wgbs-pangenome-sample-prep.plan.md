---
name: WGBS Pangenome SamplePrep
overview: Add a worker-side methylGrapher C2T/G2A SamplePrep path that preserves existing alignment-QC, extraction-QC, HDF5, read-level pattern, and informME contracts. Keep stock Giraffe and linear fq2bam_meth paths intact, with the BS bundle resolved from QNAP-backed site configuration and baked into task resolvedConfig.

> **Status: IMPLEMENTED.** Actions `sample.methylgrapher_wgbs_align` / `sample.methylgrapher_wgbs_extract`, `alignmentMode=pangenome_wgbs` / `useWgbsPangenome`, QNAP asset `pangenome-grch38-d9-bs-1.70`, SamplePrep three-way routing, CAAS fingerprints, unit tests, and 64K image smoke script are in tree. Gate production procedure promotion on the real-sample canary in [`workers/tests/test_methylgrapher_wgbs_canary.md`](../../workers/tests/test_methylgrapher_wgbs_canary.md).

azure_devops:
  type: Feature
  title: "WGBS pangenome SamplePrep (methylGrapher)"
  work_item_id: null
  epic_id: 413
todos:
  - id: typed-bs-assets
    content: Define pangenome_wgbs mode, typed C2T/G2A asset/config models, QNAP reference asset, and resolvedConfig binding
    status: completed
  - id: worker-dual-align
    content: Implement and register worker-side methylGrapher dual alignment with QC-compatible GRCh38 BAM artifacts
    status: completed
  - id: worker-graph-extract
    content: Implement graph-aware marginal and read-level pattern HDF5 extraction for existing extraction-QC/informME contracts
    status: completed
  - id: sampleprep-routing
    content: Route initial/remediation alignment and extraction across linear, stock pangenome, and WGBS pangenome modes
    status: completed
  - id: idempotency-validation
    content: Add CAAS fingerprints, schemas, unit/integration/canary tests, and 64K ARM64 image validation
    status: completed
  - id: docs-release
    content: Promote the plan, add AB#413 traceability, document QNAP inventory, and release the runtime bundle/image
    status: completed
---

# WGBS Pangenome SamplePrep

## Chosen architecture
Use a dedicated worker capability and two typed actions: `sample.methylgrapher_wgbs_align` for dual C2T/G2A alignment plus QC-compatible BAM production, and `sample.methylgrapher_wgbs_extract` for graph-aware methylation extraction into the existing marginal/pattern HDF5 contracts. This avoids feeding an unvalidated converted-read BAM into MethylExtractor while preserving downstream extraction QC and informME.

```mermaid
flowchart LR
  Fastq[FASTQs] --> Mode{alignmentMode}
  Mode -->|linear| Fq2bam[fq2bam_meth]
  Mode -->|pangenome| Giraffe[stock_Giraffe]
  Mode -->|pangenome_wgbs| MgAlign[methylGrapher_C2T_G2A]
  MgAlign --> Gaf[merged_GAF]
  MgAlign --> QcBam[QC_compatible_BAM]
  Fq2bam --> MethylQc[methyl_qc]
  Giraffe --> MethylQc
  QcBam --> MethylQc
  MethylQc --> ExtractMode{WGBS_pangenome}
  ExtractMode -->|false| ExistingExtract[MethylExtractor]
  ExtractMode -->|true| MgExtract[graph_aware_extract]
  ExistingExtract --> H5[H5_and_patterns]
  MgExtract --> H5
  H5 --> ExtractionQc[extraction_qc]
  H5 --> InfoMe[informME]
```

## Typed configuration and immutable assets
- `alignmentMode: "pangenome_wgbs"` and derived `useWgbsPangenome` in [`workflow_engine/domain/pipeline_profiles.py`](../../workflow_engine/domain/pipeline_profiles.py). `usePangenome=true` for shared lifecycle semantics.
- Pydantic step/task models in [`workers/methyl_worker/task_models/sample_prep_models.py`](../../workers/methyl_worker/task_models/sample_prep_models.py).
- QNAP-backed `pangenome-grch38-d9-bs-1.70` reference asset; site `actionConfig.methylgrapher_wgbs` / `pangenome_wgbs_genome`.
- [`buffy_wgbs_pangenome_gene_fc.procedure.json`](../../workflow_engine/domain/profiles/procedures/buffy_wgbs_pangenome_gene_fc.procedure.json) selects `pangenome_wgbs`; no silent stock Giraffe fallback when BS assets are absent.

## Worker-side alignment and QC
- Image: [`workers/docker/methylgrapher/`](../../workers/docker/methylgrapher/) + [`smoke_64k.sh`](../../workers/docker/methylgrapher/smoke_64k.sh).
- Runner: [`workers/methyl_worker/methylgrapher_wgbs_runner.py`](../../workers/methyl_worker/methylgrapher_wgbs_runner.py).
- Catalog actions registered; QC BAM / dedup metrics / qc-metrics.tar keep `sample.methyl_qc` unchanged.

## Graph-aware extraction and workflow routing
- `sample.methylgrapher_wgbs_extract` emits `{chrom}-{context}.h5` and `{chrom}-{context}.patterns.h5`.
- [`sample_prep.program.json`](../../workflow_engine/domain/fixtures/sample_prep.program.json) and remediate program use three-way align + extract branches.

## Idempotency, validation, and rollout
- CAAS fingerprints include FASTQ + C2T/G2A asset digests + tool/image pins; `forceRealign` clears align + extract outputs.
- Unit tests under `workers/tests/test_methylgrapher_wgbs.py`; canary checklist in `workers/tests/test_methylgrapher_wgbs_canary.md`.
- Promote runtime-bundle with new actions/procedure/schemas and pin `METHYL_METHYLGRAPHER_IMAGE` after canary acceptance.
