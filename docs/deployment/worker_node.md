# GPU worker node deployment

Host-native workers on shared storage under `/work/goliath`. Docker is used **only** for Parabricks alignment. The gateway does **not** mount `/work`.

**Production:** privileged host applies SQL twins + Python populate; gateway installs on local disk (`provision_gateway_node.sh`); GPU VMs use [`provision_worker_node.sh`](../../scripts/provision_worker_node.sh) (`--join-mode auto`). See [`production-platform.md`](production-platform.md), [`production_release.md`](production_release.md), [`gpu_worker_runbook.md`](gpu_worker_runbook.md), and [`worker_provision.md`](worker_provision.md).

Git clones below are **lab-only**. Production workers have no git checkout.

## Directory layout

Development bootstrap (git clones):

```
/work/goliath/
  repos/MethylPipeline/
  repos/MethylExtractor/
  venv/
  env/
    worker.env
    parabricks.env
    workflow_versions.json
  data/
  runs/
```

Production release layout (no git on workers):

```
/work/goliath/
  current -> releases/<ver>/
  releases/<ver>/manifest.json, wheels/, runtime-bundle/
  venv-aarch64/  venv-amd64/
  methyl-extractor-aarch64/  methyl-extractor-amd64/
  docker/          # shared Docker data-root (Parabricks image layers)
  env/
  data/  runs/
```

## Bootstrap a new node (lab / git clone only)

Prefer [`provision_worker_node.sh`](../../scripts/provision_worker_node.sh) in production. This git-clone path is for development hosts:

```bash
export METHYL_PIPELINE_URL=<git-url>   # optional if seeding from local checkout
export METHYL_EXTRACTOR_URL=<git-url>
export WORKER_API_BASE=https://gateway.example.com/v1

sudo bash /work/goliath/repos/MethylPipeline/scripts/bootstrap_goliath.sh \
  --root /work/goliath \
  --system-deps \
  --gpu
```

## Bootstrap from a production release

After CI publishes to `/work/goliath/releases/<ver>/`:

```bash
export WORKER_API_BASE=https://gateway.example.com/v1

bash scripts/bootstrap_goliath.sh \
  --root /work/goliath \
  --release-dir /work/goliath/releases/2026.6.1 \
  --arch aarch64 \
  --promote-release \
  --system-deps \
  --skip-parabricks-pull   # if promote already pulled Parabricks to shared docker/
```

Or promote and install separately: [`promote_release.sh`](../../scripts/promote_release.sh), [`install_release.sh`](../../scripts/install_release.sh).

Or from a fresh machine before clones exist:

```bash
git clone <MethylPipeline-url> /tmp/MethylPipeline
sudo /tmp/MethylPipeline/scripts/bootstrap_goliath.sh \
  --pipeline-url <url> \
  --extractor-url <url> \
  --system-deps --gpu
```

## GPU / Docker / Parabricks only

Shared Docker data-root (production — all GPU VMs point at `/work/goliath/docker`):

```bash
bash scripts/setup_gpu_node.sh \
  --docker-data-root /work/goliath/docker \
  --env-dir /work/goliath/env
```

Pull Parabricks once during release promote, or on a single admin node:

```bash
bash scripts/setup_gpu_node.sh --pull-parabricks --env-dir /work/goliath/env
```

## Python packages (development / editable)

All worker-capable packages install from [`scripts/packages.list`](../../scripts/packages.list) via [`scripts/install_packages.sh`](../../scripts/install_packages.sh) (includes `workers/`).

```bash
source /work/goliath/venv/bin/activate
./scripts/install_all.sh --pipeline-reqs --gpu-reqs --skip-marp
```

Production installs use [`scripts/install_release.sh`](../../scripts/install_release.sh) from release wheels (non-editable).

## Environment contract

| Variable | Purpose |
|----------|---------|
| `WORKER_ID`, `WORKER_TOKEN` | PostgreSQL worker auth |
| `WORKER_API_BASE` | REST gateway HTTPS URL (`/v1` suffix) |
| `WORKER_CAPABILITY` | Optional task filter (omit for omnibus dev worker) |
| `METHYL_PARABRICKS_IMAGE` | Clara Parabricks image |
| `METHYL_PARABRICKS_GPU_FLAGS` | Default `--gpus all` |
| `METHYL_EXTRACTOR_BIN` | Path to native MethylExtractor binary |
| `HDF5_PLUGIN_PATH` | Zstd HDF5 plugin from MethylExtractor build |
| `WORKER_STUB_EXTERNAL=1` | Stub download/Parabricks/extract/delete (smoke tests only) |

