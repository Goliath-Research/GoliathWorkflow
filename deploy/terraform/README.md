# Multi-cloud Terraform for MethylPipeline worker fleets and Azure control plane.

## Layout

- **`modules/control-plane-azure`**: Gateway, Azure SQL, Key Vault, NSGs
- **`modules/worker-common`**: Cloud-init (scripts seed → join prepare; Arc/enroll staged)
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
2. Store Nebius/Lambda API keys and per-cluster CIDRs in Key Vault (provider creds only).
3. Promote GoliathOmics release + Parabricks to QNAP `/work` (cluster once).
4. Deploy `worker-nebius` or `worker-lambda` with `worker-common` cloud-init
   (default `--prepare-only`; seed tarball → `/opt/methyl`).
5. Portal-preregister IP → approve Arc → `provision_worker_node.sh --finish-enroll`
   (token from gateway enroll, never from TF state). See
   [lambda_worker_join.md](../../docs/deployment/lambda_worker_join.md).

## Security

- Remote state: Azure Storage, encrypted, RBAC, versioning, public access disabled.
- Workers: egress-only 443 to gateway; SSH key-only; disk encryption where supported.
- No secrets in `.tfvars` committed to git — use Key Vault references or `-var-file` locally.

See [docs/deployment/multicloud-iac.md](../../docs/deployment/multicloud-iac.md).
