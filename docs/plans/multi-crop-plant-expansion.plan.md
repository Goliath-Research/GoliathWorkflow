---
name: Multi-crop plant expansion
overview: Expand the plant abiotic-stress application pack with Ensembl Plants site recipes for soybean, maize, and wheat, plus a plant trait-association prior (not Open Targets, which is human-only). Grafting, epi-GBS, plant cell-deconvolution atlases, and ag SaMD pivotal stay deferred.

> **Status: Implemented** (2026-07). Crop site recipes + offline `plant_traits` mapper prior shipped; Open Targets stays human-only. Grafting remains deferred.

azure_devops:
  type: Feature
  title: "Multi-crop plant sites + plant trait priors"
  work_item_id: null
  epic_id: 413
todos:
  - id: crop-site-recipes
    content: Add site_*.example.json + download_*.sh for soybean Wm82, maize B73, wheat IWGSC (Ensembl Plants release-58)
    status: completed
    work_item_id: null
  - id: crop-overlays
    content: Add per-crop project/context stubs under docs/examples/samd/plant-abiotic-stress/ and update ch.23 / README
    status: completed
    work_item_id: null
  - id: plant-traits-source
    content: Add mapper enrich_source=plant_traits + plant_traits_path loader; demo Arabidopsis drought TSV; schema export
    status: completed
    work_item_id: null
  - id: ci-tests-docs
    content: CI smoke for crops + plant_traits tests; regulatory/ch.24 notes; promote docs/plans/multi-crop-plant-expansion.plan.md under AB#413
    status: completed
    work_item_id: null
---

# Multi-crop plant sites + plant trait priors

## Decisions locked

| Topic | Choice |
|-------|--------|
| Crops in this wave | **Soybean (Wm82 / *Glycine max*)**, **maize (B73 / *Zea mays*)**, **wheat (IWGSC RefSeq / *Triticum aestivum*)** — same Ensembl Plants release family as TAIR10 (release-58 pins) |
| Open Targets | **Do not enable** for plant packs — Platform is human therapeutic targets only. Replace the deferred “OpenTargets for plants” item with a **plant trait prior** seam |
| Trait prior source | Offline / config-driven **gene↔trait association TSV** (drought / abiotic stress terms) loaded by the mapper when `enrich_source` includes a new `plant_traits` token; seed a small committed Arabidopsis drought demo table + document how operators add SoyBase / MaizeGDB / WheatIS extracts |
| Still deferred | Grafting; plant cell-type deconvolution atlases; epi-GBS modality; ag SaMD pivotal ladder |

```mermaid
flowchart LR
  subgraph sites [Site recipes]
    TAIR[TAIR10 existing]
    SOY[site_glycine_max_wm82]
    MZ[site_zea_mays_b73]
    WH[site_triticum_aestivum_iwgsc]
  end
  subgraph app [Shared application pack]
    LIFE[plant_stress_study_lifecycle]
    ANALYTE[plant_tissue analyte]
    PRESET[plant-stress-core]
  end
  subgraph prior [Plant trait prior]
    TSV[gene_trait TSV]
    MAP[mapper plant_traits source]
  end
  sites --> LIFE
  ANALYTE --> LIFE
  PRESET --> LIFE
  TSV --> MAP
  MAP --> LIFE
```

## Delivered

### 1. Crop site examples + download scripts

| Crop | Site example | Script | STRING taxon |
|------|--------------|--------|--------------|
| Soybean | `site_glycine_max_wm82.example.json` | `scripts/download_glycine_max_wm82.sh` | `3847` |
| Maize | `site_zea_mays_b73.example.json` | `scripts/download_zea_mays_b73.sh` | `4577` |
| Wheat | `site_triticum_aestivum_iwgsc.example.json` | `scripts/download_triticum_aestivum_iwgsc.sh` | `4565` |

### 2. Application-pack crop overlays

Under `docs/examples/samd/plant-abiotic-stress/`: per-crop project manifests + context overlays; ch.23 / pack README updated.

### 3. Plant trait prior

- `enrich_source=plant_traits` + `plant_traits_path` on `MapperStepConfig` / CLI / `BedtoolsMapper`
- `PlantTraitEnricher` joins offline TSV into existing `disease_*` columns (`source=plant_traits`)
- Demo: `data/arabidopsis_drought_gene_traits.tsv`; Arabidopsis overlay enables it
- Schema export: `schemas/config/mapper.schema.json`

### 4. CI + docs

- Crop smoke manifests under `workflow_engine/domain/checks/plant_abiotic_stress/`
- Extended `test_plant_abiotic_stress_pack.py` + mapper unit tests
- Regulatory roadmap, ch.24, ANALYTE_PROFILES, historical plant pack plan note

## Explicitly still deferred

- Graft / trait-introgression pack
- Plant cell-type deconvolution atlases
- epi-GBS / new aligners
- SaMD pivotal / clinical claim ladder for agriculture