Source env before running workers (interactive shells expand `$PATH`; systemd does not):

```bash
set -a
source /work/goliath/env/worker.env
source /work/goliath/env/parabricks.env
set +a
```

`worker.env` contains a **literal** `PATH` (venv prepended to the bootstrap host's PATH). Do not use `PATH=...:$PATH` in env files loaded by systemd `EnvironmentFile=` — variable expansion is not performed.

## Enroll worker (production)

Canonical path: [production-platform.md](production-platform.md) Phase 4.

1. Portal preregisters this VM’s **public IP** (`portal.sp_upsert_worker_enrollment`).
2. Worker is Azure Arc **Connected** (`verify_arc_prereqs.sh`).
3. Enroll through the gateway (no SQL on the node):

```bash
export WORKER_API_BASE=https://<gateway-fqdn>/v1
methyl-worker enroll \
  --api-base "$WORKER_API_BASE" \
  --cluster gpu-west \
  --key "$(hostname -s)"
```

`register_worker.sh` without DB env performs the same gateway enroll when `WORKER_API_BASE` is set.

**Dev/bootstrap only** (trusted host): `register_worker.sh` with `BACKEND_DB` + `AZURE_SQL_*` or `POSTGRES_*`. Do not put those credentials on production GPU VMs.

## Gateway connectivity tiers

| Tier | Network | `WORKER_API_BASE` | Worker auth |
|------|---------|-------------------|-------------|
| A | Azure VNet / internal LB | `https://gateway-internal/v1` | `WORKER_ID` + `WORKER_TOKEN` (+ Arc header) |
| B | Site VPN | `https://gateway/v1` (VPN reachable) | same |
| C | Public NSG | `https://gateway/v1` (HTTPS only) | same + cluster `allowed_source_cidrs` |

The gateway is **worker-only** HTTP. Study start and catalog/workflow deploy use **portal SQL** / **direct DB** scripts — not gateway admin routes. See [`production_runbook.md`](production_runbook.md#gateway-security-mixed-worker-topology).


## systemd

Templates in [`deploy/systemd/`](../../deploy/systemd/):

```bash
sudo cp deploy/systemd/methyl-worker.service /etc/systemd/system/
sudo cp deploy/systemd/methyl-worker@.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now methyl-worker.service          # omnibus
# or
sudo systemctl enable --now methyl-worker@methyl-qc.service  # per capability
```

Adjust paths in unit files if `GOLIATH_ROOT` differs from `/work/goliath`.

Production workers use **arch-specific venvs** (`venv-aarch64` or `venv-amd64`). Update `Environment=PATH=` and `ExecStart=` in the unit file to match the node architecture, for example:

```
Environment=PATH=/work/goliath/venv-aarch64/bin:...
ExecStart=/work/goliath/venv-aarch64/bin/methyl-worker --api-base ${WORKER_API_BASE}
```

## Verification

```bash
bash scripts/verify_e2e_node.sh
```

## Control plane (privileged host, not the GPU)

Follow [production-platform.md](production-platform.md) Phases 2–3:

1. [`workflow_engine/sql_mssql/deploy_azure.sh`](../../workflow_engine/sql_mssql/deploy_azure.sh) or [`sql_pg/deploy_azure.sh`](../../workflow_engine/sql_pg/deploy_azure.sh) (twins)
2. `bash scripts/bootstrap_distributed_workers.sh --skip-schema` — Python populate
3. `scripts/provision_gateway_node.sh` — gateway on local disk, no `/work`

## Staged lifecycle smoke

With gateway running and an omnibus worker (`WORKER_STUB_EXTERNAL=1`):

```bash
bash scripts/smoke_study_lifecycle.sh --api-base "$WORKER_API_BASE"
```

Production studies: [`workflow_engine/docs/portal_study_lifecycle.md`](../../workflow_engine/docs/portal_study_lifecycle.md).
