---
name: Archive methylGrapher-mojo
overview: The former methylGrapher-mojo git repository is gone (local and Azure DevOps). MethylPipeline and mojo-align use MOJO_ALIGN_* / /opt/mojo-align only. History lives in mojo-align.

> **Status: Implemented.** Env family is `MOJO_ALIGN_*`; in-container prefix `/opt/mojo-align`. The former git repository no longer exists — do not clone, link, or keep a rollback checkout.

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
    content: Drop hardcoded former-tree and host paths; sys.path uses cwd + MOJO_ALIGN_ROOT + /opt/mojo-align; fix vg_docker_wrap.sh and Dual CI README
    status: completed
  - id: mp-image-runner
    content: Dockerfile.mojo, entrypoint, build/publish scripts, methylgrapher_wgbs_runner.py, tests, schemas — new names + /opt/mojo-align
    status: completed
  - id: archive-old-repo
    content: Former git repository removed (local + Azure DevOps); history lives in mojo-align; no clone URL or SHA lookup via that repo
    status: completed
  - id: mp-docs
    content: Update MethylPipeline living docs; promote plan under AB#413
    status: completed
---

# Archive methylGrapher-mojo

**Short answer:** the former git repository does not exist. Production builds from **mojo-align**. Env knobs are **`MOJO_ALIGN_*`**. Import history is in mojo-align; there is no second checkout to pin, clone, or roll back to.

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
| `scripts/build_methylgrapher_mojo_image.sh` | `scripts/build_mojo_align_image.sh` (wrapper removed) |

CLI `methylGrapher` and image name `epimethyl/methylgrapher:1.70-mojo-*` are unchanged. Deprecated env names are dual-read for one release; they are not a path to a second git tree.

## Former git repository

That tree is **gone** — local working copy and Azure DevOps. Do not publish a clone URL, repo GUID, or “disable but keep SHAs” instruction. SHAs from the import live in **mojo-align**.

## Resulting repository set

| Repo | Role |
|------|------|
| **MethylExtractor** | Native C extract |
| **MethylPipeline** | Python orchestrator; bakes image into `/opt/mojo-align` |
| **mojo-align** | Mojo/Python alignment + methylGrapher science |
