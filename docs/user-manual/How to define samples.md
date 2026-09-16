A sample is an **ID + directory on shared storage**. Sample **identity** is imported into **`portal.Samples`** (from Institutions / Labs); the **study** enrolls those samples into analysis groups in **`cfg`**. CSV list files under `/work` are a **materialization** for workers — not the source of truth.

### Layers

| Layer | Owns |
|-------|------|
| **`portal.Samples`** (+ `LabSamples`) | Import registry from institutions/labs; clinical metadata; optional `analyte_id` → `cfg.analyte`; lab run id (`LabSamples.Sample` → processing key) |
| **`cfg.analyte`** | Versioned specimen/matrix catalog (`cfdna`, `buffy_coat`, …); study binds via `default_analyte_id` |
| **`cfg.study` / `cfg.study_group` / `cfg.study_group_member`** | Which portal samples belong to which analysis arm (`control` / `disease`); enrollment hard-filters by study analyte when set |
| **CSV lists** (`data/*.csv`) | Worker-facing lists rewritten from cfg on **study start** (also via admin `methyl-cfg materialize`) |
| **`portal.Groups` / `GroupSamples`** | Customer UI cohorts — **not** study science arms |

```text
Institutions/Labs
       │ import
       ▼
portal.Samples ──► portal.LabSamples.Sample (= BC-H-001)
       │
       │ enroll (cfg)
       ▼
cfg.study_group_member
       │ sync on study start
       ▼
/work/projects/<study>/data/*.csv  →  /work/samples/{id}/
```

### Study → groups → samples

```text
project_*.json  (synced from cfg.study on start)
  controls / diseases
    groups[]
      label
      sample_paths: [ ".../data/healthy.csv" ]   ← derived from cfg membership
  samples_base_path: "/work/samples"             ← default
```

Each CSV is typically:

```csv
sample
BC-H-001
BC-H-002
```

That resolves to processing dirs:

`/work/samples/BC-H-001/`, `/work/samples/BC-H-002/`, …

**Processing key resolution** (when enrolling a member):

1. `portal.LabSamples.Sample` if a lab run is linked  
2. Else explicit `processingSampleKey`  
3. Else `portal.Samples.ParticipantID`  
4. Else fail (do not invent IDs)

### Enroll via cfg (CLI)

```bash
source .venv/bin/activate
export METHYL_CFG_STORE=/work/goliath/cfg-store
export PYTHONPATH=workflow_engine:$PYTHONPATH

methyl-cfg set-study-group Buffy_healthy_vs_PCa \
  --role control --label all --list-filename healthy_b.csv

methyl-cfg set-study-group-members Buffy_healthy_vs_PCa \
  --role control --label all --file members_healthy.json

# members_healthy.json:
# [
#   {"portalSampleId": 1, "labSampleId": 10},
#   {"portalSampleId": 2, "processingSampleKey": "BC-H-002"}
# ]
```

Enrollment updates **cfg only**. `/work` CSVs are refreshed when you **start** the study (below). Optional admin preview: `methyl-cfg materialize --work-root /work` or `methyl-cfg materialize-study-lists`.

Portal procs: `portal.sp_set_study_group`, `sp_set_study_group_members`, `sp_list_samples_for_study_enrollment` (MSSQL picker; pass `@study_row_id` to hard-filter by the study’s `default_analyte_id`), `sp_set_sample_analyte` (bind a sample to `cfg.analyte`). Set the study analyte via `sp_set_study_process_defaults` (`@analyte`) — that also dual-writes `regulatory.primary_analyte` for the runtime.

### Sync on study start (mandatory)

Starting a run **always** synchronizes the published study from cfg onto `/work` before the instance is created or the local engine runs (`ensure_study_work_synced`):

- `finalize_instance_context` (validation start + `methyl-workflow-run`)
- `rest.db_client.create_workflow_instance` (admin / portal Python path)
- `start_sample_prep` / `start_study_validation`

That rewrite of membership CSVs + `project_*.json` is the guarantee against out-of-sync `/work`. Explicit `methyl-cfg materialize` is bootstrap/admin only — not required for run correctness.

Do **not** edit a published study mid-run; clone → edit draft → publish, then start (start syncs the published version).

SQL-only `portal.sp_create_and_start_instance` cannot write `/work` — portal must call the Python start path (or sync first).

### Three locations (same samples, different roles)

```mermaid
flowchart LR
  ingress["Ingress cloud\nfastqStorage / fastqSource"] -->|"sample.download_fastq"| work["Shared /work/samples/id/\nprocessing"]
  work -->|"align / extract / QC"| work
  work -->|"sample.archive_sample"| archive["Long-term cloud\nsampleStorage / sampleDestination"]
```

| Phase | Config object | Typical content |
|-------|---------------|-----------------|
| **Ingress** (lab FASTQ) | Study/instance `fastqStorage` → per-sample `fastqSource` | S3/Azure/GCS/file + credentials + `prefix` |
| **Processing** | `sampleRoot` = `/work/samples/{sampleId}/`; `sampleDir` = `{sampleRoot}/align.{mode}.{engine}/` | Shared FASTQs at `sampleRoot`; BAM / QC / H5 in the arm leaf |
| **Archive** (long-term) | `sampleStorage` / `h5Storage` → `sampleDestination` | Upload QC ± FASTQ ± H5 after disposition |

Workers never invent paths from env; they get typed JSON on the task.

### Group-level same location, per-sample prefix

Usually **one endpoint per role for the whole study** (or lab), not per group:

- `fastqStorage`: e.g. `s3://lab-bucket/` with `prefixBase: "plasma/"`
- Planner builds each sample as `prefix = prefixBase + sampleId` → `plasma/BC-H-001/`
- Same pattern for archive `sampleStorage`

Overrides are allowed per sample (`fastqSource` already set), but the common case is: **shared endpoint + sampleId as folder**.

### How this maps to `cfg`

| Registry | Role |
|----------|------|
| `cfg.storage_endpoint` | Named location (bucket/account/…), no secrets on `/work` |
| `cfg.credential` | Keys / SAS / etc. |
| `cfg.storage_profile` | Pairs endpoints: `fastqStorageEndpoint` + `sampleStorageEndpoint` |
| `cfg.study` | Manifest; references a storage profile by name |
| `cfg.study_group` | Analysis arm (`control`/`disease`) + CSV filename |
| `cfg.study_group_member` | FK to `portal.Samples` (+ optional `LabSamples`) + `processing_sample_key` |

At schedule time: `expand_storage_profile` / `expand_storage_endpoint` → today’s `fastqStorage` / `sampleStorage` wire format → planner stamps every sample in `context_json.samples[]`.

### What lives under `/work/samples/{id}/`

Identity root (`sampleRoot`): staged FASTQs and `.caas/`. Alignment products (`{id}.bam`, QC tar/JSON, chromosome `*.h5`) live in the bound `sampleDir` arm leaf (`align.linear.parabricks/`, `align.pangenome_wgbs.mojo/`, …). Explicit `samples[].sampleDir` that already names an arm is preserved. See [sample-prep-tooling.md](../architecture/sample-prep-tooling.md). Science workflows (centroid/detector/…) read those H5s via the study’s resolved sample dirs.

**Short version:** import samples into **portal**; enroll them into study arms in **cfg**; **start** syncs CSVs onto `/work` for workers; each ID has one **processing home** on shared storage; ingress/archive are **named cloud endpoints** with per-sample prefixes.
