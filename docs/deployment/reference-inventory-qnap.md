# Reference inventory on myQNAPcloud

Operator map for the company genome inventory: where to **upload** on S3-compatible myQNAPcloud, how pins select versions, and how workers get files under `/work/genomes/`.

Related: [production-platform.md](production-platform.md) Phase 0 · [config-registry.md](../architecture/config-registry.md) · [production_runbook.md](production_runbook.md) · [`scripts/sync_genomes_to_s3.sh`](../../scripts/sync_genomes_to_s3.sh).

## Endpoints (same bucket, different prefixes)

| Role | `cfg.storage_endpoint` | Object prefix | Credential |
|------|------------------------|---------------|------------|
| Reference genomes | `epimethyl-genomes` | `s3://epimethyl/genomes/` | `epimethyl-archive-keys` |
| Sample / H5 archive | `epimethyl-archive` | `s3://epimethyl/samples/` | same |
| Lab FASTQ ingress | lab-owned endpoint | (never inferred) | lab credentials |

- **S3 endpoint URL:** `https://s3.us-east-1.myqnapcloud.io`
- **Bucket:** `epimethyl`
- Genomes use `prefixBase: genomes/` on `epimethyl-genomes`. Recipe keys and site pins are **relative to that prefix**.

Do **not** upload reference FASTA/GTF/pangenome under `samples/`.

## Upload map (human GRCh38 inventory)

Upload so object keys match `cfg.reference_asset` recipe `key` / `inventoryPrefix`:

| Asset (`name@version`) | Local `/work` dest | QNAP object prefix | Required files |
|------------------------|--------------------|--------------------|----------------|
| `linear-grch38-ensembl-114@1` | `/work/genomes/linear/GRCh38/ensembl-114/` | `s3://epimethyl/genomes/linear/GRCh38/ensembl-114/` | `Homo_sapiens.GRCh38.dna.primary_assembly.fa` (+ `.fai` if used) |
| `gencode-v49@1` | `/work/genomes/annotation/gencode/v49/` | `s3://epimethyl/genomes/annotation/gencode/v49/` | `gencode.v49.annotation.gtf` |
| `pangenome-grch38-d9-1.70@1` | `/work/genomes/pangenome/GRCh38/d9/1.70/` | `s3://epimethyl/genomes/pangenome/GRCh38/d9/1.70/` | `hprc-v1.1-mc-grch38.d9.gbz`, `.autoindex.1.70.dist`, `.shortread.withzip.min`, `.shortread.zipcodes`, `.paths.sub` |
| `pangenome-grch38-d9-bs-1.70@1` | `/work/genomes/pangenome/GRCh38/d9-bs/1.70/` | `s3://epimethyl/genomes/pangenome/GRCh38/d9-bs/1.70/` | methylGrapher C2T+G2A bundle (`hprc-d9-bs.wl.C2T.*`, `hprc-d9-bs.wl.G2A.*`, `.cpg.tsv`, report) |

### Upload (local → QNAP)

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
# Files already under /work/genomes/{linear,annotation,pangenome}/...
scripts/sync_genomes_to_s3.sh --dry-run
scripts/sync_genomes_to_s3.sh
# optional subtree (aws s3 sync is recursive; narrow with --only):
#   --only linear | annotation | pangenome
#   --only pangenome/GRCh38/d9/1.70
#   --only pangenome/GRCh38/d9-bs/1.70
scripts/sync_genomes_to_s3.sh --only pangenome/GRCh38/d9-bs/1.70
```

### Verify on QNAP

```bash
aws s3 ls s3://epimethyl/genomes/ \
  --endpoint-url https://s3.us-east-1.myqnapcloud.io
aws s3 ls s3://epimethyl/genomes/linear/GRCh38/ensembl-114/ \
  --endpoint-url https://s3.us-east-1.myqnapcloud.io
aws s3 ls s3://epimethyl/genomes/pangenome/GRCh38/d9-bs/1.70/ \
  --endpoint-url https://s3.us-east-1.myqnapcloud.io
