---
name: DMP Gene Modeling Modes
overview: Formalize five statistically distinct DMP/gene modeling alternatives as process-agnostic engine capabilities and generic pipeline profiles—decoupled from any single study, analyte, or domain check deployment.
azure_devops:
  type: Feature
  title: "DMP/gene modeling modes (historical)"
  work_item_id: 635
  epic_id: 413
todos:
  - id: architecture-layers-doc
    content: Document engine vs generic profile vs study manifest vs domain program in domain-program-language.md and composable-pipeline plan (no study-specific runbooks)
    status: pending
    work_item_id: 636
  - id: modeling-mode-enums
    content: Add dmp_modeling_mode / gene_modeling_mode + separate dmp/gene BA targets to MonteCarloConfig; seed generic profiles from pipeline_profiles.py only
    status: pending
    work_item_id: 637
  - id: generic-profile-presets
    content: Add/rename profile presets by statistical role (mc_dmp_discovery, mc_dmp_featurecuts, mc_gene_mapper, mc_gene_featurecuts, mc_two_phase_dmp_then_gene)—not by cohort name
    status: pending
    work_item_id: 638
  - id: mapper-gene-stability
    content: Add load_mapper_genes() and gene_axis=mapper in stability.py for mode 3 (mapper-ranked gene recurrence)
    status: pending
    work_item_id: 639
  - id: dmp-source-stable
    content: Extend gene FeatureCuts DMP source to stable panel for mode 5 Phase B (artifact-driven, not study-hardcoded)
    status: pending
    work_item_id: 640
  - id: dmp-export-simplify
    content: Replace classifier/core/extended consumer surface with dmps-*-selected.csv + strict min/max BA behavior in methyldmpselect/detector
    status: pending
    work_item_id: 641
  - id: two-phase-orchestration
    content: Generic two-phase profile pair (phase_a_dmp_stability + phase_b_gene_from_stable_dmps) wired via artifact paths in context, not domain-specific programs
    status: pending
    work_item_id: 642
  - id: tests-modes
    content: Unit/integration tests for all five statistical modes using fixture manifests only (workflow_engine/domain/fixtures)
    status: pending
    work_item_id: 643
isProject: false
---

# DMP / Gene Modeling Modes (process-agnostic)

## Design principle: do not conflate engine, profile, and study

The workflow engine must stay **process-agnostic**—the same compiler, catalog actions, and IF/FOREACH topology whether execution is local or database-backed. Study-specific facts (cohort labels, analyte, regulatory stage, output paths) belong in **study manifests** (`project.json`). **Generic profiles** encode reusable statistical procedures; **domain programs** encode topology only (which actions run, in what order, gated by scope booleans).

```mermaid
flowchart TB
  subgraph engine [WorkflowEngine_ProcessAgnostic]
    catalog[ActionCatalog]
    compiler[DomainProgramCompiler]
    scheduler[LocalOrDatabaseScheduler]
  end

  subgraph generic [GenericProfiles_RepoVersioned]
    profA[mc_dmp_discovery]
    profB[mc_dmp_featurecuts]
    profC[mc_gene_featurecuts]
    profD[mc_two_phase_dmp_then_gene]
  end

  subgraph deploy [StudyDeployment_Runtime]
    manifest[project.json]
    context[instance_context]
    artifacts[/work/artifacts]
  end

  compiler --> scheduler
  generic --> context
  manifest --> context
  context --> scheduler
  scheduler --> artifacts
```

**What we are NOT doing:** baking experiment names, analyte choices, or cohort-specific thresholds into engine code or domain check folders as if they were universal settings.

**What we ARE doing:** exposing five **logical alternatives** for methylation feature selection and stability—common in internal validation and regulatory documentation (repeated splits, panel stability, held-out performance gates)—as first-class, composable profile axes applicable across analytes that share methylation levels, groups, comparisons, and model backends.

---

## Five statistical alternatives (regulatory framing)

These map to standard feasibility / analytical-validation patterns: discover features on training partitions, gate by held-out balanced accuracy, aggregate recurrence across Monte Carlo replicates, then optionally freeze a panel for confirmatory modeling.

