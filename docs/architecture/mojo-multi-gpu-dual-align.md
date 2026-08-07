# Mojo multi-GPU dual Align (leadership brief)

**One sentence:** Align mode is a science choice; GPU vendor is a site choice — both linear and pangenome WGBS run on the same Mojo-portable stack (NVIDIA, AMD, or CPU), so leaving Lambda GH200s does not force Clara Parabricks or abandon a 10-year linear workflow.

## Two Align modes (independent of GPU)

| Mode | Procedure / default | Align action | Downstream |
|------|---------------------|--------------|------------|
| **pangenome_wgbs** (recommended) | `buffy_wgbs_pangenome_gene_fc` | `sample.methylgrapher_wgbs_align` → Mojo Giraffe GAF | `methylgrapher_wgbs_extract` |
| **linear** (legacy / plasma) | `buffy_wgbs_linear_gene_fc`, cfDNA packs | `sample.parabricks_fq2bam` → Clara **or** MojoFq2bamMeth | `methyl_extract` |

Operators set `alignmentMode` (and procedure pack). They do **not** pick NVIDIA vs AMD in the disease pack.

## Portable device contract (`actionConfig` → `resolvedConfig`)

| Knob | Where | Values |
|------|-------|--------|
| `align_device` / `giraffe_device` | `actionConfig.methylgrapher_wgbs` and `actionConfig.parabricks` | `auto` \| `cpu` \| `nvidia` \| `amd` |
| `engine` (pangenome) | `methylgrapher_wgbs.engine` | `mojo` \| `python` |
| `engine` (linear) | `parabricks.engine` | `mojo` \| `parabricks` (Clara rollback) |
| `image` | same sections | e.g. `epimethyl/methylgrapher:1.70-mojo-cuda` or `:1.70-mojo-rocm` |

`auto` probes `nvidia-smi` then `rocm-smi`, else CPU. Workers consume baked `resolvedConfig` only (config-not-env).

## Accelerator honesty

- **Supported near-term:** NVIDIA CUDA, AMD ROCm (Instinct), CPU fallback.
- **Clouds:** any host that offers those GPUs (Lambda, GCP A3/A4 or AMD VMs, Azure ND/MI, etc.).
- **Not promised:** Google TPU — Mojo’s GPU surface is NVIDIA / AMD / Apple Metal today.

## Why ship both

Leadership can keep linear BAM → MethylExtract. Engineering keeps pangenome as the Buffy default and can show fair wall-time / CpG concordance on the **same** GPU class. Vendor lock-in is no longer the reason to stay on linear Clara.

## Rollback

- Pangenome: `align_engine=cpu_vg` or `engine=python` + stock `:1.70` image.
- Linear: `parabricks.engine=parabricks` + NGC Clara image.

See plan [`docs/plans/mojo-multi-gpu-dual-align.plan.md`](../plans/mojo-multi-gpu-dual-align.plan.md).