```

## Site pins and provision (QNAP → `/work`)

1. Install `/work/site/methyl_site.json` (`METHYL_SITE_CONFIG`) with `reference_selection` pins, e.g. from [`site_grch38.example.json`](../../tools/methyl-config-editor/configs/site_grch38.example.json):

```json
"reference_selection": {
  "linear": "linear/GRCh38/ensembl-114",
  "gene_annotation": "annotation/gencode/v49",
  "pangenome": "pangenome/GRCh38/d9/1.70",
  "pangenome_wgbs": "pangenome/GRCh38/d9-bs/1.70"
}
```

Pin values are inventory prefixes under `/work/genomes/` (and under `s3://epimethyl/genomes/`). `methyl-cfg provision-assets --selected-only` resolves each pin to a published `cfg.reference_asset` whose `inventoryPrefix` matches the pin path.

For WGBS pangenome SamplePrep (`alignmentMode=pangenome_wgbs`), also pin `pangenome_wgbs` and bake C2T/G2A paths into site `actionConfig.methylgrapher_wgbs` (see [`site_grch38.example.json`](../../tools/methyl-config-editor/configs/site_grch38.example.json)). Stock `pangenome` Giraffe indexes are **not** a fallback when the BS bundle is missing.

2. Seed/publish cfg (DB deploy or file store):

```bash
# DB: deploy_azure.sh applies portal_resource_profile.sql + cfg_reference_assets_seed.sql
# File store (dev/CI):
methyl-cfg import-fs --repo-root . --work-root /work
# Credential is not in import-fs fixtures — upsert before provision:
# Copy example, replace REPLACE_WITH_*, then:
methyl-cfg upsert credential \
  --file /path/to/epimethyl-archive-keys.json \
  --publish --provider s3
# Production: replace secrets via portal.sp_* instead.
```

3. Provision selected trees:

```bash
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...   # shell sync path
scripts/provision_selected_genomes.sh                    # verify; sync if missing
# or cfg recipes (uses cfg credential after expand):
methyl-cfg provision-assets --selected-only --site default --work-root /work
# full inventory mirror (not pin-selective):
scripts/sync_genomes_to_s3.sh --download
```

`methyl-cfg materialize` writes site/endpoint/asset **metadata** under `/work/site/`; it does **not** download FASTA/GTF. Downloads are `provision-assets` or `sync_genomes_to_s3.sh --download`.

Layout check (optional site + pinned files): `bash scripts/verify_work_layout.sh`.

## Out of band (not cfg genome inventory)

These write under `/work` via public download scripts or packages; they are **not** seeded as `epimethyl-genomes` recipes:

| Content | How it lands | Notes |
|---------|--------------|--------|
| Plant genomes | `scripts/download_arabidopsis_tair10.sh`, etc. | Ensembl Plants → `/work/genomes/linear\|annotation/...` |
| RNA GRCh38 | `scripts/download_rna_reference_grch38.sh` | `/work/genomes/rna/...`; site examples may pin paths |
| Pangenome bootstrap | `scripts/download_pangenome_hprc_grch38.sh` | Public HPRC; production expects the tree already on QNAP |
| Mapper / STRING caches | runtime or ad-hoc | `/work/cache/methyl_mapper`, `/work/cache/methylenricher/string_edges` |
| Houseman / HiTIMED bases | packaged in `methyldeconv` | Optional site override; `site_reference_asset` roles exist, no QNAP seed |

## SQL and fixtures (parity)

| Artifact | Path |
|----------|------|
| Endpoint + credential seed | `workflow_engine/sql_{mssql,pg}/portal_resource_profile.sql` |
| Reference asset recipes | `workflow_engine/sql_{mssql,pg}/cfg_reference_assets_seed.sql` |
| JSON fixtures | `workflow_engine/domain/fixtures/reference_assets/*.json` |
| Endpoint fixture | `workflow_engine/domain/fixtures/storage_endpoints/epimethyl-genomes.json` |
| Credential example (not auto-imported) | `workflow_engine/domain/fixtures/credentials/epimethyl-archive-keys.example.json` |

PostgreSQL DDL lives under **`workflow_engine/sql_pg/`** (not `sql_pgsql`).

Action-catalog population for PostgreSQL (`scripts/populate_postgres_reference_data.py`) does **not** seed genomes; use `cfg_reference_assets_seed.sql` + provision above.
