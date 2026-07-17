# GPU worker provisioning playbook

Step-by-step for joining a **new GPU VM** to an existing production release on shared storage, with **Azure Arc** governance before cluster enrollment.

**Canonical production story:** [production-platform.md](production-platform.md) (portal IP prereg → Arc → gateway enroll). This page is the per-VM detail.

Related: [production_release.md](production_release.md), [gpu_worker_runbook.md](gpu_worker_runbook.md), [arc_worker_runbook.md](arc_worker_runbook.md).

## Assumptions

- Release already promoted: `/work/epimethyl/current` → valid `manifest.json`
- Shared artifacts present: `venv-<arch>/`, `methyl-extractor-<arch>/`, `docker/` (if Parabricks pre-pulled)
- Gateway HTTPS up (`WORKER_API_BASE`); portal has preregistered this VM’s **public IP**
- Operator has sudo + Azure permissions for Arc onboarding (company tenant/subscription)

## Orchestrated path (recommended)

Single entry point for Arc → bundle → register → systemd:

```bash
export WORKER_API_BASE=https://gateway.example.com/v1
export AZ_SUBSCRIPTION_ID=... AZ_RESOURCE_GROUP=... AZURE_TENANT_ID=...

sudo bash /work/epimethyl/current/runtime-bundle/scripts/provision_worker_node.sh \
  --gpu \
  --arc-onboard \
  --require-arc \
  --register-worker \
  --enable-systemd \
  --cluster gpu-west
```

Second and subsequent VMs on the same cluster (shared venv already on `/work`):

```bash
sudo bash scripts/provision_worker_node.sh \
  --gpu --require-arc --skip-promote \
  --register-worker --enable-systemd --cluster gpu-west
```

## Manual steps (reference)

### 0. Azure Arc (production)

```bash
sudo bash scripts/install_arc_agent.sh \
  --subscription-id "$AZ_SUBSCRIPTION_ID" \
  --resource-group "$AZ_RESOURCE_GROUP" \
  --tenant-id "$AZURE_TENANT_ID" \
  --tags "cluster_key=gpu-west,environment=prod,phi=true,hipaa=true"
bash scripts/verify_arc_prereqs.sh
```

See [arc_worker_runbook.md](arc_worker_runbook.md) for Private Link Scope and Guest Configuration policies.

### 1. Mount shared storage

```bash
ls /work/epimethyl/current/manifest.json
```

### 2. NVIDIA driver

```bash
nvidia-smi
```

Install or upgrade driver per [gpu_worker_runbook.md](gpu_worker_runbook.md) before continuing.

### 3. Host system dependencies (once per VM)

```bash
RUNTIME="$(readlink -f /work/epimethyl/current/runtime-bundle)"
bash "$RUNTIME/scripts/setup_host.sh" \
  --system-deps --gpu \
  --venv /work/epimethyl/venv-$(source "$RUNTIME/scripts/detect_platform.sh" && platform_arch_key) \
  --no-venv
```

Use `--no-venv` if venv already exists on shared storage from promote. Omit `--no-venv` only on first environment bootstrap.

This installs host tools including **bedtools** (MethylMapper), **samtools** (alignment QC flagstat on GPU workers), and **fastp** (SamplePrep trim remediation).

### 4. Docker + shared data-root (once per VM)

```bash
RUNTIME="$(readlink -f /work/epimethyl/current/runtime-bundle)"
bash "$RUNTIME/scripts/setup_gpu_node.sh" \
  --docker-data-root /work/epimethyl/docker \
  --env-dir /work/epimethyl/env
```

Add user to docker group if prompted: `sudo usermod -aG docker "$USER"`.

### 5. Bootstrap release bundle

```bash
bash /work/epimethyl/current/runtime-bundle/scripts/bootstrap_epimethyl.sh \
  --root /work/epimethyl \
  --require-arc
```

`bootstrap_epimethyl.sh` defaults `WORKER_API_BASE` to HTTPS. Use `--skip-arc-check` only in dev/lab.

### 6. Environment

If promote already wrote `worker.env`, confirm `WORKER_API_BASE=https://<gateway-fqdn>/v1`. Otherwise:

```bash
bash /work/epimethyl/current/runtime-bundle/scripts/write_worker_env.sh \
  --root /work/epimethyl \
  --manifest /work/epimethyl/current/manifest.json \
  --arch aarch64
```

### 7. Enroll worker via gateway (once per VM)

**Production:** portal must already have this VM’s public IP (`portal.sp_upsert_worker_enrollment`). No SQL credentials on the worker.

```bash
export WORKER_API_BASE=https://<gateway-fqdn>/v1
bash /work/epimethyl/current/runtime-bundle/scripts/verify_arc_prereqs.sh
methyl-worker enroll \
  --api-base "$WORKER_API_BASE" \
  --cluster gpu-west \
  --key "$(hostname -s)"
# writes /etc/methyl/worker-token (mode 600)
```

`register_worker.sh` without `AZURE_SQL_*` / `POSTGRES_*` also enrolls through the gateway when `WORKER_API_BASE` is set. It reads `ARC_RESOURCE_ID` from `/etc/methyl/arc.env` when present.

**Dev/bootstrap only** (trusted host with DB env — never on production GPU VMs):

```bash
export BACKEND_DB=mssql   # or postgres + POSTGRES_*
# AZURE_SQL_* …
bash /work/epimethyl/current/runtime-bundle/scripts/register_worker.sh \
  --cluster gpu-west \
  --key "$(hostname -s)" \
  --require-arc \
  --env-file /work/epimethyl/env/worker.env
```

### 8. Verify

```bash
set -a
source /work/epimethyl/env/worker.env
source /work/epimethyl/env/parabricks.env
set +a
bash /work/epimethyl/current/runtime-bundle/scripts/verify_e2e_node.sh
```

### 9. systemd

```bash
sudo bash /work/epimethyl/current/runtime-bundle/scripts/install_worker_systemd.sh \
  --root /work/epimethyl
```

Or manually copy units and set arch-specific venv:

```bash
ARCH=$(source /work/epimethyl/current/runtime-bundle/scripts/detect_platform.sh && platform_arch_key "$(uname -m)")
sudo cp /work/epimethyl/current/runtime-bundle/deploy/systemd/methyl-worker.service /etc/systemd/system/
sudo sed -i "s|venv-aarch64|venv-${ARCH}|g" /etc/systemd/system/methyl-worker.service
sudo systemctl daemon-reload
sudo systemctl enable --now methyl-worker.service
sudo systemctl status methyl-worker.service
```

`methyl-worker.service` uses `After=azure-arc-agent.service` when Arc is installed.

## Second and subsequent GPU VMs

Skip promote and venv install. Repeat Arc verify (if new VM) and steps **3–9** only.

## Omnibus vs capability workers

| Mode | Enroll / register | systemd unit |
|------|-------------------|--------------|
| All capabilities | no `--capability` | `methyl-worker.service` |
| Single capability | `--capability methyl-qc` (dev DB path) or matching key | `methyl-worker@methyl-qc.service` via `install_worker_systemd.sh --capability methyl-qc` |
