---
name: Storage Transfer Hardening
overview: Restore high-performance multipart S3/Azure transfers with strong idempotent skips and retries in a shared worker transfer layer, and stop embedding long-lived cloud keys in task JSON by resolving cfg.credential via Azure Key Vault (MI) or locally encrypted files—aligned with existing worker isolation and config-not-code.
> **Status: COMPLETED** — cloud_transfer + vault/encrypted credential refs + schemas/docs.

azure_devops:
  type: Feature
  title: "Storage Transfer Hardening"
  work_item_id: null
  epic_id: 413
todos:
  - id: cloud-transfer-module
    content: "Add cloud_transfer helper: TransferConfig, Azure concurrency, retries, partial+replace, strong skip; wire fastq_source + sample_archive"
    status: completed
  - id: transfer-config-schema
    content: Add storage_transfer knobs to actionConfig/Pydantic + export schemas (config-not-code)
    status: completed
  - id: cred-auth-modes
    content: Add azure_key_vault + encrypted_file auth modes; expand emits refs; worker resolves via MI/Fernet
    status: completed
  - id: tests-docs
    content: Unit tests for transfer + credential refs; update sample_prep_capabilities + portal_resource_profile
    status: completed
---

# Storage transfer performance + credential resolution

## Delivered

- Shared [`workers/methyl_worker/cloud_transfer.py`](../../workers/methyl_worker/cloud_transfer.py): S3 `TransferConfig`, Azure `max_concurrency`, partial+replace downloads, strong multipart skip, within-sample parallelism
- Wired [`fastq_source.py`](../../workers/methyl_worker/fastq_source.py) + [`sample_archive.py`](../../workers/methyl_worker/sample_archive.py)
- Tunables: `actionConfig.storage_transfer` → [`StorageTransferStepConfig`](../../packages/methyldomain/methyl_domain/storage_transfer_config.py) / [`schemas/config/storage_transfer.schema.json`](../../schemas/config/storage_transfer.schema.json)
- Credential refs: `azure_key_vault` / `encrypted_file` in [`fastq_storage.py`](../../packages/methyldomain/methyl_domain/fastq_storage.py); expand emits refs only ([`storage_expand.py`](../../workflow_engine/cfg/storage_expand.py)); worker resolve via [`storage_secrets.py`](../../packages/methyldomain/methyl_domain/storage_secrets.py)
- Docs: [`sample_prep_capabilities.md`](../../workflow_engine/contract/sample_prep_capabilities.md), [`portal_resource_profile.md`](../../docs/deployment/portal_resource_profile.md)

Bulk genomes still use [`scripts/sync_genomes_to_s3.sh`](../../scripts/sync_genomes_to_s3.sh); pipeline sample I/O uses the hardened worker layer.
