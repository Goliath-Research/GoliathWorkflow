# MethylPipeline Operations Manual

This manual describes the supported operator workflow and the repository-level contracts developers should follow when extending the pipeline.

For package math and theory, see [Theory and packages](THEORY_AND_PACKAGES.md).

## For Users

### Supported install paths

Host install:

```bash
bash scripts/setup_host.sh --system-deps --gpu
```

Common variants:

- CPU-only: omit `--gpu`
- Custom virtualenv: add `--venv /path/to/venv`
- Conda / RAPIDS workflow: `bash scripts/setup_host_conda.sh --install-miniforge`
- Verification: `bash scripts/verify_setup.sh`

If the environment already exists and only the local packages need installing:

```bash
bash scripts/install_all.sh --pipeline-reqs
```

Docker / container users should use the scripts under `scripts/` or the production image in `docker/Dockerfile.production`.

### Supported project schema

Use one project JSON with:

- `project_name`
- `output_base`
- `controls`
- `diseases`
- `comparisons`
- optional `samples_base_path`, `chromosomes`, `contexts`, `path_remap`
- optional `step_config`

Legacy `group1` / `group2` and flat `groups` still load, but the supported workflow is `controls` / `diseases` / `comparisons`.

Project-aware CLIs:

- `methyl-centroid`
- `methyl-detector`
- `methyl-mapper`
- `methyl-enricher`
- `methyl-classifier`
- `methyl-predictor`
- `methyl-qc` / `methyl-alignment-qc`

Related tools:

- `methyl-centroid-explorer`
- `methyl-detector-explorer`
- `methyl-cluster`

Validation is separate:

- `methyl-validation --config ...`

The Monte Carlo validation config points at a `base_project`; the validation CLI does not accept `--project`.

### Sample input expectations

Sample directories are expected to contain chromosome/context HDF5 files such as:

- `1-CG.h5`
- `1-CHG.h5`
- `1-CHH.h5`

Project `sample_paths` entries may be:

- direct sample directory paths
- text files with one sample path per line
- CSV files with a `sample`, `path`, or `sample_path` column
- JSON arrays of paths

If `samples_base_path` is set, entries inside those files may be sample folder names instead of absolute paths.

### Output layout

Given `project_root = {output_base}/{project_name}`, the canonical layout is:

```text
{project_root}/
├── centroids/
│   ├── controls/<control-side-label>/<group>/
│   └── diseases/<disease-side-label>/<group>/
├── detections/<control_group>/<disease_group>/
├── mapper/<control_group>/<disease_group>/
├── enricher/<control_group>/<disease_group>/
├── classifiers/<control_group>/<disease_group>/
├── predictors/<control_group>/<disease_group>/
├── alignment_qc/
└── clustering/
```

For control/disease projects with multiple comparisons, downstream tools automatically use comparison-specific directories to avoid overwriting.

### Workflow order

Run steps in this order:

1. `methyl-centroid --project ... --group all`
2. `methyl-detector --project ...`
3. `methyl-mapper --project ...`
4. `methyl-enricher --project ...`
5. `methyl-classifier --project ...`
6. `methyl-predictor --project ...`
7. `methyl-validation --config ...` when you want Monte Carlo evaluation

Optional side workflows:

- `methyl-qc` / `methyl-alignment-qc`
- `methyl-cluster`
- explorer CLIs

### CLI reference

| Command | Canonical mode | Notes |
|---------|----------------|-------|
| `methyl-centroid` | `--project PROJECT --group all` | Builds all configured centroids. |
| `methyl-detector` | `--project PROJECT` | Auto-switches to per-comparison outputs when needed. |
| `methyl-mapper` | `--project PROJECT` | Reads detector CSVs from `detections/<control>/<disease>/`. |
| `methyl-enricher` | `--project PROJECT` | Reads mapper combined gene CSV from the matching comparison directory. |
| `methyl-classifier` | `--project PROJECT` | Scores samples using classifier bundles from detector or classifier outputs. |
| `methyl-predictor` | `--project PROJECT` | Uses `step_config.predictor` test sets by default. |
| `methyl-validation` | `--config VALIDATION_JSON` | Monte Carlo runner; config contains `base_project`. |
| `methyl-qc` / `methyl-alignment-qc` | `--project PROJECT` | Optional alignment QC extraction. |

