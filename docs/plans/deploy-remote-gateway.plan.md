---
name: Deploy remote gateway
overview: >
  SSH into gateway.goliathresearch.com, bring methyl-gateway + nginx to a healthy HTTPS /v1/health
  state from the synced repo release layout, then point this VM’s worker at that gateway so
  SamplePrep can run distributed instead of local methyl-workflow-run.

> **Status: completed (2026-07-29)** — HTTPS health OK; omnibus methyl-worker cut over; in-flight local Aligns left running.

todos:
  - id: inventory-remote
    content: "SSH inventory gateway.goliathresearch.com: arch, /work, gateway.env, certs, systemd, loopback health"
    status: completed
  - id: install-gateway
    content: install_gateway_systemd.sh + fix gateway.env if needed; restart methyl-gateway
    status: completed
  - id: nginx-tls
    content: setup_gateway_nginx.sh --hostname gateway.goliathresearch.com; ensure certs; open :443
    status: completed
  - id: verify-health
    content: Verify loopback + https://gateway.goliathresearch.com/v1/health from this VM
    status: completed
  - id: worker-cutover
    content: Point this VM WORKER_API_BASE at remote gateway; enroll worker; avoid double-Align on in-flight samples
    status: completed
  - id: rotate-creds
    content: Install SSH pubkey and rotate the chat-exposed azureuser password
    status: completed
azure_devops:
  type: Feature
  parent_epic: AB#413
  work_item_id: null
---

# Deploy gateway.goliathresearch.com and cut over workers

## Done (2026-07-29)

- Synced latest MethylPipeline tree to gateway VM (`/work/goliath/repos/MethylPipeline`); editable `methyl-gateway` reinstalled; systemd binds `127.0.0.1:8080`.
- Let’s Encrypt cert + nginx TLS for `gateway.goliathresearch.com`; NSG allows :80/:443.
- `WORKER_API_BASE=https://gateway.goliathresearch.com/v1`; omnibus `methyl-worker.service` polling; existing worker token reused (no re-enroll).
- nginx `worker_poll` rate raised 30→300 r/m after per-capability units stampeded the limiter.
- SSH: `ubuntu` / `azureuser` via `deploy/gateway_key.pem`; chat password rotated (operator host `/tmp/gateway_azureuser_newpass.txt`).
- Local SamplePrep PIDs left running (no double-Align).

Operator note: [`/work/projects/prostate-cancer/GATEWAY_CUTOVER.md`](/work/projects/prostate-cancer/GATEWAY_CUTOVER.md).
