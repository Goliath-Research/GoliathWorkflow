# Multi-cloud infrastructure (Terraform)

> **Status:** Scaffold deployed (2026-07-01). `terraform apply` is operator-only.

## Architecture

Azure hosts the **control plane** (gateway, Azure SQL with private endpoint, Key Vault,
Entra app registrations, Defender/Sentinel). GPU worker fleets run as **systemd VMs** on
Nebius and Lambda Cloud, onboarded via **Azure Arc** for cross-cloud governance.

```mermaid
flowchart TB
  subgraph azure [Azure control plane]
    GW[gateway TLS + NSG]
    SQL[(Azure SQL private endpoint)]
    KV[Key Vault]
    SENT[Defender / Sentinel via Arc]
  end
  subgraph nebius [Nebius GPU VMs]
    NW[systemd methyl-worker]
  end
  subgraph lambda [Lambda Cloud GPU VMs]
    LW[systemd methyl-worker]
  end
  NW -->|egress 443 + token + X-Arc-Resource-Id| GW
  LW --> GW
  GW --> SQL
  NW -.Arc agent.-> SENT
  LW -.Arc agent.-> SENT
  NW -.boot token fetch.-> KV
  LW -.boot token fetch.-> KV
```

Repository layout: [`deploy/terraform/README.md`](../../deploy/terraform/README.md).

## Per-cloud notes

| Cloud | Model | Provider | Status |
|-------|-------|----------|--------|
| **Azure** | Control plane + optional Azure GPU workers | `hashicorp/azurerm` (official) | Scaffold module |
| **Nebius** | GPU VMs, egress-only network | `nebius/nebius` (official) | Scaffold module |
| **Lambda Cloud** | GPU VMs | `lambdaops/lambda` **community** | Scaffold + supply-chain pin |
| **CoreWeave** | CKS Kubernetes only | k8s manifests (not Terraform VMs) | Design follow-on |

### Lambda provider risk

The Lambda Terraform provider is **community-maintained** (no vendor SLA). Mitigations:

- Pin exact version in `deploy/terraform/versions.tf`
- Review provider changelog on upgrade
- Prefer Nebius official provider for production GPU pools when both are available

### Nebius

Use official `nebius/nebius` provider for GPU instances, encrypted disks, key-only SSH,
and `user_data` from `worker-common` cloud-init. API keys live in Key Vault — never in
Terraform state (use write-only/ephemeral variables where supported).

## Secure state and secrets

| Asset | Storage |
|-------|---------|
| Terraform state | Azure Storage backend, encrypted, RBAC, versioning, no public access |
| `WORKER_TOKEN` | Key Vault secret; fetched at VM boot via managed identity |
| Cloud API keys (Nebius, Lambda) | Key Vault / CI secret store |
| Worker credentials on VM | `/etc/methyl/worker-token` mode 600 |

Terraform modules **do not** embed worker tokens in state. `worker-common` cloud-init
runs `register_worker.py --auto-detect` after bundle checksum verification.

## Operator workflow

1. **Control plane** — `cd deploy/terraform/envs/<env> && terraform init && terraform apply`
   (requires Azure credentials).
2. **Populate Key Vault** — worker registration tokens, Nebius SA key, Lambda API key.
3. **Worker fleet** — apply `worker-nebius` or `worker-lambda` module with `worker-common`
   `cloud_init` output.
4. **Gateway NSG** — set `gateway_allowed_worker_cidrs` to each fleet egress CIDR
   (feeds `wf.cluster.allowed_source_cidrs` at registration).
5. **Verify** — `scripts/verify_arc_prereqs.sh`, `methyl-worker --authenticate`, poll test.

## Capability tie-in

Cloud-init invokes capability detection before registration:

1. `resolve_worker_capabilities()` probes GPU, Parabricks, extractor, CLIs.
2. `register_worker.py` writes the set to `wf.worker.capabilities`.
3. `sp_worker_request_task` only returns matching tasks.
4. systemd installs `methyl-worker@<capability>.service` per detected cap (or omnibus).

## CoreWeave follow-on (design only)

CoreWeave **CKS** is Kubernetes-native — not a VM+bash model.

| Component | Approach |
|-----------|----------|
| Cluster | Terraform VPC + CKS cluster + GPU node pool |
| Worker | Container image from epimethyl release + `methyl-worker` entrypoint |
| Token | Kubernetes Secret mounted read-only; sync from Key Vault via CSI |
| Governance | Arc-enabled Kubernetes extension |
| Deploy | Helm chart (`charts/methyl-worker`) — **not yet in repo** |

Steps to implement later:

1. Publish `methyl-worker` container image (CUDA base + epimethyl venv).
2. Helm chart: Deployment, ServiceAccount, Secret, GPU `nodeSelector`, liveness via `/workers/authenticate`.
3. Terraform module `worker-coreweave-cks` wrapping cluster + Helm release.

Until then, Nebius and Lambda VM fleets are the supported multi-cloud GPU path.

## References

- [Worker transport decision](../architecture/worker-transport-decision.md)
- [Worker security review](../architecture/worker-security-review.md)
- [Worker provisioning](worker_provision.md)
- [Distributed workers bootstrap](distributed-workers-bootstrap.md)
