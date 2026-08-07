# Constrained worker ops actions (no shell)

UI/DB must not get a worker shell. Science parameters stay on
`actionConfig` → task `resolvedConfig`. Separately, a small **allowlisted ops
action family** may be added later for fleet diagnostics.

## Proposed actions (not implemented)

| Action | Capability | Behavior | Limits |
|--------|------------|----------|--------|
| `worker.env_get` | `worker.ops` | Return allowlisted env values | Deny `*_TOKEN`, `*_PASSWORD`, `AZURE_SQL_*` |
| `worker.env_set` | `worker.ops` | Set allowlisted non-secret deploy keys (or write `/work/epimethyl/env/overrides/`) | No arbitrary export; restart-safe |
| `worker.fs_list` | `worker.ops` | List under allowlisted roots | `/work/cache`, `/work/genomes`, `/work/epimethyl/images`, sample-scoped paths; no `..` |
| `workflow.fs-stat` | existing | Prefer extending this for read-only probes | Read-only |

## Security checklist

- Portal RBAC distinct from science Align claimers
- Pydantic I/O + JSON Schema (`extra=forbid`)
- Allowlists in schema/code, not free-form shell
- Secret redaction in outputs
- Audit via `wf.node_execution`

**Never** use ops env actions for Align science knobs (`align_engine`, Mojo
packs, `qc_bam_engine`, etc.) — those belong on `actionConfig.methylgrapher_wgbs`.
