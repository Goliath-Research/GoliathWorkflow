# Logging and observability

> **Canonical** reference for where logs and timing live today. Centralized metrics are **not** implemented.

## Local (in-process) runs

| Source | Content |
|--------|---------|
| `methyl-workflow-run -v` | Graph scheduling, template resolution |
| Package CLIs | stderr + optional `--log-file` per tool |
| Action manifests | Written under run output dirs when workers emulate locally |

## Distributed workers

| Source | Content |
|--------|---------|
| `journalctl -u methyl-worker` | Claim/submit loop, action stderr |
| `output_json` | `result_code`, `manifest`, `timing_ms`, typed outputs |
| Gateway access | Uvicorn access log (if enabled); no built-in log shipper |

Worker protocol: [`workers/WORKER_PROTOCOL.md`](../../workers/WORKER_PROTOCOL.md).

## Database status

| Table | Operator view |
|-------|---------------|
| `wf.workflow_instance` | Instance `status`, `context_json` |
| `wf.node_execution` | Per-node `status`, `lease_owner`, `result_code` |
| `wf.worker` | Registration, `last_heartbeat_at` |

Poll via SQL or portal; gateway does not expose admin read APIs.

## JSONL timelines

Monte Carlo and validation actions may append structured lines under project output trees (`action_run_log.jsonl` patterns — see typed observability plan). Fields typically include `action_name`, `node_execution_id`, `duration_ms`, `result_code`.

## Correlation

Propagate `workflow_instance_id` and `node_execution_id` from claim payload into worker logs. Gateway does not inject trace headers today.

## Retention

- **VM logs:** systemd journal rotation (operator policy)
- **DB rows:** no automatic purge documented
- **`/work` artifacts:** study retention policy

## Gaps (honest)

| Gap | Status |
|-----|--------|
| Centralized metrics (Prometheus/Datadog) | Not shipped |
| Lease expiry alerts | Not shipped |
| Unified trace ID across gateway + worker + DB | Partial (IDs in payloads only) |
| Log aggregation from multiple workers | Operator responsibility |

## Related

- [Traceability and provenance](traceability-provenance.md)
- [Troubleshooting ch.11](../usage/11-troubleshooting-and-recovery.qmd)
- [Distributed runtime](../architecture/distributed-runtime.md)
