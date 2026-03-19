---
name: Unified secret persist
overview: Unify Grok, DisGeNET, and Azure SQL password handling—any secret supplied via CLI or config JSON (discouraged) is idempotently persisted to encrypted local cache and Azure Key Vault when configured; resolution uses the same local→vault→env order for all.
todos:
  - id: persist-helper
    content: Add generic persist_if_changed(manager, value) in secure_credentials.py (idempotent vs get_credential(None))
    status: pending
  - id: align-sql-resolve
    content: Refactor AzureSQLConfig.resolve_password to use get_credential(explicit_key=password) only (file→vault→env; remove env-before-file)
    status: pending
  - id: mapper-step-config
    content: Add disgenet_api_key (+ optional persist_secrets) to MapperStepConfig; apply in _apply_mapper_config_to_args
    status: pending
  - id: bedtools-persist
    content: main_bedtools after final args—persist grok/disgenet when enrich_source needs them and value non-empty; vault URL from args/env
    status: pending
  - id: legacy-main-persist
    content: Legacy methyl-mapper path (MethylMapperConfig load)—persist database.password when non-empty after config load
    status: pending
  - id: cli-flags-docs
    content: Add --no-persist-secrets (or per-type flags); update help/epilog—discourage secrets in JSON
    status: pending
isProject: false
---

# Unified secret persistence (Grok, DisGeNET, Azure SQL)

## Scope

Apply **one pattern** to all sensitive values MethylMapper uses:

| Secret | Credential name / files | Today |
|--------|-------------------------|--------|
| Grok API key | `grok_api_key` → `grok_api_key.encrypted`, KV name `grok-api-key` (default) | `get_credential(explicit_key=...)`; no auto-save |
| DisGeNET API key | `disgenet_api_key` | Same; **not** on `MapperStepConfig` yet (CLI only for bedtools) |
| Azure SQL password | `azure_sql_password` | `resolve_password`: **env first**, then `get_credential()` — order differs from Grok |

There is **no** separate “connection string” field in [`AzureSQLConfig`](packages/methylmapper/methyl_mapper/config.py) today—only `server`, `database`, `username`, `password` composed in `get_connection_string()`. Treat **password** as the secret to persist. If you later add a single ODBC/URL field, store it under a dedicated `credential_name` (e.g. `azure_sql_odbc`) the same way.

## Target behavior

1. **Input sources** (any non-empty value triggers persistence when enabled):
   - CLI (`--grok-api-key`, `--disgenet-api-key`, …)
   - **Config JSON** — e.g. `step_config.mapper.grok_api_key`, `disgenet_api_key` (after adding to [`MapperStepConfig`](packages/methylmapper/methyl_mapper/config.py)); full mapper JSON `database.password` for legacy [`MethylMapperConfig`](packages/methylmapper/methyl_mapper/config.py).
2. **Persist** (default **on**): if value differs from `get_credential(explicit_key=None)`, call existing [`save_credential`](packages/methylmapper/methyl_mapper/secure_credentials.py) with `use_encrypted_file=True` and `use_azure=bool(AZURE_KEY_VAULT_URL)` (same semantics as `methyl_mapper_credentials save --save-to both`).
3. **Next run**: omit CLI/JSON secret; load **encrypted file → Key Vault → env** via `get_credential(explicit_key=None)` (or explicit empty + same chain for SQL after refactor).
4. **Discourage** embedding secrets in JSON in docs/help; still support them for bootstrap then persist.
5. **Escape hatch**: `--no-persist-secrets` (single flag for all) or, if you need granularity, `--no-persist-grok-key` etc.

Use a **separate** `SecureCredentialManager` per secret with that credential’s default Azure secret name (`credential_name.replace("_", "-")`), not a single shared `AZURE_SECRET_NAME` for every secret (today a global `azure_secret_name` can mis-route DisGeNET vs Grok—implementation should prefer **per-credential defaults** unless we add optional `grok_azure_secret_name` / `disgenet_azure_secret_name` later).

## Implementation outline

### 1. Generic helper ([`secure_credentials.py`](packages/methylmapper/methyl_mapper/secure_credentials.py))

- `persist_secret_if_changed(manager: SecureCredentialManager, value: str, *, use_azure: bool) -> bool`
  - Strip/ignore empty `value`.
  - `existing = manager.get_credential(explicit_key=None)`; if `existing == value`, return (no write).
  - Else `manager.save_credential(value, use_azure=use_azure, use_encrypted_file=True)`.
- Optionally pass `azure_key_vault_url` from env/config so `use_azure` is true only when URL is set.

### 2. Align Azure SQL resolution ([`config.py`](packages/methylmapper/methyl_mapper/config.py))

- In `AzureSQLConfig.resolve_password`, replace the current “env then secure storage” split with one call:
  - `explicit = self.password.strip() if self.password else None`
  - `mgr = SecureCredentialManager(credential_name="azure_sql_password", env_var_name="AZURE_SQL_PASSWORD", azure_key_vault_url=...)`  
    (Vault URL: optional field on `AzureSQLConfig` or env `AZURE_KEY_VAULT_URL`—today SQL path may not pass vault URL; add optional `azure_key_vault_url` on `AzureSQLConfig` if missing so KV works for SQL too.)
  - `self.password = mgr.get_credential(explicit_key=explicit) or ""`
- After model load (legacy CLI), if `explicit` was non-empty, call `persist_secret_if_changed(mgr, explicit, ...)`.

### 3. Bedtools / project flow ([`cli.py`](packages/methylmapper/methyl_mapper/cli.py))

- Extend [`MapperStepConfig`](packages/methylmapper/methyl_mapper/config.py): `disgenet_api_key: Optional[str] = None`; wire `_apply_mapper_config_to_args` like `grok_api_key`.
- After `_apply_mapper_config_to_args` and project merge, when `args.persist_secrets` (default True):
  - Build managers with `azure_key_vault_url=args.azure_key_vault_url or os.environ.get("AZURE_KEY_VAULT_URL")`, **default** secret names per credential (do not force one `azure_secret_name` for both Grok and DisGeNET unless explicitly overridden per future fields).
  - If Grok enabled and `args.grok_api_key`: persist.
  - If DisGeNET enabled and `args.disgenet_api_key`: persist.

### 4. Legacy `MethylMapperConfig` / DB path ([`cli.py`](packages/methylmapper/methyl_mapper/cli.py) + [`config.py`](packages/methylmapper/methyl_mapper/config.py))

- Where full JSON is loaded (`load_config_from_json` / `main()` path), after validation, if `config.database.password` was non-empty from file, run persist for `azure_sql_password` with the same manager as `resolve_password`.

### 5. Docs

- Help text: secrets may be written to `~/.methyl_mapper/credentials/*.encrypted` and Key Vault; prefer removing them from JSON after first successful run.
- Update `methyl_mapper_credentials` epilog to mention auto-persist from mapper.

## Testing

- Mock `SecretClient.set_secret`; temp dir for encrypted files; assert skip when value unchanged.
- Manual: JSON with `grok_api_key` + vault env → run bedtools → remove key from JSON → second run still enriches.

## Out of scope (unless requested)

- Per-secret Azure secret name CLI flags (beyond fixing shared-name footgun).
- Storing a full ODBC connection string as one blob (needs a new config field + credential name).
