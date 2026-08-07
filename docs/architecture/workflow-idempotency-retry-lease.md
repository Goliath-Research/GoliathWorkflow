# Workflow idempotency, retry, and leases

> **Canonical** operational contract for the database workflow engine.  
> Documents **implemented** behavior and **known gaps**.

## Atomic claim

Workers call `POST /v1/workers/claim`. The database procedure assigns at most one runnable node per successful claim using lease columns on `wf.node_execution`.

- **Duplicate workers:** Second claimant receives empty/no work for that node while lease held.
- **Same worker:** Poll loop; no parallel claim of same node.

## Submit and idempotency

`POST /v1/workers/submit` records `output_json`, `result_code`, and transitions node status.

| Scenario | Behavior |
|----------|----------|
| First successful submit | Node → terminal success/fail per `result_code` |
| Duplicate submit (same node, completed) | Gateway/DB rejects or no-ops (dialect-specific); treat as operator error if seen |
| `forceRerun` (instance/program) | New node execution row or reset — see instance configure path |

## Manifest and CAAS reuse

Hyperparameter and content-addressed actions may skip work when `content_key` matches stored CAAS entries (`hyperparameter-result-versioning` plan). This is **action-level** idempotency, not workflow-level.

## Action-level retries

Individual CLIs may retry internally (e.g. network). The engine does **not** automatically requeue failed nodes.

## Leases

| Aspect | Current behavior |
|--------|------------------|
| Lease set on claim | Yes (`wf.task_lease.lease_expires_at_utc`) |
| Worker heartbeat renew | `POST /v1/workers/tasks/{id}/heartbeat` → `wf.sp_worker_heartbeat` |
| **Lease expiry requeue** | **Automatic:** claim path + systemd timer call `wf.sp_reclaim_expired_leases`; portal/ops: `portal.sp_reclaim_expired_leases` / `methyl-reclaim-leases` |
| `attempt_no` | Incremented on reclaim / manual READY reset |

Healthy long Align jobs stay safe while the worker heartbeats (lease keeps extending). After a worker crash or `systemctl restart` mid-task, reclaim returns the node to `READY` once the lease expires (60s grace).

### Automatic reclaim

1. **On claim** — `wf.sp_worker_request_task` quietly runs reclaim when any expired/missing lease exists (before picking work).
2. **Timer** — on the gateway host, `methyl-reclaim-leases.timer` runs every 2 minutes:

```bash
sudo bash scripts/install_reclaim_leases_timer.sh
# or via install_gateway_systemd.sh (installs timer too)
systemctl status methyl-reclaim-leases.timer
journalctl -u methyl-reclaim-leases.service -n 50
```

CLI (same DB env as gateway): `methyl-reclaim-leases --grace-seconds 60`

## `forceRerun` and replanning

Operators may create a new instance or use portal/admin paths to reset work. `methyl-study-start plan-iterations` can persist new `iterations[]` into `context_json` without recompiling the graph.

## Recovery (operator)

See [Usage ch.11 — Troubleshooting and recovery](../usage/11-troubleshooting-and-recovery.qmd):

1. Find stuck `RUNNING` rows with expired/missing leases (query below or portal task list).
2. Verify worker health (`systemctl status methyl-worker`, journal).
3. Reclaim:

```sql
-- Azure SQL
EXEC portal.sp_reclaim_expired_leases @grace_seconds = 60;
EXEC portal.sp_reclaim_expired_leases
  @workflow_instance_id = 59,
  @grace_seconds = 60;

-- PostgreSQL
SELECT * FROM portal.sp_reclaim_expired_leases(NULL, 60);
SELECT * FROM portal.sp_reclaim_expired_leases(59, 60);
```

4. Prefer a new instance for science reruns when `actionConfig` changed (do not reclaim to “fix” bad config).

## Related

- [Workflow engine implementation](../implementation/workflow-engine.md)
- [WORKER_PROTOCOL.md](../../workers/WORKER_PROTOCOL.md)
- [Logging and observability](../reference/logging-observability.md)
