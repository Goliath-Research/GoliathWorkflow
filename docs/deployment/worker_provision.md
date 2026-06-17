# GPU worker provisioning playbook

Step-by-step for joining a **new GPU VM** to an existing production release on shared storage.

Related: [production_release.md](production_release.md), [gpu_worker_runbook.md](gpu_worker_runbook.md).

## Assumptions

- Release already promoted: `/work/epimethyl/current` → valid `manifest.json`
- Shared artifacts present: `venv-<arch>/`, `methyl-extractor-<arch>/`, `docker/` (if Parabricks pre-pulled)
- Gateway and PostgreSQL available for worker registration

## 1. Mount shared storage

```bash
ls /work/epimethyl/current/manifest.json
```

## 2. NVIDIA driver

```bash
nvidia-smi
```

Install or upgrade driver per [gpu_worker_runbook.md](gpu_worker_runbook.md) before continuing.

## 3. Host system dependencies (once per VM)

```bash
RUNTIME="$(readlink -f /work/epimethyl/current/runtime-bundle)"
bash "$RUNTIME/scripts/setup_host.sh" \
  --system-deps --gpu \
  --venv /work/epimethyl/venv-$(source "$RUNTIME/scripts/detect_platform.sh" && platform_arch_key) \
  --no-venv
```

Use `--no-venv` if venv already exists on shared storage from promote. Omit `--no-venv` only on first environment bootstrap.

## 4. Docker + shared data-root (once per VM)

```bash
RUNTIME="$(readlink -f /work/epimethyl/current/runtime-bundle)"
bash "$RUNTIME/scripts/setup_gpu_node.sh" \
  --docker-data-root /work/epimethyl/docker \
  --env-dir /work/epimethyl/env
```

Add user to docker group if prompted: `sudo usermod -aG docker "$USER"`.

## 5. Environment

If promote already wrote `worker.env`, skip to step 6. Otherwise:

```bash
bash /work/epimethyl/current/runtime-bundle/scripts/write_worker_env.sh \
  --root /work/epimethyl \
  --manifest /work/epimethyl/current/manifest.json \
  --arch aarch64
```

Set `WORKER_API_BASE` in `/work/epimethyl/env/worker.env` if not present.

## 6. Register worker (once per VM)

```bash
export PGHOST=… PGUSER=… PGPASSWORD=… PGDATABASE=…
bash /work/epimethyl/current/runtime-bundle/scripts/register_worker.sh \
  --key "$(hostname -s)" \
  --env-file /work/epimethyl/env/worker.env
```

## 7. Verify

```bash
set -a
source /work/epimethyl/env/worker.env
source /work/epimethyl/env/parabricks.env
set +a
bash /work/epimethyl/current/runtime-bundle/scripts/verify_e2e_node.sh
```

## 8. systemd

Copy units from runtime bundle and set arch-specific venv in `ExecStart`:

```bash
ARCH=$(source /work/epimethyl/current/runtime-bundle/scripts/detect_platform.sh && platform_arch_key "$(uname -m)")
sudo cp /work/epimethyl/current/runtime-bundle/deploy/systemd/methyl-worker.service /etc/systemd/system/
sudo sed -i "s|venv-aarch64|venv-${ARCH}|g" /etc/systemd/system/methyl-worker.service
sudo systemctl daemon-reload
sudo systemctl enable --now methyl-worker.service
sudo systemctl status methyl-worker.service
```

## Second and subsequent GPU VMs

Skip promote and venv install. Repeat steps **3–8** only (system deps, docker data-root config, register, verify, systemd).

## Omnibus vs capability workers

| Mode | register_worker | systemd unit |
|------|-----------------|--------------|
| All capabilities | no `--capability` | `methyl-worker.service` |
| Single capability | `--capability methyl-qc` | `methyl-worker@methyl-qc.service` |
