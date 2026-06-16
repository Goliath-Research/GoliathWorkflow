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
| `project.json` | `chromosomes`, `step_config.methyl_extract` |

### Extract contexts vs downstream `contexts`

| Config | Purpose |
|--------|---------|
| `project.contexts` | Downstream centroid/detector (often `["CG"]` only) |
| `step_config.methyl_extract.extract_contexts` | What sample prep writes (default `["CG","CHG","CHH"]`) |

Extracting all contexts lets `sample.delete_bam` reclaim space without losing CHG/CHH for later analysis.

## Post-deploy smoke test

```bash
./scripts/verify_methyl_extractor.sh
```

## Manual / local dev

```bash
./scripts/methyl_extract.sh DPLST-051425-111148 \
  --project /work/prostate-cancer/configs/project_Plasma_healthy_vs_PCa.json \
  --sample-dir /work/samples/DPLST-051425-111148
```

Optional dev env: `METHYL_EXTRACTOR_BIN` if the binary is not on default PATH.

## Outputs

Under `{sampleDir}`:

- `{chrom}-{ctx}.h5` — methylation matrices (e.g. `1-CG.h5`, `1-CHG.h5`)
- `{sampleId}.methyl_extract.log` — command log

See [`workflow_engine/contract/sample_prep_capabilities.md`](../../workflow_engine/contract/sample_prep_capabilities.md) for the full contract.
