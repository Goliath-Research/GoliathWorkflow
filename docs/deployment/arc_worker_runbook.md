# Azure Arc worker onboarding runbook

Operational guide for registering GPU worker VMs with **Microsoft Arc** before they join a MethylPipeline cluster. Arc provides inventory, policy compliance, Defender EDR, and Sentinel telemetry — it **does not** replace gateway TLS or `worker_token` auth.

Related: [worker_provision.md](worker_provision.md), [production_runbook.md](production_runbook.md).

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| Outbound HTTPS (443) | Arc + Azure Monitor endpoints; use Private Link Scope when egress is restricted |
| Azure permissions | `Microsoft.HybridCompute/machines/write`, resource group contributor for onboarding |
| VM admin (sudo) | Arc agent install; optional AMA extension |
| Tags policy | `cluster_key`, `environment`, `phi=true`, `hipaa=true` |

## Phase A1 — Inventory and policy

### 1. Private Link Scope (recommended)

1. Create an **Azure Arc Private Link Scope** in the gateway subscription.
2. Associate worker VNets / subnets that host GPU nodes.
3. Allowlist only Arc and Monitor FQDNs on worker egress NSGs.

### 2. Install and connect Arc agent

On each worker VM (or via [`scripts/provision_worker_node.sh`](../../scripts/provision_worker_node.sh) `--arc-onboard`):

```bash
sudo bash scripts/install_arc_agent.sh \
  --subscription-id "$AZ_SUBSCRIPTION_ID" \
  --resource-group "$AZ_RESOURCE_GROUP" \
  --tenant-id "$AZURE_TENANT_ID" \
  --tags "cluster_key=gpu-west,environment=prod,phi=true,hipaa=true" \
  --with-ama
```

This writes `/etc/methyl/arc.env` with `ARC_RESOURCE_ID` for registration.

Verify:

```bash
bash scripts/verify_arc_prereqs.sh
# or: az connectedmachine show -n "$(hostname -s)" -g "$AZ_RESOURCE_GROUP" --query "status"
```

Status must be **Connected** before production registration.

### 3. Azure Policy Guest Configuration

Apply an initiative on the Arc resource group or subscription:

- Linux CIS benchmark (Guest Configuration)
- Require **Azure Monitor Agent** (AMA) on Arc machines
- Block password SSH / require key-only admin access (admin accounts ≠ worker service identity)

Assign at scope that includes all worker resource groups (Azure native + AWS/Lambda/Nebius Arc machines).

### 4. Tagging

Ensure every Arc machine carries:

| Tag | Example |
|-----|---------|
| `cluster_key` | `gpu-west` (matches `wf.cluster.cluster_key`) |
| `environment` | `prod` |
| `phi` | `true` |
| `hipaa` | `true` |

## Phase A2 — Bind Arc to `wf.cluster`

Deploy SQL (if not already applied):

- Azure SQL: [`workflow_engine/sql_mssql/wf_cluster_security_columns.sql`](../../workflow_engine/sql_mssql/wf_cluster_security_columns.sql)
- PostgreSQL: [`workflow_engine/sql_pg/wf_cluster_security_columns.sql`](../../workflow_engine/sql_pg/wf_cluster_security_columns.sql)

Register worker (auto-loads `/etc/methyl/arc.env` when present):

```bash
bash scripts/register_worker.sh \
  --cluster gpu-west \
  --key "$(hostname -s)" \
  --require-arc \
  --env-file /work/epimethyl/env/worker.env
```

Manual override:

```bash
bash scripts/register_worker.sh \
  --arc-resource-id "/subscriptions/.../Microsoft.HybridCompute/machines/gpu-west-01" \
  ...
```

### Optional gateway attestation (A2b)

On the gateway VM, enable header check against `wf.cluster.arc_resource_id`:

```bash
GATEWAY_REQUIRE_ARC_ATTEST=1
```

Workers should send `X-Arc-Resource-Id: /subscriptions/.../machines/...` on every `POST /v1/workers/*` request (the Python client sets this from `/etc/methyl/arc.env`).

## Production posture (storage + Arc)

| Control | Requirement |
|---------|-------------|
| Gateway Arc attest | Set `GATEWAY_REQUIRE_ARC_ATTEST=1` so only Arc-enrolled VMs may poll/claim |
| Worker SQL | **Forbidden** — OpenAPI/gateway only |
| Storage SoT | Database (`cfg.*`) via portal admins; workers receive secrets only in claim `input_json` |
| Secret logging | Do **not** log `input_json.credentials` / AccessKeys on gateway or workers |
| Node-local cache | `/var/lib/methyl/storage-credentials/` + `/etc/methyl/storage-credential.key` (mode 600); never under `/work` |

## Phase A3 — Defender and Sentinel

See [production_runbook.md — Arc compliance and incident response](production_runbook.md#arc-compliance-and-incident-response).

## Permission matrix

| Actor | Arc onboard | Methyl bundle | Register worker | systemd |
|-------|-------------|---------------|-----------------|---------|
| Platform admin | yes | — | — | — |
| Cluster operator | yes | yes | yes (DB env) | yes |
| Worker service account | no | no | no | runs as `methyl` user |

## Troubleshooting

| Symptom | Action |
|---------|--------|
| `verify_arc_prereqs.sh` fails | Check outbound 443, proxy (`--proxy-url`), SP creds |
| Arc **Disconnected** | Re-run `azcmagent connect` or `install_arc_agent.sh` |
| Registration rejects `--require-arc` | Confirm `/etc/methyl/arc.env` exists and `ARC_RESOURCE_ID` is set |
| Gateway 403 on worker poll | Check `GATEWAY_REQUIRE_ARC_ATTEST` header matches DB row |
