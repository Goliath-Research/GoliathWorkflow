# GPU worker node deployment

Host-native workers on shared storage under `/work/epimethyl`. Docker is used **only** for Parabricks alignment.

**Production releases** (wheels, binary tarballs, shared Docker store): see [`production_release.md`](production_release.md), [`gpu_worker_runbook.md`](gpu_worker_runbook.md), and [`worker_provision.md`](worker_provision.md).

## Directory layout

Development bootstrap (git clones):

```
/work/epimethyl/
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
/work/epimethyl/
  current -> releases/<ver>/
  releases/<ver>/manifest.json, wheels/, runtime-bundle/
  venv-aarch64/  venv-amd64/
  methyl-extractor-aarch64/  methyl-extractor-amd64/
  docker/          # shared Docker data-root (Parabricks image layers)
  env/
  data/  runs/
```

## Bootstrap a new node (development)

```bash
export METHYL_PIPELINE_URL=<git-url>   # optional if seeding from local checkout
export METHYL_EXTRACTOR_URL=<git-url>
export WORKER_API_BASE=https://gateway.example.com/v1

sudo bash /work/epimethyl/repos/MethylPipeline/scripts/bootstrap_epimethyl.sh \
  --root /work/epimethyl \
  --system-deps \
  --gpu
```

## Bootstrap from a production release

After CI publishes to `/work/epimethyl/releases/<ver>/`:

```bash
export WORKER_API_BASE=https://gateway.example.com/v1

bash scripts/bootstrap_epimethyl.sh \
  --root /work/epimethyl \
  --release-dir /work/epimethyl/releases/2026.6.1 \
  --arch aarch64 \
  --promote-release \
  --system-deps \
  --skip-parabricks-pull   # if promote already pulled Parabricks to shared docker/
```

Or promote and install separately: [`promote_release.sh`](../../scripts/promote_release.sh), [`install_release.sh`](../../scripts/install_release.sh).

Or from a fresh machine before clones exist:

```bash
git clone <MethylPipeline-url> /tmp/MethylPipeline
sudo /tmp/MethylPipeline/scripts/bootstrap_epimethyl.sh \
  --pipeline-url <url> \
  --extractor-url <url> \
  --system-deps --gpu
```

## GPU / Docker / Parabricks only

Shared Docker data-root (production — all GPU VMs point at `/work/epimethyl/docker`):

```bash
bash scripts/setup_gpu_node.sh \
  --docker-data-root /work/epimethyl/docker \
  --env-dir /work/epimethyl/env
```

Pull Parabricks once during release promote, or on a single admin node:

```bash
bash scripts/setup_gpu_node.sh --pull-parabricks --env-dir /work/epimethyl/env
```

## Python packages (development / editable)

All worker-capable packages install from [`scripts/packages.list`](../../scripts/packages.list) via [`scripts/install_packages.sh`](../../scripts/install_packages.sh) (includes `workers/`).

```bash
source /work/epimethyl/venv/bin/activate
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
source /work/epimethyl/env/worker.env
source /work/epimethyl/env/parabricks.env
set +a
```

`worker.env` contains a **literal** `PATH` (venv prepended to the bootstrap host's PATH). Do not use `PATH=...:$PATH` in env files loaded by systemd `EnvironmentFile=` — variable expansion is not performed.

## Register worker

Clusters must be registered in `wf.cluster` before workers poll. Use HTTPS `WORKER_API_BASE` in production.

```bash
# Uses BACKEND_DB / gateway connection env (Azure SQL or PostgreSQL)
bash scripts/register_worker.sh --key "$(hostname -s)"

# Per-capability (production):
bash scripts/register_worker.sh --key "gpu-1-methyl-qc" --capability methyl-qc

# Tier C (public NSG): bind cluster to egress CIDR(s)
bash scripts/register_worker.sh --cluster gpu-public --allowed-cidr 203.0.113.0/24
```

Legacy PostgreSQL-only registration via `PGPASSWORD` still works when `BACKEND_DB=postgres` is set in the environment.

## Gateway connectivity tiers

| Tier | Network | `WORKER_API_BASE` | Worker auth |
|------|---------|-------------------|-------------|
| A | Azure VNet / internal LB | `https://gateway-internal/v1` | `WORKER_ID` + `WORKER_TOKEN` |
| B | Site VPN | `https://gateway/v1` (VPN reachable) | same |
| C | Public NSG | `https://gateway/v1` (HTTPS only) | same + cluster `allowed_source_cidrs` |

Operator APIs (start SamplePrep, deploy definitions) require **Entra ID JWT** at the gateway when `GATEWAY_REQUIRE_ENTRA=1`. See [`production_runbook.md`](production_runbook.md#gateway-security-mixed-worker-topology).


## systemd

Templates in [`deploy/systemd/`](../../deploy/systemd/):

```bash
sudo cp deploy/systemd/methyl-worker.service /etc/systemd/system/
sudo cp deploy/systemd/methyl-worker@.service /etc/systemd/system/
sudo cp deploy/systemd/methyl-gateway.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now methyl-worker.service          # omnibus
# or
sudo systemctl enable --now methyl-worker@methyl-qc.service  # per capability
```

Adjust paths in unit files if `EPIMETHYL_ROOT` differs from `/work/epimethyl`.

Production workers use **arch-specific venvs** (`venv-aarch64` or `venv-amd64`). Update `Environment=PATH=` and `ExecStart=` in the unit file to match the node architecture, for example:

```
Environment=PATH=/work/epimethyl/venv-aarch64/bin:...
ExecStart=/work/epimethyl/venv-aarch64/bin/methyl-worker --api-base ${WORKER_API_BASE}
```

## Verification

```bash
bash scripts/verify_e2e_node.sh
```

## Control plane (once per environment)

1. [`workflow_engine/sql_pg/deploy_azure.sh`](../../workflow_engine/sql_pg/deploy_azure.sh) (PostgreSQL) or [`workflow_engine/sql_mssql/deploy_azure.sh`](../../workflow_engine/sql_mssql/deploy_azure.sh) (Azure SQL)
2. `bash scripts/bootstrap_distributed_workers.sh --skip-schema` — seed 33 actions + deploy workflows
3. `bash scripts/deploy_workflow_definitions.sh`
4. Start gateway (`methyl-gateway` systemd on Linux) — see [`deploy/systemd/methyl-gateway.service`](../../deploy/systemd/methyl-gateway.service) and [`production_runbook.md`](production_runbook.md)

## Staged lifecycle smoke

With gateway running and an omnibus worker (`WORKER_STUB_EXTERNAL=1`):

```bash
bash scripts/smoke_study_lifecycle.sh --api-base "$WORKER_API_BASE"
```

Production studies: [`workflow_engine/docs/portal_study_lifecycle.md`](../../workflow_engine/docs/portal_study_lifecycle.md).
