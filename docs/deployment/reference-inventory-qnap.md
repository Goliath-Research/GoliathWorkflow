# Reference inventory on myQNAPcloud

Operator map for the company genome inventory: where to **upload** on S3-compatible myQNAPcloud, how pins select versions, and how workers get files under `/work/genomes/`.

Related: [production-platform.md](production-platform.md) Phase 0 · [config-registry.md](../architecture/config-registry.md) · [production_runbook.md](production_runbook.md) · [`scripts/sync_genomes_to_s3.sh`](../../scripts/sync_genomes_to_s3.sh).

## Endpoints (same bucket, different prefixes)

| Role | `cfg.storage_endpoint` | Object prefix | Credential |
|------|------------------------|---------------|------------|
| Reference genomes | `goliath-genomes` | `s3://goliath/genomes/` | `goliath-archive-keys` |
| Sample / H5 archive | `goliath-archive` | `s3://goliath/samples/` | same |
| Lab FASTQ ingress | lab-owned endpoint | (never inferred) | lab credentials |

- **S3 endpoint URL:** `https://s3.us-east-1.myqnapcloud.io`
- **Bucket:** `goliath`
- Genomes use `prefixBase: genomes/` on `goliath-genomes`. Recipe keys and site pins are **relative to that prefix**.

Do **not** upload reference FASTA/GTF/pangenome under `samples/`.

## Upload map (human GRCh38 inventory)

Upload so object keys match `cfg.reference_asset` recipe `key` / `inventoryPrefix`:

| Asset (`name@version`) | Local `/work` dest | QNAP object prefix | Required files |
|------------------------|--------------------|--------------------|----------------|
| `linear-grch38-ensembl-116@1` (**default site pin**) | `/work/genomes/linear/GRCh38/ensembl-116/` | `s3://goliath/genomes/linear/GRCh38/ensembl-116/` | `Homo_sapiens.GRCh38.dna.primary_assembly.fa` (+ `.fai`); Clara: `${FASTA}.bwameth.c2t` (+ `.amb/.ann/.bwt/.pac/.sa`); MojoFq2bamMeth: `${FASTA}.C2T.fa` + `${FASTA}.mojo_linear_k15/{meta.json,kmers.bin,offsets.bin,postings.bin,ref.fa}` dense-v1 (prebuild with `mojo-align/fq2bam-meth/scripts/ensure_mojo_linear_index.sh`; do **not** upload an incomplete pack). Provenance: Ensembl 116 primary_assembly. |
| `gencode-v50@1` (**default site pin**) | `/work/genomes/annotation/gencode/v50/` | `s3://goliath/genomes/annotation/gencode/v50/` | `gencode.v50.annotation.gtf` (inventory name; content is GENCODE 50 PRI comprehensive `gencode.v50.primary_assembly.annotation.gtf`). GENCODE seqnames are `chr1` / `chrM`; Ensembl FASTA uses `1` / `MT`. Methylation mapper remaps 1↔chr1. STAR requires exact match — `download_rna_reference_grch38.sh` builds the index from a temporary chr-stripped GTF. |
| `linear-grch38-ensembl-114@1` (historical) | `/work/genomes/linear/GRCh38/ensembl-114/` | `s3://goliath/genomes/linear/GRCh38/ensembl-114/` | Same layout as 116. Keep for 114-aligned BAMs; do **not** mix with a 116 FASTA. |
| `gencode-v49@1` (historical) | `/work/genomes/annotation/gencode/v49/` | `s3://goliath/genomes/annotation/gencode/v49/` | `gencode.v49.annotation.gtf` |
| `rna-grch38-star-ensembl-116@1` | `/work/genomes/rna/GRCh38/star/ensembl-116/` | `s3://goliath/genomes/rna/GRCh38/star/ensembl-116/` | STAR genome index (`SAindex`, …). No `cfg.site_reference_asset` role — provision with `methyl-cfg provision-assets --name rna-grch38-star-ensembl-116` or `sync_genomes_to_s3.sh --only rna`. |
| `rna-grch38-kallisto-gencode-v50@1` | `/work/genomes/rna/GRCh38/kallisto/` | `s3://goliath/genomes/rna/GRCh38/kallisto/` | `gencode.v50.transcripts.fa`, `.idx`, `gencode.v50.tx2gene.tsv` |
| `pangenome-grch38-d9-1.70@1` | `/work/genomes/pangenome/GRCh38/d9/1.70/` | `s3://goliath/genomes/pangenome/GRCh38/d9/1.70/` | `hprc-v1.1-mc-grch38.d9.gbz`, `.autoindex.1.70.dist`, `.shortread.withzip.min`, `.shortread.zipcodes`, `.paths.sub` |
| `pangenome-grch38-d9-bs-1.70@1` | `/work/genomes/pangenome/GRCh38/d9-bs/1.70/` | `s3://goliath/genomes/pangenome/GRCh38/d9-bs/1.70/` | native-Mojo methylGrapher C2T+G2A bundle (`hprc-d9-bs.wl.gfa`, `hprc-d9-bs.wl.C2T.*`, `hprc-d9-bs.wl.G2A.*`, `.cpg.tsv`, `node.replacement.json`, report). **`wl.gfa` is required for MethylCall** (~43 GB). Pair with image `:1.70-mojo-cuda` or `:1.70-mojo-rocm`. |
| SamplePrep canary WGBS (GSE261315 / SRR28293403) | `/work/genomes/pangenome/canary/gse261315/SRR28293403/` | `s3://goliath/genomes/pangenome/canary/gse261315/SRR28293403/` | `full/` + `subset/` FASTQ pairs, `checksums.json`, `provenance.json` (HPRC/methylGrapher public WGBS; provision via `scripts/provision_sample_prep_canary.sh`) |

