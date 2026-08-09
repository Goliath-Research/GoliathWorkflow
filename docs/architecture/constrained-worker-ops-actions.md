# Constrained worker ops (no shell)

UI/DB must not get a worker shell. Science parameters stay on
`actionConfig` → task `resolvedConfig`. Fleet control and diagnostics are
separate from science knobs.

## Fleet control (implemented)

Operators set `wf.worker.desired_state` via `portal.sp_set_worker_desired_state`
(`ACTIVE` | `DRAINING` | `STOPPING`). Workers learn it from claim/heartbeat ACK
(`desired_state`, `command` = `NONE`|`DRAIN`|`STOP`) without SSH.

| Command | Idle worker | In-flight task |
|---------|-------------|----------------|
| **DRAIN** | Skip new claims | Finish current work (cooperative pause only if catalog `control.can_pause`) |
| **STOP** | Skip new claims | Abort if catalog `control.can_stop`; else drain after natural completion |
| **ACTIVE** | Claim normally | Continue |

Per-action in-flight capabilities live on the **action catalog**
(`control.can_pause` / `can_continue` / `can_stop` in
`schemas/actions/catalog.json` / `cfg.action_definition.document_json`). The
runner is process-agnostic: it only reads those flags for the claimed
`action_name`. See [action-provider-registry.md](action-provider-registry.md).

Abort uses `fail_task` with error code `4099` (`WORKER_STOPPED`).

## Proposed diagnostic actions (not implemented)

| Action | Capability | Behavior | Limits |
|--------|------------|----------|--------|
| `worker.env_get` | `worker.ops` | Return allowlisted env values | Deny `*_TOKEN`, `*_PASSWORD`, `AZURE_SQL_*` |
| `worker.env_set` | `worker.ops` | Set allowlisted non-secret deploy keys (or write `/work/epimethyl/env/overrides/`) | No arbitrary export; restart-safe |
| `worker.fs_list` | `worker.ops` | List under allowlisted roots | `/work/cache`, `/work/genomes`, `/work/epimethyl/images`, sample-scoped paths; no `..` |
| `workflow.fs-stat` | existing | Prefer extending this for read-only probes | Read-only |

## Security checklist

- Portal RBAC distinct from science Align claimers
- Pydantic I/O + JSON Schema (`extra=forbid`) for any ops actions
- Allowlists in schema/code, not free-form shell
- Secret redaction in outputs
- Audit via `wf.node_execution` / portal SP calls

**Never** use ops env actions for Align science knobs (`align_engine`, Mojo
packs, `qc_bam_engine`, etc.) — those belong on `actionConfig.methylgrapher_wgbs`.
**Never** put pause/stop policy only in host env — declare it on the catalog
`control` block and drive fleet state via `desired_state`.
