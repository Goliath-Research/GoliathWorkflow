# Troubleshooting and Recovery

## Purpose

Operator recovery for **distributed** (gateway + DB + workers) and **local** (`methyl-workflow-run`) workflows.

## Failure routing

```mermaid
flowchart TB
  subgraph portal ["Company Portal"]
    editor["Schema config editor Web :8077"]
    runPrep["Start SamplePrepPipeline"]
    runDdp["Start DataDrivenPipeline"]
  end
  subgraph database ["Backend Database"]
    wfPrep["SamplePrepPipeline"]
    wfDef["DataDrivenPipeline"]
    inst["workflow_instance + context_json"]
    nexec["node_execution + scope_variable"]
  end
  subgraph mt ["Middle-Tier"]
    rest["WfEngine REST :8080"]
    engine["Engine procs T-SQL / PL/pgSQL"]
  end
  subgraph workers ["Remote Workers"]
    w0["download / Parabricks / QC / extract"]
    w1["methyl-centroid / detector"]
    w3["mapper / enricher / progression"]
  end
  storage[("Shared storage NFS / Azure Files /work/...")]

  editor --> runPrep
  runPrep --> wfPrep
  wfPrep -->|"HDF5 ready"| runDdp
  runDdp --> wfDef
  wfDef --> inst
  inst --> nexec
  rest --> engine
  engine --> nexec
  w0 --> rest
  w1 --> rest
  w3 --> rest
  w0 --> storage
  w1 --> storage
  w3 --> storage
  nexec -.->|"input paths"| storage
```

*Failure routing*


## Distributed — common problems

| Symptom | Likely cause | Recovery |
|---------|--------------|----------|
| Worker idle, nodes `READY` | Worker not registered or wrong capability | `register_worker.sh`, check `wf.worker`; restart systemd unit |
| Node `RUNNING`, stale lease | Worker crash/restart; claim only serves `READY` | Auto: claim path + `methyl-reclaim-leases.timer`. Manual: Azure SQL `EXEC portal.sp_reclaim_expired_leases …` / PostgreSQL `SELECT * FROM portal.sp_reclaim_expired_leases(…)` / CLI `methyl-reclaim-leases` ([lease doc](../architecture/workflow-idempotency-retry-lease.md)) |
| `401` on claim/submit | Token mismatch | Re-issue token via `register_worker.sh`; sync `/etc/methyl/worker-token` |
| Gateway unreachable | systemd down or wrong `WORKER_API_BASE` | `install_gateway_systemd.sh`, curl health |
| Instance `FAILED` | Negative `result_code` from action | Inspect `node_execution.output_json`; fix science/config; new instance |
| Smoke fails immediately | DB env, missing `workflow_versions.json`, no worker | `bootstrap_distributed_workers.sh --verify`; deploy workflows; start worker |

## Local / legacy — common problems

| Symptom | Likely cause | Recovery |
|---------|--------------|----------|
| `command not found: methyl-workflow-run` | `.venv` inactive | `source .venv/bin/activate`; `bash scripts/setup_host.sh --with-deps` |
| freeze fails for missing stable panel | stability not run | Re-run stability stage or set `freeze_stable_dmp_csv` in manifest paths |
| path file-not-found across hosts | path drift | `path_remap` / consistent `/work/projects/...` layout |

## Safe recovery sequence (distributed)

1. Confirm release: `bash scripts/verify_setup.sh --runtime-bundle`
2. Query instance + nodes in DB (`wf.workflow_instance`, `wf.node_execution`)
3. Check worker logs: `journalctl -u methyl-worker -f`
4. Do **not** assume automatic retry — prefer new instance when `actionConfig` changed
5. Record `workflow_instance_id` and overrides for traceability

## Safe recovery sequence (local)

1. Validate `.venv` and CLI availability
2. Confirm previous-stage artifacts exist under project output dir
3. Re-run failed stage only (`methyl-workflow-run` with scoped program node or legacy `--resume`)

## Resume examples (legacy transitional)

```bash
source .venv/bin/activate
methyl-validation --project /work/projects/prostate-cancer/configs/project_Healthy_vs_PCa1-4-CG.json --stability --resume
```

Prefer DomainProgram reruns for new studies.

## Operational guardrails

- Keep original run directories and DB instance rows for traceability
- Prefer new `workflow_instance` over manual `node_execution` edits
- Document `resolvedConfig` overrides in operator notes

## See also

- [Logging and observability](../reference/logging-observability.md)
- [Traceability](../reference/traceability-provenance.md)
- [Operator journey](../deployment/operator-journey.md)
- [Config parameter matrix](../reference/config-parameter-matrix.md)
