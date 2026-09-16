---
name: Sync Genomes to QNAP
overview: Operator script to sync /work/genomes to myQNAPcloud via aws s3 sync (S3 credentials from env).
> **Status: COMPLETED** — scripts/sync_genomes_to_s3.sh + runbook notes.

azure_devops:
  type: Feature
  title: "Sync Genomes to QNAP"
  work_item_id: null
  epic_id: 413
todos:
  - id: sync-script
    content: Add scripts/sync_genomes_to_s3.sh (env credentials, dry-run, optional subtree)
    status: completed
  - id: doc-note
    content: Document one-liner in deployment runbook / script header for myQNAPcloud genomes sync
    status: completed
---

# Sync /work/genomes to myQNAPcloud

Use [`scripts/sync_genomes_to_s3.sh`](../../scripts/sync_genomes_to_s3.sh). Destination: `s3://goliath/genomes/` at `https://s3.us-east-1.myqnapcloud.io`. Not rsync — S3 Access Key / Secret Key only.
