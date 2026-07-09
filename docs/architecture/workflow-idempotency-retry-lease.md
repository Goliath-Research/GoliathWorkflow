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
| Lease set on claim | Yes (`lease_owner`, `lease_expires_at`) |
| Worker heartbeat renew | Depends on worker loop; no separate lease-renew endpoint |
| **Lease expiry requeue** | **Not implemented** — expired leases may leave nodes stuck until operator intervention |
| `attempt_no` | Always `1` today — no multi-attempt retry counter |

## `forceRerun` and replanning

Operators may create a new instance or use portal/admin paths to reset work. `methyl-study-start plan-iterations` can persist new `iterations[]` into `context_json` without recompiling the graph.

## Recovery (operator)

See [Usage ch.11 — Troubleshooting and recovery](../usage/11-troubleshooting-and-recovery.qmd):

1. Identify stuck `lease_owner` / expired lease in `wf.node_execution`
2. Verify worker health (`register_worker.sh`, systemd)
3. Safe manual SQL or portal procedure to release lease **only** per runbook (dialect-specific)
4. Prefer new instance for science reruns when config changed

## Related

- [Workflow engine implementation](../implementation/workflow-engine.md)
- [WORKER_PROTOCOL.md](../../workers/WORKER_PROTOCOL.md)
- [Logging and observability](../reference/logging-observability.md)
