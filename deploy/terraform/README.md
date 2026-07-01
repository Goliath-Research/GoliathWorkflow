# Multi-cloud Terraform for MethylPipeline worker fleets and Azure control plane.

## Layout

- **`modules/control-plane-azure`**: Gateway, Azure SQL, Key Vault, NSGs
- **`modules/worker-common`**: Cloud-init (Arc, bundle, register, systemd)
- **`modules/worker-nebius`**: Nebius GPU VMs (official `nebius/nebius` provider)
- **`modules/worker-lambda`**: Lambda Cloud VMs (community provider, pinned)
- **`envs/<name>/`**: Backend and `tfvars` configuration per environment

> [!IMPORTANT]
> Apply requires per-cloud credentials and is an operator action (not a CI automated apply).

## Prerequisites

- Terraform >= 1.5
- Azure subscription for control plane + remote state storage
- Nebius / Lambda API credentials in Key Vault or CI secret store
- `terraform login` for provider registries as needed

## Quick validate (no cloud creds)

```bash
cd deploy/terraform/envs/dev
terraform init -backend=false
terraform validate
```

## Operator workflow

1. Deploy `envs/prod` control plane (`control-plane-azure` module).
2. Store Nebius/Lambda API keys and per-cluster CIDRs in Key Vault.
3. Deploy `worker-nebius` or `worker-lambda` with `worker-common` cloud-init.
4. Workers fetch `WORKER_TOKEN` from Key Vault at boot (never in TF state).
5. `register_worker.py --auto-detect` runs in cloud-init; capabilities flow to dispatch.

## Security

- Remote state: Azure Storage, encrypted, RBAC, versioning, public access disabled.
- Workers: egress-only 443 to gateway; SSH key-only; disk encryption where supported.
- No secrets in `.tfvars` committed to git — use Key Vault references or `-var-file` locally.

See [docs/deployment/multicloud-iac.md](../../docs/deployment/multicloud-iac.md).
