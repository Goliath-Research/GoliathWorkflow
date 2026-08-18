---
name: Archive methylGrapher-mojo
overview: Archive the methylGrapher-mojo git repo and replace the METHYLGRAPHER_MOJO_* contract (env vars, /opt prefix, overlay dir) with MOJO_ALIGN_* so MethylPipeline and mojo-align no longer speak the old repo’s name.

> **Status: Implemented.** Env family is `MOJO_ALIGN_*`; in-container prefix `/opt/mojo-align`. Azure DevOps repo disable (`isDisabled`) after this README is pushed.

azure_devops:
  type: Feature
  title: "Archive methylGrapher-mojo / MOJO_ALIGN_* contract"
  work_item_id: null
  epic_id: 413
todos:
  - id: rename-contract
    content: Rename METHYLGRAPHER_MOJO_* → MOJO_ALIGN_* (and METHYL_METHYLGRAPHER_MOJO_IMAGE → METHYL_MOJO_ALIGN_IMAGE); /opt/methylgrapher-mojo → /opt/mojo-align; overlay dir; one-release dual-read of old env names
    status: completed
  - id: mojo-align-paths
    content: Drop /home/ubuntu/methylGrapher-mojo and /home/ubuntu/mojo-align hardcodes; sys.path uses cwd + MOJO_ALIGN_ROOT + /opt/mojo-align; fix vg_docker_wrap.sh and Dual CI README
    status: completed
  - id: mp-image-runner
    content: Dockerfile.mojo, entrypoint, build/publish scripts, methylgrapher_wgbs_runner.py, tests, schemas — new names + /opt/mojo-align
    status: completed
  - id: archive-old-repo
    content: Archive-notice README on methylGrapher-mojo; Azure DevOps read-only; drop local checkout after rename lands
    status: completed
  - id: mp-docs
    content: Update MethylPipeline living docs; promote plan under AB#413
    status: completed
---

# Archive methylGrapher-mojo

**Short answer:** you do not need `methylGrapher-mojo` as a live checkout. Production already builds from **mojo-align**. While dropping it, replace every `METHYLGRAPHER_MOJO_*` name with **`MOJO_ALIGN_*`**.

## Naming: `MOJO_ALIGN_*`

See the implementation in:

- mojo-align: `gpu-common/python/mojo_align_env.py`, `gpu-common/src/mojo_align_env.mojo`, `methylgrapher/engine/mojo_align_env.py`
- MethylPipeline: `workers/methyl_worker/mojo_align_env.py`

| Old | New |
|-----|-----|
| `METHYLGRAPHER_MOJO_*` | `MOJO_ALIGN_*` |
| `METHYL_METHYLGRAPHER_MOJO_IMAGE` | `METHYL_MOJO_ALIGN_IMAGE` |
| `/opt/methylgrapher-mojo` | `/opt/mojo-align` |
| `/work/epimethyl/images/methylgrapher-mojo-overlay` | `/work/epimethyl/images/mojo-align-overlay` |
| `scripts/build_methylgrapher_mojo_image.sh` | `scripts/build_mojo_align_image.sh` (wrapper kept) |

CLI `methylGrapher` and image name `epimethyl/methylgrapher:1.70-mojo-*` are unchanged.

## Azure DevOps (after pushing the archive README)

No pipelines matched `methylGrapher` / `mojo-align` in Development. Disable the repo (read-only) after the archive notice is on `main`:

```bash
az rest --method patch \
  --uri 'https://dev.azure.com/EpiMethyl/Development/_apis/git/repositories/71b024b3-904d-443e-8b2a-78922774e6a1?api-version=7.1' \
  --body '{"isDisabled": true}' \
  --resource 499b84ac-1321-427f-aa17-267ca6975798
```

Do not delete the repo. Keep SHAs for import history.

## Resulting repository set

| Repo | Role |
|------|------|
| **MethylExtractor** | Native C extract |
| **MethylPipeline** | Python orchestrator; bakes image into `/opt/mojo-align` |
| **mojo-align** | Mojo/Python alignment + methylGrapher science |
