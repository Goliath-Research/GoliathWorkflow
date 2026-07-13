---
name: Worker Transport Security
overview: Evaluate worker transport; implement capability-based dispatch, security hardening, and multi-cloud Terraform IaC for GPU worker fleets.
azure_devops:
  type: Feature
  title: "Worker Transport Security"
  work_item_id: 672
  epic_id: 413
todos:
  - id: doc-transport
    content: "Write docs/architecture/worker-transport-decision.md"
    status: completed
    work_item_id: 673
  - id: doc-security
    content: "Write docs/architecture/worker-security-review.md"
    status: completed
    work_item_id: 674
  - id: impl-capability-detect
    content: "Add resolve_worker_capabilities() and registration auto-detect"
    status: completed
    work_item_id: 675
  - id: impl-db-capabilities
    content: "Capability-based sp_worker_request_task (PostgreSQL + Azure SQL)"
    status: completed
    work_item_id: 676
  - id: impl-exec-guard
    content: "Execute-time GPU guard in handlers.py"
    status: completed
    work_item_id: 677
  - id: impl-arc-header
    content: "Send X-Arc-Resource-Id from worker client"
    status: completed
    work_item_id: 678
  - id: impl-token-hardening
    content: "Per-VM token file, deploy/env examples, verify_arc_prereqs.sh"
    status: completed
    work_item_id: 679
  - id: impl-provisioning
    content: "Capability-aware provision_worker_node.sh / install_worker_systemd.sh"
    status: completed
    work_item_id: 680
  - id: iac-scaffold
    content: "Scaffold deploy/terraform/"
    status: completed
    work_item_id: 681
  - id: iac-control-plane
    content: "control-plane-azure module"
    status: completed
    work_item_id: 682
  - id: iac-worker-common
    content: "worker-common cloud-init module"
    status: completed
    work_item_id: 683
  - id: iac-worker-nebius
    content: "worker-nebius module"
    status: completed
    work_item_id: 684
  - id: iac-worker-lambda
    content: "worker-lambda module"
    status: completed
    work_item_id: 685
  - id: iac-ci-validate
    content: "CI terraform fmt/validate"
    status: completed
    work_item_id: 686
  - id: iac-coreweave-design
    content: "CoreWeave CKS follow-on in multicloud doc"
    status: completed
    work_item_id: 687
  - id: doc-multicloud
    content: "Write docs/deployment/multicloud-iac.md"
    status: completed
    work_item_id: 688
  - id: verify
    content: "Run pytest, parity, terraform validate"
    status: completed
    work_item_id: 689
---

# Worker Transport, Security, and Capability-Aware Deployment

> **Status: COMPLETED** (2026-07-01)

See [worker-transport-decision.md](../architecture/worker-transport-decision.md),
[worker-security-review.md](../architecture/worker-security-review.md), and
[multicloud-iac.md](../deployment/multicloud-iac.md) for the delivered artifacts.

## Summary

- **Transport:** Keep REST gateway; MCP not used for worker data plane.
- **Dispatch:** `wf.worker.capabilities` authoritative in `sp_worker_request_task`.
- **Registration:** `resolve_worker_capabilities()` auto-detect on VM; `--omnibus` for legacy.
- **Security:** Arc header, per-VM token file, stricter Arc prereq check.
- **IaC:** `deploy/terraform/` scaffold (Azure control plane, Nebius/Lambda workers, CoreWeave design).