### Upload (local → QNAP)

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
# Files already under /work/genomes/{linear,annotation,rna,pangenome}/...
scripts/sync_genomes_to_s3.sh --dry-run
scripts/sync_genomes_to_s3.sh
# optional subtree (aws s3 sync is recursive; narrow with --only):
#   --only linear | annotation | pangenome | rna
#   --only linear/GRCh38/ensembl-116
#   --only annotation/gencode/v50
#   --only rna/GRCh38
#   --only pangenome/GRCh38/d9/1.70
#   --only pangenome/GRCh38/d9-bs/1.70
#   --only pangenome/canary
# Full linear pin (FASTA + bwameth + Mojo C2T/dense-v1 siblings once pack is complete).
# Recipe s3_sync of linear/GRCh38/ensembl-116/ already covers these on provision.
scripts/sync_genomes_to_s3.sh --only linear/GRCh38/ensembl-116
scripts/sync_genomes_to_s3.sh --only annotation/gencode/v50
scripts/sync_genomes_to_s3.sh --only rna
scripts/sync_genomes_to_s3.sh --only pangenome/GRCh38/d9-bs/1.70
# After provisioning the SamplePrep canary FASTQs under genomes/pangenome/canary/:
scripts/sync_genomes_to_s3.sh --only pangenome/canary
```

### Verify on QNAP

```bash
aws s3 ls s3://goliath/genomes/ \
  --endpoint-url https://s3.us-east-1.myqnapcloud.io
aws s3 ls s3://goliath/genomes/linear/GRCh38/ensembl-116/ \
  --endpoint-url https://s3.us-east-1.myqnapcloud.io
aws s3 ls s3://goliath/genomes/annotation/gencode/v50/ \
  --endpoint-url https://s3.us-east-1.myqnapcloud.io
aws s3 ls s3://goliath/genomes/rna/GRCh38/ \
  --endpoint-url https://s3.us-east-1.myqnapcloud.io
aws s3 ls s3://goliath/genomes/pangenome/GRCh38/d9-bs/1.70/ \
  --endpoint-url https://s3.us-east-1.myqnapcloud.io
