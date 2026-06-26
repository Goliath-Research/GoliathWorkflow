# Parabricks fq2bam_meth on GPU workers

Sample prep alignment (`sample.parabricks_fq2bam`) runs **NVIDIA Clara Parabricks `fq2bam_meth`** inside Docker on GPU worker nodes. Implementation: [`methyl_worker/parabricks_runner.py`](../methyl_worker/parabricks_runner.py).

## Prerequisites

- NVIDIA GPU driver + `nvidia-smi` on the host
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) so `docker run --gpus all` exposes GPUs
- Docker CLI on PATH
- Parabricks image pulled locally (licensed via NGC)
- **samtools** on the worker host PATH (used by `sample.methyl_qc` for BAM flagstat alignment guardrails when `alignment_guardrails.flagstat_enabled` is true; installed by `setup_host.sh --system-deps`)

## Configuration

Set on the worker host or job environment:

```bash
export METHYL_PARABRICKS_IMAGE=nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1
export METHYL_PARABRICKS_GPU_FLAGS="--gpus all"
export METHYL_PARABRICKS_BWA_THREADS=16
```

Pick the newest image validated on your cluster’s GPU generation (Hopper/Blackwell vs Ampere). The repo does not pin a single image tag in code.

## Smoke test

```bash
export METHYL_PARABRICKS_IMAGE=nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1
./scripts/verify_parabricks.sh
```

## Manual / HPC alignment

```bash
export METHYL_PARABRICKS_IMAGE=nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1
./scripts/parabricks_fq2bam_meth.sh DPLST-051425-111148 \
  --sample-dir /work/samples/DPLST-051425-111148 \
  --reference /work/genomes/human_genome/release-114/Homo_sapiens.GRCh38.dna.primary_assembly.fa
```

Equivalent CLI (after `pip install -e workers`):

```bash
methyl-parabricks-align DPLST-051425-111148 --sample-dir /work/samples/DPLST-051425-111148
```

## Outputs

Under `{sampleDir}`:

- `{sampleId}.bam` — input to `sample.methyl_extract`
- `{sampleId}.qc-metrics.tar` — input to `sample.methyl_qc` (WGBS guardrails)
- `{sampleId}.deduplicate_metrics.txt`, `{sampleId}.fq2bam_meth.log`

See [`workflow_engine/contract/sample_prep_capabilities.md`](../../workflow_engine/contract/sample_prep_capabilities.md) for the full contract.