| # | Statistical intent | DMP step | Gene step | Typical regulatory use |
|---|-------------------|----------|-----------|------------------------|
| **1** | Full discovery pool; stability on raw detected loci | No validation-driven DMP subset | None | Exploratory locus recurrence; biology / mapper interpretation |
| **2** | Validation-tuned DMP panel per split | FeatureCuts_DMPs (BA gate) | None | Analytical feature selection with explicit held-out gate |
| **3** | Gene-level biology from mapped loci; no gene k-search | Discovery (or FC) | Mapper-ranked genes only | Pathway / annotation stability without classifier gene panel |
| **4** | Separate gene panel search on mapped features | Discovery (optional FC) | FeatureCuts_Genes (BA gate) | Independent gene-axis validation; DMP and gene gates decoupled |
| **5** | Sequential: locus stability first, then gene modeling on consensus panel | Phase A → stable DMP CSV | Phase B → map stable loci → optional FeatureCuts_Genes | Two-stage panel lock common before freeze / production model |

Analytes (plasma, buffy-coat, tissue) differ in signal and QC; **groups, comparisons, and model backends** stay in the manifest. Profiles select **which statistical branch** runs—not which study.

---

## Is it currently possible? (engine capability matrix)

| # | Mode | Today | Generic profile direction | Gap |
|---|------|-------|---------------------------|-----|
| **1** | Discovery DMPs only | **Yes** | `mc_dmp_discovery` (maps from existing `gene_enricher_stability`-style flags) | None for DMP-only |
| **2** | FeatureCuts_DMPs | **Yes** | `mc_dmp_featurecuts` (maps from `dmp_panel_stability`) | End-to-end FC loci for mapper/gene not always aligned |
| **3** | Mapper genes, no gene FC | **Partial** | `mc_gene_mapper` | Stability reads enricher, not mapper `all-gene_name-combined.csv` |
| **4** | Discovery-mapped + FeatureCuts_Genes | **Partial** | `mc_gene_featurecuts` | Conflated BA knobs; ad-hoc dmp_source flag only on gene features |
| **5** | Genes from stable DMPs (two-phase) | **No (automated)** | `mc_two_phase_dmp_then_gene` | Stable panel feeds freeze/detector, not Phase B gene FC |

Reference implementation today lives in [`pipeline_profiles.py`](workflow_engine/domain/pipeline_profiles.py) presets and [`stability.py`](packages/methylvalidation/methyl_validation/stability.py)—not in study domain folders.

---

## Root engineering issues (cross-study)

### 1. Three consumer-facing DMP tiers (discovery / core / extended)

[`methyldetector.py`](packages/methyldetector/methyl_detector/core/methyldetector.py) exports discovery, classifier core, and extended margin panels. Downstream tools disagree on which to read. For a process-agnostic API, consumers should see:

- **Raw pool** — detector output (`dmps-*-discovery.csv`; not a "mode")
- **Selected panel** — one artifact after optional FeatureCuts (`dmps-*-selected.csv`)

### 2. `min_core_dmps` semantics vs statistical intent

`min_core_dmps` currently **expands** a panel when FeatureCuts selects fewer loci than the floor—potentially **lowering** held-out BA. For regulatory gating, min/max should mean:

- **min_dmps** — reject or exclude run if selected panel too small *after* BA gate (not expand into worse BA)
- **max_dmps** — cap search/export
- **target_ba** — explicit held-out threshold (e.g. 0.95)

Defaults belong in **profile templates**, tuned per study in manifest overrides—not hardcoded from one experiment.

### 3. One knob drives two actions

`stability_target_balanced_accuracy` and `stability_featurecuts_enabled` affect both DMP FeatureCuts and gene FeatureCuts. Modes 2 and 4 require **separate** DMP vs gene BA targets.

### 4. Stability aggregation axes are incomplete

[`compute_gene_stability`](packages/methylvalidation/methyl_validation/stability.py) supports enricher genes or FeatureCuts gene panels—not mapper-ranked genes (mode 3) or stable-DMP-mapped genes (mode 5 Phase B).

---

## Target configuration model (engine-level)

Two independent axes in [`MonteCarloConfig`](packages/methylvalidation/methyl_validation/config.py), seeded by **generic profiles** only:

```yaml
dmp_modeling_mode: raw_pool | featurecuts | stable_panel
gene_modeling_mode: none | mapper_ranked | featurecuts | from_stable_dmp_panel
```

Derived IF flags (`runDmpSelection`, `runGeneFeaturecuts`, etc.) remain for [`DomainProgram`](workflow_engine/domain/) compatibility—programs stay topology-only; they must not embed study thresholds.

| Mode | `dmp_modeling_mode` | `gene_modeling_mode` | `runDmpSelection` | `runGeneFeaturecuts` |
|------|---------------------|------------------------|-------------------|----------------------|
| 1 | raw_pool | none | false | false |
| 2 | featurecuts | none | true | false |
| 3 | raw_pool | mapper_ranked | false | false |
| 4 | raw_pool | featurecuts | false | true |
| 5 Phase B | stable_panel | featurecuts | false | true |

