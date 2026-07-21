---
name: Proteomics GPU Process Pack
overview: "Add proteomics as a third omics modality: GPU DIA-NN mass-spec quantification on the existing Lambda/Nebius GH200 NVIDIA workers, feeding a generalized samples-x-features seam (shared with RNA-Seq) into differential-abundance selection, the tabular sklearn classifier, covariate stacking, and Monte Carlo stability. Includes non-commercial extensions: panel-matrix ingest (Olink/SomaScan/open, CPU), Prosit rescoring + in-silico libraries, and Casanovo de novo (GPU). DDA/MSFragger deferred (commercial license)."
azure_devops:
  type: Feature
  title: "Proteomics GPU process pack"
  work_item_id: null
  epic_id: 413
todos:
  - id: modality-generalize
    content: Add proteomics modality; extract shared omics_features seam; refactor rna_express to delegate; feature_mode proteomics_abundance
    status: completed
    work_item_id: null
  - id: diann-ingest
    content: diann_runner.py (GPU Docker) + download_msdata + proteomics_prep models/handlers + proteomics.diann capability + generalized docker-gpu probe
    status: completed
    work_item_id: null
  - id: qc-abundance
    content: proteomics_qc package + register_abundance on omics_features + abundance_matrix_ref/protein_sample_ref domain schemas
    status: completed
    work_item_id: null
  - id: downstream
    content: pipeline.protein_de_select via omics_features (log2+median+min-impute) wired into tabular sklearn + covariate stacking
    status: completed
    work_item_id: null
  - id: programs-profiles-config
    content: sample_prep_proteomics + proteomics_study_lifecycle programs, proteomics_research profile, proteomics config keys, site proteomics_reference
    status: completed
    work_item_id: null
  - id: gpu-provisioning
    content: platform_matrix.env PROTEOMICS_* images per arch, setup_gpu_node proteomics.env, systemd EnvironmentFile, gpu_worker_runbook GH200 + page-size note
    status: completed
    work_item_id: null
  - id: panel-ingest
    content: sample.ingest_panel (Olink NPX / SomaScan RFU / open) to abundance.h5 (CPU)
    status: completed
    work_item_id: null
  - id: prosit-rescore
    content: Prosit GPU sample.dl_rescore + proteomics.prosit capability + arm64 image env
    status: completed
    work_item_id: null
  - id: casanovo-denovo
    content: Casanovo GPU sample.casanovo + proteomics.casanovo capability + arm64 image env
    status: completed
    work_item_id: null
  - id: register-deploy-docs-tests
    content: Register actions, regenerate task/config/domain schemas + catalog, deploy script, tests, E2E + usage docs, regulatory update, promote plan
    status: completed
    work_item_id: null
---

# Proteomics GPU Process Pack

> **Status: Implemented** (2026-07). Proteomics is a third omics modality on the shared control plane. GPU DIA-NN + panel ingest + Prosit + Casanovo ship as capabilities on the same GH200 VMs; RNA-Seq and proteomics now share the `omics_features` seam. DDA/MSFragger deferred. Operators must confirm an arm64 GPU DIA-NN image before enabling `proteomics.diann` on Grace/Hopper.

## Framing
Proteomics is a third `primary_modality` (`proteomics`), like RNA-Seq but **not a Parabricks drop-in**: the front is a GPU mass-spec search engine (DIA-NN) or a CPU panel-matrix ingest; the back reuses the generalized `samples x features` seam.

```mermaid
flowchart TD
  src{"ingest_mode? (usePanel)"}
  src -->|"panel (CPU)"| panel["sample.ingest_panel"]
  src -->|"dia (GPU)"| dl["sample.download_msdata"] --> diann["sample.diann (GPU)"]
  diann --> rescore["sample.dl_rescore (GPU Prosit, optional)"]
  rescore --> reg["sample.register_abundance"]
  diann --> reg
  panel --> qc["sample.proteomics_qc"]
  reg --> qc
  qc --> de["pipeline.protein_de_select"]
  de --> model["tabular sklearn + covariate stacking + validation.stability"]
```

## Implemented components
- **Shared seam:** `packages/omicsfeatures/omics_features` (`feature_store`, `matrix.load_feature_matrix` with transform/normalize/impute, `de_select`); `rna_express` refactored to delegate (public API preserved); `BackendSharedParams.feature_mode` gains `proteomics_abundance`.
- **Ingest:** `workers/methyl_worker/diann_runner.py` (GPU DIA-NN, `METHYL_DIANN_IMAGE`), `prosit_runner.py`, `casanovo_runner.py`; `sample.download_msdata`; task models + handlers in `proteomics_prep`. Generalized capability probe `_PROBE_DOCKER_GPU` (`DOCKER_GPU_TOOL_IMAGE_ENV`) with `proteomics.diann/prosit/casanovo` in `GPU_REQUIRED_CAPABILITIES`; `proteomics.panel_ingest` is CPU.
- **Adapters/QC:** `packages/proteomicsfeatures` (DIA-NN report + panel ingest -> `abundance.h5`, `pipeline.protein_de_select`), `packages/proteomicsqc` (`sample.proteomics_qc`); domain schemas `abundance_matrix_ref` + `protein_sample_ref`.
- **Programs/profile/config:** `sample_prep_proteomics` + `proteomics_study_lifecycle` programs, `proteomics_research` profile, `proteomics_quant/proteomics_qc/protein_de_select` config keys, site `proteomics_reference`; `ingest_mode`->`usePanel` / `rescore`->`useRescore` resolution in `pipeline_profiles.py`.
- **Provisioning:** `platform_matrix.env` `PROTEOMICS_*_IMAGE_{amd64,aarch64}`, `detect_platform.sh:resolve_proteomics_image`, `setup_gpu_node.sh` writes `proteomics.env`, systemd unit loads it, `gpu_worker_runbook.md` GH200/arm64 + page-size caution.
- **Register/deploy/tests/docs:** actions in `action_catalog.py`; regenerated task/config/domain schemas + `catalog.json`; deploy script compiles the proteomics programs; tests in `packages/omicsfeatures/tests`, `packages/proteomicsfeatures/tests`, `workflow_engine/tests/test_proteomics_pack.py` + golden fixtures; E2E doc `end-to-end-workflow-proteomics.md`, usage ch.22, regulatory roadmap row.

## Explicitly NOT in scope
- DDA / MSFragger / FragPipe (commercial license) - later addition (CPU capability; can also build experimental spectral libraries for DIA-NN).
- Methylation/RNA science changes beyond the shared-seam refactor.

## Validation
- Catalog validates; task/config schema drift checks pass; RNA tests green after the refactor.
- Profile resolves `usePanel`/`useRescore`; both proteomics programs compile.
- Ingest (DIA-NN report + Olink NPX/wide panels) -> abundance.h5; DE recovers planted differential proteins; `feature_mode=proteomics_abundance` accepted.
