---
name: Proteomics Sage DDA
overview: "Add a DDA ingest mode to the proteomics pack using Sage (Apache-2.0, Rust) instead of the license-encumbered MSFragger: a CPU Sage runner (Docker image with native-binary fallback), a dda ingest branch in the sample-prep program, a sage abundance-ingest source feeding the shared samples-x-features seam, plus config, provisioning, tests, and docs. No GPU required (runs on cheap CPU workers, not the GH200s)."
azure_devops:
  type: Feature
  title: "Proteomics DDA via Sage"
  work_item_id: null
  epic_id: 413
todos:
  - id: sage-runner
    content: sage_runner.py (CPU Docker image + native binary fallback), SageTaskInput/Output, _handle_sage handler, proteomics.sage capability + _PROBE_SAGE probe (no GPU gate), methyl-sage CLI
    status: completed
    work_item_id: null
  - id: sage-ingest-source
    content: parse_sage_quant + register_sample_abundance source=sage (Sage lfq.tsv -> abundance.h5)
    status: completed
    work_item_id: null
  - id: program-config
    content: 3-way ingest (panel|dia|dda) in sample_prep_proteomics program; useDda flag + ingest_mode=dda in pipeline_profiles; Sage config keys + profile doc
    status: completed
    work_item_id: null
  - id: provisioning
    content: platform_matrix SAGE image per arch, setup_gpu_node/write_worker_env METHYL_SAGE_IMAGE, gpu_worker_runbook proteomics.sage CPU row
    status: completed
    work_item_id: null
  - id: register-tests-docs
    content: Register sample.sage in catalog, regenerate schemas + golden fixture, tests, usage/E2E docs, regulatory + plan update
    status: completed
    work_item_id: null
---

# Proteomics Sage DDA ingest

> **Status: Implemented** (2026-07). DDA now ships on the proteomics pack via **Sage** (Apache-2.0, Rust), the open replacement for MSFragger. `ingest_mode: dda` runs Sage on CPU workers, produces LFQ protein intensities, and feeds the same `abundance.h5` contract as DIA-NN and panels. GPU is not required.

## Framing
The proteomics pack deferred DDA only because MSFragger.jar is license-encumbered. Sage removes the blocker: fast, CPU-only, multi-arch, Apache-2.0. It slots in as a third `ingest_mode` (`dia` GPU / `panel` CPU / `dda` CPU) and reuses the whole downstream unchanged.

## Implemented components
- **Runner + capability:** [workers/methyl_worker/sage_runner.py](../../workers/methyl_worker/sage_runner.py) (prefers `METHYL_SAGE_IMAGE` Docker CPU run, else `sage` binary via `METHYL_SAGE_BIN`/PATH; writes a Sage config JSON from `proteomics_quant` + site `protein_fasta`). Capability `proteomics.sage` with a `_PROBE_SAGE` probe in [capabilities.py](../../workers/methyl_worker/capabilities.py) - CPU, **not** in `GPU_REQUIRED_CAPABILITIES`. `SageTaskInput/Output`, `_handle_sage`, `methyl-sage` CLI.
- **Ingest source:** `parse_sage_quant` + `register_sample_abundance(source="sage")` in [proteomics_features/ingest.py](../../packages/proteomicsfeatures/proteomics_features/ingest.py) (Sage `lfq.tsv` -> `abundance.h5`).
- **Program + config:** 3-way ingest in [sample_prep_proteomics.program.json](../../workflow_engine/domain/fixtures/sample_prep_proteomics.program.json); `useDda` flag + `ingest_mode=dda` resolution in [pipeline_profiles.py](../../workflow_engine/domain/pipeline_profiles.py); Sage knobs documented in [proteomics_research.profile.json](../../workflow_engine/domain/profiles/proteomics_research.profile.json).
- **Provisioning:** `PROTEOMICS_SAGE_IMAGE_*` in [platform_matrix.env](../../scripts/platform_matrix.env); `METHYL_SAGE_IMAGE` written by [setup_gpu_node.sh](../../scripts/setup_gpu_node.sh) and [write_worker_env.sh](../../scripts/write_worker_env.sh) (so non-GPU workers advertise it); `proteomics.sage` CPU row in [gpu_worker_runbook.md](../../docs/deployment/gpu_worker_runbook.md).
- **Register/tests/docs:** `sample.sage` in [action_catalog.py](../../workers/methyl_worker/action_catalog.py); regenerated task/catalog schemas + golden fixture; tests in `packages/proteomicsfeatures/tests` + `workflow_engine/tests/test_proteomics_pack.py`; usage ch.22 + proteomics E2E doc + regulatory roadmap updated.

## Explicitly NOT in scope
- Sage results -> spectral library -> DIA-NN (DDA-assisted DIA) - later optional extension.
- TMT/iTRAQ labeled quant (LFQ only).
- MSFragger/FragPipe (commercial).

## Validation
- `proteomics.sage` advertises on a CPU worker when `METHYL_SAGE_IMAGE` or the `sage` binary is present; not GPU-gated.
- 3-way ingest program compiles; `useDda` resolves from `ingest_mode=dda`.
- `register_abundance(source=sage)` on a synthetic Sage `lfq.tsv` yields `abundance.h5`; downstream unchanged; task/config/catalog drift checks pass.