Phase A for mode 5: `dmp_modeling_mode: featurecuts`, `gene_modeling_mode: none` → artifact `stable_dmps_production.csv` passed via context (`stableDmpCsv` / `freeze_stable_dmp_csv`), not a named study path.

---

## Parameter model (profile defaults, manifest overrides)

### DMP FeatureCuts (mode 2, Phase A of mode 5)

| Param | Role |
|-------|------|
| `dmp_featurecuts_target_ba` | Held-out BA gate (profile default e.g. 0.95; study may override) |
| `dmp_featurecuts_min_dmps` | Minimum panel size **after** FC; fail/exclude run if unmet (no BA-diluting expansion) |
| `dmp_featurecuts_max_dmps` | Upper cap on k-search / export |
| `dmp_featurecuts_fail_if_below_target` | Strict mode: exclude iteration from stability if BA not met |

### Gene FeatureCuts (modes 4, 5 Phase B)

| Param | Role |
|-------|------|
| `gene_featurecuts_target_ba` | Separate from DMP |
| `gene_featurecuts_min_genes` / `max_genes` | Panel size bounds without forcing arbitrary k |
| `gene_featurecuts_loci_source` | `raw_pool \| featurecuts_selected \| stable_panel` |

### Export simplification

- Keep detector raw pool filename internally.
- Single downstream **selected** panel artifact for mapper, stability, and gene FC.
- Legacy classifier/extended filenames supported one release via compatibility loaders.

---

## Two-phase orchestration (mode 5) — generic, artifact-driven

User-selected pattern: **two explicit phases**, not an in-loop switch inside one study program.

**Phase A profile** (`phase_a_dmp_stability`): MC iterations, DMP stability only, emits `stable_dmps_production.csv`.

**Phase B profile** (`phase_b_gene_from_stable_dmps`): Context references Phase A artifact path; mapper + optional gene FeatureCuts; gene stability on classifier panels or mapper ranks.

No new domain check per study—same [`mc_stability.program.json`](workflow_engine/domain/fixtures/mc_stability_staged.program.json) topology with different profile + context. Study manifests supply paths and regulatory metadata only.

```mermaid
flowchart LR
  phaseA[PhaseA_profile_dmp_stability]
  artifact[stable_dmps_production.csv]
  phaseB[PhaseB_profile_gene_from_stable]
  phaseA --> artifact
  artifact --> phaseB
```

---

## Documentation scope (generic only)

Update [`docs/reference/domain-program-language.md`](docs/reference/domain-program-language.md) and [`docs/plans/composable-pipeline-flexibility.plan.md`](docs/plans/composable-pipeline-flexibility.plan.md):

- Artifact ladder: program → profile → manifest → context
- Profile matrix keyed by **statistical mode**, not Buffy / H_PCa / prostate-cancer
- Regulatory narrative: MC stability, BA gates, panel freeze—cite [`docs/theory/chapters/12-two-workflows.qmd`](docs/theory/chapters/12-two-workflows.qmd) patterns
- Example commands use **fixture** manifests under `workflow_engine/domain/fixtures/`

**Do not add** study-specific runbooks to domain check READMEs as part of this work; studies may document their chosen profile + overrides locally under `/work/projects/...` if needed.

---

## Implementation phases

### Phase 1 — Engine config and generic profiles

- `dmp_modeling_mode`, `gene_modeling_mode`, split BA targets
- Rename/organize profiles in [`workflow_engine/domain/profiles/`](workflow_engine/domain/profiles/) by statistical role
- `pipeline_profiles.py` seeds IF flags from modes; deprecate analyte-named profile aliases gradually (`buffy_mc_gene_fc` → pointer to `mc_gene_fc`)

### Phase 2 — DMP export and strict gating semantics

- `dmps-*-selected.csv`; `fail_if_below_target` behavior
- Compatibility loaders for legacy names

### Phase 3 — Stability sources and two-phase wiring

- Mapper gene loader (mode 3)
- Stable-panel loci source for gene FC (mode 5 Phase B)
- Generic Phase A / Phase B profile pair; context-bound artifact paths

### Phase 4 — Tests and docs

- Fixture-only integration tests (no `/work/projects/...` paths in CI)
- Profile matrix and mode selection guide for FDA-facing documentation authors

---

## Out of scope for this plan

- Per-study parameter tuning (train_fraction, BA thresholds, min_dmps) — set in manifest/profile overrides at deploy time
- Analyte comparison reports or experiment post-mortems
- New domain check folders named after cohorts