```

## Site pins and provision (QNAP → `/work`)

1. Install `/work/site/methyl_site.json` (`METHYL_SITE_CONFIG`) with `reference_selection` pins, e.g. from [`site_grch38.example.json`](../../tools/methyl-config-editor/configs/site_grch38.example.json):

```json
"reference_selection": {
  "linear": "linear/GRCh38/ensembl-116",
  "gene_annotation": "annotation/gencode/v50",
  "pangenome": "pangenome/GRCh38/d9/1.70",
  "pangenome_wgbs": "pangenome/GRCh38/d9-bs/1.70"
}
```

Pin values are inventory prefixes under `/work/genomes/` (and under `s3://goliath/genomes/`). `methyl-cfg provision-assets --selected-only` resolves each pin to a published `cfg.reference_asset` whose `inventoryPrefix` matches the pin path.

For WGBS pangenome SamplePrep (`alignmentMode=pangenome_wgbs`), also pin `pangenome_wgbs` and bake C2T/G2A paths into site `actionConfig.methylgrapher_wgbs` (see [`site_grch38.example.json`](../../tools/methyl-config-editor/configs/site_grch38.example.json)). Stock `pangenome` Giraffe indexes are **not** a fallback when the BS bundle is missing.

2. Seed/publish cfg (DB deploy or file store):

```bash
# DB: deploy_azure.sh applies portal_resource_profile.sql + cfg_reference_assets_seed.sql
# File store (dev/CI):
methyl-cfg import-fs --repo-root . --work-root /work
# Credential is not in import-fs fixtures — upsert before provision:
# Copy example, replace REPLACE_WITH_*, then:
methyl-cfg upsert credential \
  --file /path/to/goliath-archive-keys.json \
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

These write under `/work` via public download scripts or packages; they are **not** seeded as `goliath-genomes` recipes:

| Content | How it lands | Notes |
|---------|--------------|--------|
| Plant genomes | `scripts/download_arabidopsis_tair10.sh`, etc. | Ensembl Plants → `/work/genomes/linear\|annotation/...` |
| RNA GRCh38 | `scripts/download_rna_reference_grch38.sh` then QNAP upload | `/work/genomes/rna/...`; recipes `rna-grch38-star-ensembl-116` / `rna-grch38-kallisto-gencode-v50` exist for provision-by-name. No site role (`ck_cfg_sra_role`). Site examples pin `rna_reference` paths. |
| Pangenome bootstrap | `scripts/download_pangenome_hprc_grch38.sh` | Public HPRC; production expects the tree already on QNAP |
| Mapper / STRING caches | runtime or ad-hoc | `/work/cache/methyl_mapper`, `/work/cache/methylenricher/string_edges` |
| Houseman / HiTIMED bases | packaged in `methyldeconv` | Optional site override; `site_reference_asset` roles exist, no QNAP seed |

## SQL and fixtures (parity)

| Artifact | Path |
|----------|------|
| Endpoint + credential seed | `workflow_engine/sql_{mssql,pg}/portal_resource_profile.sql` |
| Reference asset recipes | `workflow_engine/sql_{mssql,pg}/cfg_reference_assets_seed.sql` |
| Site role links (`default@1`) | `workflow_engine/sql_{mssql,pg}/cfg_site_reference_assets_seed.sql` (calls `cfg.cfg_repo_link_site_asset`) and `methyl-cfg link-site-assets --deploy-db`. Stock `pangenome_bundle` (d9-1.70) only; WGBS d9-bs-1.70 is an `@links` swap (`uq_cfg_sra_site_role` + no WGBS role in `ck_cfg_sra_role`). Asset seed alone leaves the grid empty. |
| JSON fixtures | `workflow_engine/domain/fixtures/reference_assets/*.json` |
| Endpoint fixture | `workflow_engine/domain/fixtures/storage_endpoints/goliath-genomes.json` |
| Credential example (not auto-imported) | `workflow_engine/domain/fixtures/credentials/goliath-archive-keys.example.json` |

PostgreSQL DDL lives under **`workflow_engine/sql_pg/`** (not `sql_pgsql`).

Action-catalog population for PostgreSQL (`scripts/populate_postgres_reference_data.py`) does **not** seed genomes; use `cfg_reference_assets_seed.sql` + provision above.
