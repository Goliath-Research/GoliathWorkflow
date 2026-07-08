# MethylExtractor on sample-prep workers

Sample prep extraction (`sample.methyl_extract`) runs the **native MethylExtractor binary** installed on GPU/CPU worker nodes. Implementation: [`methyl_worker/extract_runner.py`](../methyl_worker/extract_runner.py).

## Source and deploy

MethylExtractor is maintained separately at `/home/ubuntu/MethylExtractor`. On each worker machine:

```bash
cd /home/ubuntu/MethylExtractor
make deps && make && make install
```

This installs `MethylExtractor` to `/usr/local/bin/` (machine image provisioning, not per-task JSON).

## Production worker contract

Remote workers receive **`input_json`** from the workflow engine and read **`project.json`** from shared storage (`/work/...`). No environment variables are required.

| Source | Fields |
|--------|--------|
| `input_json` | `sampleId`, `sampleDir`, `project`, `referenceFasta` (+ optional overrides) |
| `resolvedConfig` / profile | `actionConfig.methyl_extract` (chromosomes from study manifest; extract contexts, read-level knobs) |

Workers on the distributed path receive merged config via `--resolved-config`; they do **not** read `step_config` from `project.json`.

### Extract contexts vs downstream `contexts`

| Config | Purpose |
|--------|---------|
| `project.contexts` | Downstream centroid/detector (often `["CG"]` only) |
| `actionConfig.methyl_extract.extract_contexts` | What sample prep writes (default `["CG","CHG","CHH"]`) |

Extracting all contexts lets `sample.delete_bam` reclaim space without losing CHG/CHH for later analysis.

## Post-deploy smoke test

```bash
./scripts/verify_methyl_extractor.sh
```

## Manual / local dev

```bash
./scripts/methyl_extract.sh DPLST-051425-111148 \
  --project /work/projects/prostate-cancer/configs/project_Plasma_healthy_vs_PCa.json \
  --sample-dir /work/samples/DPLST-051425-111148
```

Optional dev env: `METHYL_EXTRACTOR_BIN` if the binary is not on default PATH.

## Outputs

Under `{sampleDir}`:

| Artifact | Pattern | Role |
|----------|---------|------|
| Per-chrom HDF5 | `{chrom}-{ctx}.h5` | Marginal per-CpG counts (e.g. `1-CG.h5`) |
| Read-level sidecar | `{chrom}-{ctx}.patterns.h5` | Per-tile read co-methylation histograms (when `--read-level`) |
| Extraction log | `{sampleId}.methyl_extract.log` | Command log |

### Read-level pattern sidecar (optional)

When profile `actionConfig.methyl_extract.read_level.enabled` is true (or `--read-level`
is passed), MethylExtractor also writes `{chrom}-{ctx}.patterns.h5` files. Schema:
[`docs/reference/read_level_pattern_contract.md`](../../docs/reference/read_level_pattern_contract.md).

Profile example:

```json
"methyl_extract": {
  "read_level": { "enabled": true, "tile_size": 4 }
}
```

Worker CLI flags: `--read-level`, `--tile-size=<k>` (forwarded from resolved config).

See [`workflow_engine/contract/sample_prep_capabilities.md`](../../workflow_engine/contract/sample_prep_capabilities.md) for the full contract.
