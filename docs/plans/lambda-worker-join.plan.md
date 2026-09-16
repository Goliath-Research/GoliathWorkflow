---
name: Lambda worker join
overview: Make Lambda GPU join easy/safe/fast by separating QNAP shared content (CI promote + genomes/samples), human-gated Azure Arc approval, and a join-only local install+enroll script—then wire that into cloud-init.

> **Status: IMPLEMENTED.** Runbook: [`docs/deployment/lambda_worker_join.md`](../deployment/lambda_worker_join.md). Scripts: `preflight_worker_join.sh`, join-mode `provision_worker_node.sh` (`--prepare-only` / `--finish-enroll`), Docker install path in `bootstrap_epimethyl.sh`, Terraform `worker-common` prepare-only cloud-init.

azure_devops:
  type: Feature
  title: "Lambda worker join (QNAP + staged Arc)"
  work_item_id: null
  epic_id: 413
todos:
  - id: clarify-docs-model
    content: Write lambda_worker_join.md mental model (Azure vs QNAP vs NGC vs Arc) + link from production-platform Phase 4 and operator-journey
    status: completed
  - id: preflight-script
    content: Add scripts/preflight_worker_join.sh (QNAP /work health, require current/manifest, nvidia-smi, WORKER_API_BASE)
    status: completed
  - id: provision-join-only
    content: "Harden provision_worker_node.sh for join-only default: local Docker/CTK/host tools, skip-promote, staged Arc, portal enroll, systemd"
    status: completed
  - id: bootstrap-docker-path
    content: Adjust bootstrap_epimethyl.sh so node join installs Docker/CTK locally while Parabricks layers stay on shared /work/epimethyl/docker
    status: completed
  - id: arc-staged
    content: Support Arc as a separate approved step (prepare-without-arc vs finish-after-arc) so human approval is not inside a long opaque install
    status: completed
  - id: cloud-init
    content: Fix worker-common cloud-init for portal enroll + extract scripts locally; call join path (Arc optional/staged)
    status: completed
  - id: promote-plan
    content: Promote plan to docs/plans/lambda-worker-join.plan.md + README mapping under AB#413
    status: completed
---

# Lambda worker join — easy, safe, fast

## What we decided before (decoded)

Three stores, not one:

| Store | Holds | Who writes | Workers use it for |
|-------|-------|------------|--------------------|
| **Azure DevOps / Artifacts** | MethylPipeline wheels + runtime-bundle, MethylExtractor arch tarballs, assemble/deploy pipelines | CI on tag + manual assemble/deploy | Source of the **release** that gets promoted to QNAP |
| **myQNAPStorage → `/work`** | `epimethyl/` (current release, venvs, extractor, shared Docker data-root), `genomes/`, `samples/`, `site/`, projects | Deploy pipeline / ops / provision-assets | Day-2 runtime (no git on workers) |
| **NGC (not Azure)** | Clara Parabricks container layers | One promote host with NGC login → `/work/epimethyl/docker` | GPU SamplePrep linear/Giraffe paths |

Azure Arc is **governance + attest** (inventory, policy, `X-Arc-Resource-Id`), **not** where we store containers or release bits, and **not** the enroll API.

Portal prereg + gateway enroll is the **trust join** for claim/submit (IP allowlist → one-time `worker_token`).

```mermaid
flowchart LR
  subgraph azure [Azure]
    CI[ADO CI assemble deploy]
    Arc[Arc Connected approval]
    Portal[Portal prereg IP]
    Gw[Gateway TLS]
  end
  subgraph qnap [myQNAPStorage via /work]
    Rel["/work/epimethyl/current"]
    Gen["/work/genomes"]
    Sam["/work/samples"]
    Dock["/work/epimethyl/docker"]
  end
  subgraph ngc [NVIDIA NGC]
    Pb[Parabricks image]
  end
  subgraph vm [Lambda GPU VM]
    Local[Docker CTK host tools]
    Agent[Arc agent]
    Worker[methyl-worker systemd]
  end

  CI -->|promote once| Rel
  Pb -->|pull once on promote host| Dock
  Gen --- Local
  Sam --- Local
  Rel --> Worker
  Dock --> Local
  Portal --> Worker
  Arc -->|you approve| Agent
  Agent --> Gw
  Worker --> Gw
```

## Recommended operating model

**Principle:** Do slow/shared/human-gated work **once**. Make every Lambda VM a **join-only** machine.

### A. Cluster bootstrap (once) — not on every VM

1. Mount QNAP paths: `/work/epimethyl`, `/work/genomes`, `/work/samples`, `/work/site`.
2. GoliathOmics-Release-Assemble + Deploy → `/work/epimethyl/current/manifest.json`.
3. One Parabricks pull into `/work/epimethyl/docker` (NGC; first arch).
4. Genomes/site: Phase 0.

### B. Per worker

1. Portal preregister public IP + `cluster_key` + worker key.
2. Mount `/work`; `preflight_worker_join.sh --require-current` fails closed if release missing.
3. `--prepare-only`: Docker/CTK + host tools; no Arc/enroll.
4. Human-gated Arc Connected + `verify_arc_prereqs.sh`.
5. `--finish-enroll`: gateway enroll + systemd.

## Implementation delivered

| Artifact | Change |
|----------|--------|
| [`docs/deployment/lambda_worker_join.md`](../deployment/lambda_worker_join.md) | Mental model + A/B checklist |
| [`scripts/preflight_worker_join.sh`](../../scripts/preflight_worker_join.sh) | Fail-closed QNAP join checks |
| [`scripts/provision_worker_node.sh`](../../scripts/provision_worker_node.sh) | `--join-mode join\|first`, `--prepare-only`, `--finish-enroll` |
| [`scripts/bootstrap_epimethyl.sh`](../../scripts/bootstrap_epimethyl.sh) | Install Docker/CTK on join; Parabricks pull stays cluster-once |
| [`deploy/terraform/modules/worker-common/main.tf`](../../deploy/terraform/modules/worker-common/main.tf) | Seed → `/opt/methyl`; default prepare-only; no Key Vault worker token |

## Decision: do **not** containerize MethylPipeline / MethylExtractor (like mojo)

Keep CI artifacts — MP wheels + per-arch native MethylExtractor — on shared `/work/epimethyl`. Containers remain for GPU/tool side-cars (Parabricks/NGC, mojo-align, DIA-NN, etc.).

## Out of scope

- Automating QNAP/NFS mount creation (mount remains ops)
- Putting Parabricks/mojo/MP/ME images into Azure Container Registry
- Rebuilding MethylPipeline/MethylExtractor as primary runtime containers
- Building mojo-align in ADO CI
- Replacing Arc approval with fully unattended onboarding (document SP path later)

## Success criteria

- Operator can explain in one page where CI, QNAP, NGC, Arc, and portal each fit
- A new Lambda VM with `/work` mounted and release already promoted becomes a claiming worker via prepare → (Arc approve) → finish-enroll
- Missing QNAP `current` fails immediately with “deploy release first”
- Second worker never re-promotes or re-pulls Parabricks
