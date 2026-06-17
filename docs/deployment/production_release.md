# Production release layout (GPU workers)

Production GPU workers consume **versioned releases** on fast shared storage (`/work/epimethyl`). No git checkouts on worker nodes at runtime.

See also: [worker_node.md](worker_node.md), [gpu_worker_runbook.md](gpu_worker_runbook.md), [worker_provision.md](worker_provision.md), [platform_matrix.md](platform_matrix.md).

## Directory layout

```
/work/epimethyl/
  current -> releases/2026.06.1
  releases/
    2026.06.1/
      manifest.json
      requirements-worker.lock
      wheels/*.whl
      runtime-bundle/          # schemas, verify scripts, systemd units
      methyl-extractor-linux-aarch64.tar.gz
      methyl-extractor-linux-amd64.tar.gz
  docker/                      # shared Docker data-root (all GPU VMs)
  venv-aarch64/
  venv-amd64/
  methyl-extractor-aarch64/
  methyl-extractor-amd64/
  env/
    worker.env
    parabricks.env
    workflow_versions.json
  data/
  runs/
```

| Path | Shared? | Updated |
|------|---------|---------|
| `releases/<ver>/` | Yes | Per release tag (CI) |
| `docker/` | Yes | Once per release promote (`docker pull`) |
| `venv-<arch>/` | Yes | When lockfile changes |
| `methyl-extractor-<arch>/` | Yes | Per release × arch |
| `/etc/docker/daemon.json` | Per VM | Points `data-root` at shared `docker/` |

## manifest.json

Schema: [`schemas/deployment/epimethyl_release_manifest.schema.json`](../../schemas/deployment/epimethyl_release_manifest.schema.json).

Example:

```json
{
  "version": "2026.06.1",
  "python": "3.12",
  "parabricks_image": "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1",
  "parabricks_image_digest": "sha256:…",
  "docker_data_root": "/work/epimethyl/docker",
  "min_driver_version": "550.xx",
  "requirements_lock": "requirements-worker.lock",
  "runtime_bundle": "runtime-bundle",
  "artifacts": {
    "aarch64": {
      "methyl_extractor": "methyl-extractor-linux-aarch64.tar.gz",
      "sha256": "…"
    },
    "amd64": {
      "methyl_extractor": "methyl-extractor-linux-amd64.tar.gz",
      "sha256": "…"
    }
  }
}
```

## Build a release (CI or admin)

From a tagged MethylPipeline checkout:

```bash
source .venv/bin/activate
bash scripts/build_release.sh \
  --version 2026.06.1 \
  --output /work/epimethyl/releases/2026.06.1
```

Produces wheels, `requirements-worker.lock`, runtime-bundle, and a draft `manifest.json`.

MethylPipeline CI template: [`ci/azure-pipelines-methyl-pipeline-release.yml`](../../ci/azure-pipelines-methyl-pipeline-release.yml).

MethylExtractor tarballs are built separately ([`ci/azure-pipelines-methyl-extractor-release.yml`](../../ci/azure-pipelines-methyl-extractor-release.yml)) and copied into the release directory before promote.

## Promote a release

Run **once** on shared storage (serializes `docker pull`):

```bash
bash scripts/promote_release.sh \
  --root /work/epimethyl \
  --release /work/epimethyl/releases/2026.06.1 \
  --arch aarch64 \
  --pull-parabricks
```

This will:

1. Verify `manifest.json` and tarball checksums
2. Extract MethylExtractor to `/work/epimethyl/methyl-extractor-<arch>/`
3. Install or refresh `/work/epimethyl/venv-<arch>/` from release wheels
4. Optionally `docker pull` Parabricks into shared `docker/`
5. Update `/work/epimethyl/current` symlink
6. Write `env/worker.env` and `env/parabricks.env`

Repeat `--arch amd64` when both architectures share the same release version.

## Rollback

```bash
bash scripts/promote_release.sh \
  --root /work/epimethyl \
  --release /work/epimethyl/releases/<previous-ver> \
  --arch aarch64 \
  --skip-docker-pull
```

Restart workers after rollback: `sudo systemctl restart methyl-worker.service`.

## Phase 2: Azure Artifacts

Replace local `wheels/` with a PyPI feed URL in `install_release.sh`:

```bash
pip install --index-url "https://pkgs.dev.azure.com/EpiMethyl/_packaging/<feed>/pypi/simple/" \
  -r requirements-worker.lock
```

Universal Packages can host MethylExtractor tarballs and optional `docker save` fallbacks with the same manifest filenames.
