---
name: Plant deconv epi-GBS seams
overview: Invest now in protocol-separated SamplePrep (Parabricks WGBS vs epi-GBS), a generic Docker-align + demux seam, and atlas-as-cfg-asset deconvolution (multi-context extract, no blood fallback)—so future plant atlases and alternate aligners are data/config/image only, not release-per-tool Python.

> **Status: Implemented** (2026-07). Platform seams shipped; plant atlases and epi-GBS tools are post-release config/data/image.

azure_devops:
  type: Feature
  title: "Plant deconv + epi-GBS platform seams"
  work_item_id: null
  epic_id: 413
todos:
  - id: eval-decisions
    content: "Lock architecture decisions: atlases via cfg path not wheel; Parabricks vs epiGBS program split; docker_align + demux seams"
    status: completed
    work_item_id: null
  - id: deconv-runtime-seams
    content: Multi-context H5 extract; plant_tissue hard-error without basis path; HiTIMED plant_tissue via path-loaded JSON; unit tests
    status: completed
    work_item_id: null
  - id: deconv-cfg-asset
    content: cfg.reference_asset roles houseman_seed_basis / hitimed_hierarchy_basis; site pins; fixture; compose script; with_deconv program
    status: completed
    work_item_id: null
  - id: protocol-split-sampleprep
    content: libraryProtocol (wgbs_linear|wgbs_pangenome|epi_gbs); sample_prep_epigbs.program.json
    status: completed
    work_item_id: null
  - id: docker-align-demux
    content: sample.docker_align + sample.demultiplex catalog/handlers; epi-GBS program wiring
    status: completed
    work_item_id: null
  - id: qc-presets-docs
    content: epi_gbs profile overlay; catalog/docs; promote under AB#413
    status: completed
    work_item_id: null
---

# Plant deconv + epi-GBS platform seams

## Locked decisions (implemented)

1. Atlases live outside the wheel (`seed_basis_path` / `hierarchy_basis_path` + cfg roles).
2. HiTIMED plant support = path-loaded JSON with `analyte_trees.plant_tissue`.
3. `libraryProtocol` ∈ `wgbs_linear` | `wgbs_pangenome` | `epi_gbs`; Parabricks stays on `sample_prep.program.json`; epi-GBS uses `sample_prep_epigbs.program.json`.
4. epi-GBS remains `primary_modality: methylation`.
5. Default plant lifecycle omits deconv; `plant_stress_study_lifecycle_with_deconv.program.json` includes it when an atlas is provisioned.

## Key artifacts

| Area | Path |
|------|------|
| Multi-context extract + plant guard | `packages/methyldeconv/methyl_deconv/core/{houseman,hitimed,runner}.py` |
| Houseman CI fixture | `workflow_engine/domain/checks/plant_abiotic_stress/data/plant_houseman_seed_fixture.json` |
| HiTIMED composer | `scripts/build_plant_hitimed_basis.py` |
| With-deconv lifecycle | `workflow_engine/domain/fixtures/plant_stress_study_lifecycle_with_deconv.program.json` |
| epi-GBS SamplePrep | `workflow_engine/domain/fixtures/sample_prep_epigbs.program.json` |
| Actions | `sample.demultiplex`, `sample.docker_align` |
| Profile overlay | `workflow_engine/domain/profiles/epi_gbs.profile.json` |
| cfg roles | `houseman_seed_basis`, `hitimed_hierarchy_basis` in SQL CHECK |

## Operator paths (post-release, no Python)

**Plant atlas:** provision JSON → set site `actionConfig.cell_deconvolution.*_basis_path` → run `…_with_deconv` program.

**epi-GBS:** set `libraryProtocol=epi_gbs`, pin `docker_align.image` + `argv`, optional `demultiplex.barcode_tsv` (or `skip: true` if demuxed upstream) → run `sample_prep_epigbs.program.json`.
