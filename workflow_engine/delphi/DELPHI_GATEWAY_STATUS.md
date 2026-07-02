# Delphi `WfEngineSrv` gateway status

**Status:** Frozen reference (June 2026)

The Delphi HTTP gateway (`WfEngineSrv` / `MethylWfGateway` Windows service) is **no longer the production middle tier**. The supported gateway is **Python `methyl-gateway`** on a dedicated Linux VM (systemd), documented in [`deploy/systemd/methyl-gateway.service`](../../deploy/systemd/methyl-gateway.service) and [`docs/deployment/production_runbook.md`](../../docs/deployment/production_runbook.md).

## Scope when frozen

- Worker and admin REST subset only (OpenAPI `/v1/*` routes implemented in DMVC controllers).
- Dual-database connection helpers (Azure SQL + PostgreSQL, managed identity) remain in `WfEngine.Connection.pas` for historical comparison with Python.
- **No new routes**, OpenAPI parity work, or production deployment changes are planned.

## Build (manual, Win64)

`WfEngineSrv` is **excluded** from the default `WfEngine.groupproj` `Build` target. Build the package and tests via the group project; build the gateway executable only when needed:

1. Open `WfEngine.groupproj` in RAD Studio.
2. Build **WfEnginePkg** and **WfEngineTests** (default group `Build`).
3. For the gateway host: right-click **WfEngineSrv** → Build (Win64).

Or MSBuild:

```text
msbuild WfEngineSrv.dproj /p:Platform=Win64 /t:Build
```

## Development modes (optional)

```text
WfEngineSrv /console port=8080
WfEngineSrv /install
```

See [`WORKFLOW_ENGINE_DELPHI.md`](WORKFLOW_ENGINE_DELPHI.md) for Delphi runtime notes.

## Do not delete

Keep `WfEngineSrv.dproj`, DMVC units, and integration tests for Windows debugging and contract archaeology. CI (`.github/workflows/db-parity.yml`) exercises the **Python** gateway only.