### Step config guidance

Use `step_config` inside the project JSON for defaults. Resolution order is:

1. project-derived paths and shared project fields
2. `step_config[step]`
3. `--step-override`
4. CLI flags

Common step keys:

- `centroid`: `base_config`, `parallel_combinations`, `min_samples`, `save_batch_summary`
- `detection`: `alpha`, `delta_mean_reduction`, `effect_size_coverage`, `contexts`, `chromosomes`, `max_dmps_for_classifier`
- `mapper`: `csv_pattern`, `gtf`, `disease_term`, `enrich_*`
- `enricher`: `gene_column`, `libraries`, `disease_only`
- `classifier`: `weight_method`, `temperature`, `enable_platt_calibration`, `chromosome_weights`
- `predictor`: `test_control_paths`, `test_disease_paths`, `test_group_paths`, `debug`
- `alignment_qc`: `groups`, `sample_paths`, `validate_schema`
- `cluster`: clustering defaults for pre-centroid subgroup discovery

Secrets should come from the environment or per-run override files, not from tracked configs.

### Quick examples

Binary or one-comparison project:

```bash
methyl-centroid --project configs/project_PCa_vs_Healthy.json --group all
methyl-detector --project configs/project_PCa_vs_Healthy.json
methyl-mapper --project configs/project_PCa_vs_Healthy.json
methyl-enricher --project configs/project_PCa_vs_Healthy.json
methyl-classifier --project configs/project_PCa_vs_Healthy.json
methyl-predictor --project configs/project_PCa_vs_Healthy.json
```

Monte Carlo validation:

```bash
methyl-validation --config configs/monte_carlo.json
```

### Troubleshooting

- GPU missing: run `nvidia-smi`, then reinstall with `scripts/setup_host.sh --gpu`
- Path mismatch after moving data: use `path_remap` in the project JSON
- Missing detector CSVs for mapper: check `detections/<control>/<disease>/`
- Missing predictor metrics: verify `step_config.predictor` test sets or CLI overrides
- Grok / enrichment auth: set `GROK_API_KEY` in the environment or a step override file

## For Developers

### Repository layout

- `packages/`: installable pipeline packages
- `configs/`: repo-level project examples
- `docs/`: repo-level workflow and architecture docs
- `scripts/`: install / container / verification helpers
- `docker/`: production and development container definitions

### Config and path contract

The code-level source of truth is `packages/methylutils/methyl_utils/pipeline_config.py`.

Important rules:

- prefer `controls` / `diseases` / `comparisons`
- keep shared options at the project top level
- use comparison directories for detector / mapper / enricher / classifier / predictor outputs
- resolve step configs through the package `project_resolver.py` module, not by duplicating path logic in each CLI

### Adding or changing a step

When a package supports `--project`, it should:

1. load the shared project contract with `methyl_utils.load_project()`
2. derive canonical output paths from project helpers
3. merge `step_config[step_name]`
4. optionally merge `--step-override`
5. validate against that package's config model

New CLI entry points should be registered in the package `pyproject.toml`.

### Testing

From repo root:

```bash
pytest packages/
```

Or target a package:

```bash
pytest packages/methyldetector/tests -v
```

Keep tests next to the active package, not in unrelated repo-level folders.

### Documentation rules

- pipeline workflow docs live under `docs/`
- package-specific behavior lives under `packages/<name>/README.md` and `packages/<name>/docs/`
- keep docs aligned to the active ECDF pipeline and the canonical project-driven CLI workflow
