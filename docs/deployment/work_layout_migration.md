# `/work` layout migration

Migrate study science from `/work/<disease>/` to `/work/projects/<disease>/` and adopt the **four-layer config** stack (site, profile, program, study manifest).

## Target layout

| Path | Role |
|------|------|
| `/work/epimethyl/` | Deployed runtime (unchanged) |
| `/work/site/methyl_site.json` | Site manifest — genomes, GTF, caches (`METHYL_SITE_CONFIG`) |
| `/work/genomes/`, `/work/cache/` | Shared references (`linear/`, `annotation/`, `pangenome/`) and caches |
| `/work/samples/{sample_id}/` | Flat sample archive (unchanged) |
| `/work/projects/<disease>/` | Study configs, data, and run outputs |

Off-cluster durable copy of genomes (myQNAPcloud S3): [`scripts/sync_genomes_to_s3.sh`](../../scripts/sync_genomes_to_s3.sh) → `s3://epimethyl/genomes/`.

Programs (`*.program.json`) and profiles (`*.profile.json`) stay in the **git repo** under `workflow_engine/domain/`.

## Prerequisites

- Maintenance window; stop `methyl-worker` and drain active workflows.
- Disk space ≥ 1.1× size of `/work/<disease>/`.
- `source .venv/bin/activate` from repo root.

## Quick start (prostate-cancer)

```bash
cd /path/to/MethylPipeline
source .venv/bin/activate
cp scripts/migrate_work_layout.env.example scripts/migrate_work_layout.env
# edit paths if needed

# 1. Preflight (no writes)
python scripts/migrate_work_layout.py --manifest-out /tmp/migrate_work_layout.manifest.json

# 2. Filesystem copy + archive source
python scripts/migrate_work_layout.py --apply-fs --no-dry-run
# optional transition symlink:
python scripts/migrate_work_layout.py --apply-fs --symlink --no-dry-run

# 3. Slim legacy manifests, merge site, archive stray programs/profiles on /work
python scripts/migrate_work_layout.py --apply-config --no-dry-run

# 4. Path remap manifests + JSON/CSV/JSONL artifacts
python scripts/migrate_work_layout.py --apply-remap --no-dry-run

# 5. Database (after backup)
psql "$GATEWAY_DATABASE_URL" -f workflow_engine/sql_pg/migrate_work_paths_prostate_cancer.sql
# MSSQL: workflow_engine/sql_mssql/migrate_work_paths_prostate_cancer.sql

# 6. Verify
python scripts/migrate_work_layout.py --verify
```

Or run the shell wrapper directly:

```bash
bash scripts/migrate_work_layout_fs.sh \
  --old-root /work/prostate-cancer \
  --new-root /work/projects/prostate-cancer
```

## Four-layer workflow (post-migration)

```bash
methyl-workflow-run \
  --program workflow_engine/domain/fixtures/mc_stability.program.json \
  --context-file workflow_engine/domain/profiles/mc_gene_fc.profile.json \
  --context '{"projectPath":"/work/projects/prostate-cancer/configs/project_Buffy_healthy_vs_PCa.json"}'
```

| Layer | Owner | Location |
|-------|-------|----------|
| Site | Platform / infra | `/work/site/methyl_site.json` |
| Study manifest | Scientists | `/work/projects/<disease>/configs/project_*.json` |
| Profile | Pipeline engineering (repo) | `workflow_engine/domain/profiles/` |
| Program | Pipeline engineering (repo) | `workflow_engine/domain/**/*.program.json` |

Set on workers (`/work/epimethyl/env/worker.env`):

```bash
METHYL_SITE_CONFIG=/work/site/methyl_site.json
```

Legacy manifests with `step_config`:

```bash
python scripts/migrate_project_config.py --in-place --site-out /work/site/methyl_site.json \
  /work/projects/prostate-cancer/configs/project_*.json
```

## Verification checklist

**Layout**

1. `python scripts/migrate_work_layout.py --verify` — no stale `/work/prostate-cancer` under `/work/projects/` (except `.bak`, `path_remap` legacy keys, symlink).
2. `/work/site/methyl_site.json` validates against `schemas/config/site_manifest.schema.json`.
3. `python scripts/check_missing_sample_dirs.py --samples-base /work/samples` — samples resolve.

**Four-layer config**

4. Every `project_*.json` under `configs/` has **no** `step_config`.
5. `methyl-workflow-run` compile/dry-run with `--program`, `--context-file`, `--context`.
6. `METHYL_SITE_CONFIG` set; `enrich_instance_context` loads site manifest.
7. Idempotency: re-run MC workflow skips actions with matching `.action_results` signatures.

**Database**

8. Zero `wf.workflow_instance` rows with `/work/prostate-cancer` in `context_json` (see SQL verify section).

## Rollback

1. Stop workers and gateway dispatch.
2. Remove `/work/prostate-cancer` symlink if present.
3. Restore from `/work/prostate-cancer.migrated.<timestamp>/` via `rsync`.
4. Restore DB from backup or reverse `REPLACE` in SQL scripts.
5. Restore study manifests from `*.legacy.bak` / `*.pre_layout.bak`.

## Future diseases

```bash
for d in prostate-cancer breast-cancer; do
  python scripts/migrate_work_layout.py --disease "$d" \
    --apply-fs --apply-config --apply-remap --no-dry-run
done
```

New studies should be created directly under `/work/projects/<disease>/`.
