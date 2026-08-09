# Mojo multi-GPU dual Align (leadership brief)

**One sentence:** Align mode is a science choice; GPU vendor is a site choice — `pangenome_wgbs` always runs native-Mojo on NVIDIA **or** AMD (one DeviceContext implementation), while Clara Parabricks is an **explicit** linear/stock-pangenome config choice, never an automatic Mojo failure path.

Canonical operator/developer detail: [`docs/implementation/sample-preparation-flow.md`](../implementation/sample-preparation-flow.md).

## Two Align modes (independent of GPU vendor)

| Mode | Procedure / default | Align action | Downstream |
|------|---------------------|--------------|------------|
| **pangenome_wgbs** (recommended) | `buffy_wgbs_pangenome_gene_fc` | `sample.methylgrapher_wgbs_align` → **native-Mojo** Giraffe GAF (NVIDIA CUDA or AMD HIP) | `methylgrapher_wgbs_extract` (native-Mojo MethylCall/MergeCpG) |
| **linear** / **pangenome** (explicit) | `buffy_wgbs_linear_gene_fc`, cfDNA packs, stock Giraffe packs | `sample.parabricks_fq2bam` / `sample.parabricks_giraffe` → Clara (NVIDIA) **or** linear MojoFq2bamMeth when `parabricks.engine=mojo` | `methyl_extract` |

Operators set `alignmentMode` (and procedure pack). They do **not** pick NVIDIA vs AMD in the disease pack — site image + host runtime do.

## Portable device contract (`actionConfig` → `resolvedConfig`)

| Knob | Where | Values |
|------|-------|--------|
| `align_device` / `giraffe_device` | `actionConfig.methylgrapher_wgbs` and `actionConfig.parabricks` | `auto` \| `nvidia` \| `amd` (production); `cpu` only for unknown GPU vendors / dev |
| `engine` (pangenome) | `methylgrapher_wgbs.engine` | `mojo` (canonical) \| `python` (dev/parity rollback) |
| `align_engine` | `methylgrapher_wgbs.align_engine` | `gpu_giraffe` \| `mojo_giraffe` (canonical); `cpu_vg` only unknown-GPU / parity |
| `engine` (linear) | `parabricks.engine` | `parabricks` (Clara, **explicit**) \| `mojo` (MojoFq2bamMeth) |
| `image` | same sections | e.g. `epimethyl/methylgrapher:1.70-mojo-cuda` or `:1.70-mojo-rocm` |

`auto` probes `nvidia-smi` then `rocm-smi`. On known NVIDIA/AMD fleets, DeviceContext failure is **fail-closed** — not a switch to Clara. Workers consume baked `resolvedConfig` only (config-not-env).

## Accelerator honesty

- **Production `pangenome_wgbs`:** NVIDIA CUDA **and** AMD ROCm (Instinct) via the same native-Mojo binary.
- **Production `linear` / `pangenome` (Clara):** NVIDIA only — selected by config, not by Mojo failure.
- **CPU align:** only when the GPU vendor is **unknown** (e.g. Google Cloud GPUs that are neither NVIDIA nor AMD), or explicit dev/parity rollback.
- **Not promised:** Google TPU — Mojo’s GPU surface is NVIDIA / AMD (/ Apple Metal) today.

## Why ship both modes

Leadership can keep linear BAM → MethylExtract via **explicit** Clara (or linear Mojo) procedure packs. Engineering keeps pangenome_wgbs as the Buffy default on the **same** Mojo stack across NVIDIA and AMD. Vendor lock-in is no longer the reason to stay on linear Clara.

## Rollback (explicit only)

- **Switch science mode:** set `alignmentMode: linear` (or `pangenome`) + Clara image — never automatic.
- **Unknown GPU vendor:** `align_engine=cpu_vg` / host seeds.
- **Dev/parity:** `engine=python` + stock `:1.70` image, or `parabricks.engine=parabricks` for linear Clara.

See plan [`docs/plans/mojo-multi-gpu-dual-align.plan.md`](../plans/mojo-multi-gpu-dual-align.plan.md).
