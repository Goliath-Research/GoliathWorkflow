# Worker transport decision

> **Status:** Adopted (2026-07-01). REST gateway remains the worker data plane.

## Context

MethylPipeline workers are headless daemons that poll a middle-tier REST API, claim READY workflow
ACTION tasks under lease, run long-running GPU/CPU jobs (minutes to hours), heartbeat, and submit
typed results. Workers **never** connect to the database; the gateway is the sole DB boundary.

This document evaluates transport alternatives against those requirements and records the
architecture decision.

## Requirements

| Requirement | Weight |
|-------------|--------|
| DB isolation (workers have no SQL credentials) | Must |
| Long-running tasks with lease + heartbeat | Must |
| Idempotent replay / signature skip | Must |
| High concurrency (many workers, many instances) | Must |
| Capability-based dispatch (prevention at claim) | Must |
| Multi-cloud egress-only workers (Nebius, Lambda, Azure) | Must |
| Operator familiarity and debuggability | Should |
| Sub-second task pickup latency | Nice-to-have |
| Typed RPC code generation | Nice-to-have |

## Options evaluated

### 1. REST gateway (current)

**Shape:** `POST /v1/workers/{enroll,authenticate,tasks/request,tasks/{id}/submit,heartbeat,fail}` →
`wf.sp_worker_*` procs. Contract: [`contracts/openapi.yaml`](../../contracts/openapi.yaml),
[`workers/WORKER_PROTOCOL.md`](../../workers/WORKER_PROTOCOL.md).

| Pros | Cons |
|------|------|
| Already implemented end-to-end | Polling adds latency vs push |
| TLS + nginx rate limits + IP/Arc gates | JSON payloads less compact than protobuf |
| OpenAPI contract shared with portal/tests | No native streaming for log tail |
| Works through corporate egress (443 only) | |
| Stateless gateway scales horizontally | |

### 2. MCP (Model Context Protocol)

**Shape:** stdio/SSE tool server exposing DB/workflow operations to LLM agents.

| Pros | Cons |
|------|------|
| Excellent for operator/agent DB inspection (already used via Cursor MCP) | Designed for agent tool-calls, not fleet job queues |
| | No native leasing, SKIP LOCKED claim, or heartbeat |
| | Would add a new server surface without improving worker security |
| | Poor fit for hundreds of concurrent GPU workers |

**Verdict:** MCP is the right tool for **operator and dev tooling**, not the worker data plane.
Do not move worker poll/submit to MCP.

### 3. gRPC + mTLS

**Shape:** Typed protobuf RPCs replacing REST JSON for the same proc surface.

| Pros | Cons |
|------|------|
| Strong typing, efficient payloads | New client/server stack on workers and gateway |
| Native streaming for logs/metrics | mTLS cert rotation across multi-cloud VMs is operationally heavy |
| | Does not change DB isolation model (same procs) |
| | Debugging harder than curl/OpenAPI |

**Verdict:** Reasonable **future upgrade** on the same security boundary if payload size or
streaming becomes a bottleneck. Not justified while REST contract is stable and proven.

### 4. Message broker (Azure Service Bus / Storage Queues)

**Shape:** Gateway enqueues task messages; workers subscribe; completion via callback or result queue.

| Pros | Cons |
|------|------|
| Push delivery, natural backpressure | Requires durable broker + DLQ operations |
| Lower pickup latency than poll | Claim/lease/idempotency must be reimplemented on top |
| Decouples gateway from worker timing | Multi-cloud workers need broker egress + auth |
| | At-least-once delivery complicates exactly-once execution |

**Verdict:** Best candidate if **sub-second pickup** or **gateway decoupling** becomes critical.
Treat as a documented future option; not built in the current increment.

## Decision

**Keep REST as the worker transport and security boundary.**

Rationale:

1. **DB isolation is already solved** — workers hold only `WORKER_ID` + `WORKER_TOKEN`; the gateway
   enforces auth, optional IP CIDR bind, and Arc attestation.
2. **Leasing and idempotency are DB-native** — `sp_worker_request_task` uses `FOR UPDATE SKIP LOCKED`;
   signature skip lives in the worker process. A broker would duplicate this logic.
3. **Multi-cloud egress** — HTTPS 443 to a single gateway endpoint is the lowest-friction path for
   Nebius/Lambda/CoreWeave workers.
4. **MCP is the wrong abstraction** for a GPU fleet queue.

## Hardening on the current channel (implemented)

| Layer | Action |
|-------|--------|
| Dispatch | `wf.worker.capabilities` authoritative in `sp_worker_request_task` |
| Attestation | Workers send `X-Arc-Resource-Id` when `GATEWAY_REQUIRE_ARC_ATTEST=1` |
| Secrets | Per-VM token file (mode 600), Key Vault fetch at boot (IaC) |
| Network | Egress-only workers; gateway NSG allowlist per cluster CIDR |
| Defense in depth | Execute-time GPU guard for misregistered nodes |

## Future options (not scheduled)

| Trigger | Option |
|---------|--------|
| Pickup latency SLO &lt; 1s at scale | Service Bus push prototype |
| Large log/metric streaming | gRPC streaming side channel (REST remains control plane) |
| Stricter wire auth | mTLS client certs issued per Arc-managed VM |

## References

- [`worker-security-review.md`](worker-security-review.md)
- [`docs/deployment/multicloud-iac.md`](../deployment/multicloud-iac.md)
- [`docs/plans/worker-transport-security.plan.md`](../plans/worker-transport-security.plan.md)
