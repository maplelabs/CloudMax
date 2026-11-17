# DEMO-01.1 — Demo Environment Lifecycle & Snapshot Strategy

| | |
|---|---|
| **Status** | Draft — pending repository owner review/approval |
| **Applies to** | `maplelabs/CloudMax` ephemeral demo environment (DEMO-01) |
| **Related** | [IMG-01](#) container image pipeline · DEMO-01.2 (Terraform module) · DEMO-01.3 (create workflow) · DEMO-01.4 (destroy workflow) · DEMO-01.7 (`:verified` tag) |

## 1. Purpose

CloudMax demos today run on manually-created, long-lived Azure VMs — idle disks,
snapshots, and static IPs billed continuously with no demo actually running most of
the time. This document defines the lifecycle design for an **ephemeral,
Terraform-provisioned demo environment**: how it's created, what state it restores
from, when/how it's destroyed, and how snapshots prevent data loss across that
cycle — before any Terraform or workflow code is written (DEMO-01.2–01.4).

## 2. Lifecycle overview

The **first** create has no prior snapshot to restore from — it provisions a VM
with fresh disks (standard image, not snapshot-sourced). **Every create after
that** restores OS + data disks from the latest snapshot left behind by the
previous destroy cycle:

```
FIRST RUN ONLY
 ┌────────────┐  create (manual, fresh disks — no snapshot source yet)
 │  No demo   │ ─────────────────────────────────────────────────────▶ ┐
 │  running   │                                                        │
 └────────────┘                                                        │
                                                                        ▼
STEADY-STATE CYCLE (2nd create onwards)                       ┌──────────────┐
 ┌────────────┐   create (manual, restores from latest snap)  │ Demo running │
 │  No demo   │ ──────────────────────────────────────────────▶│ (VM + disks  │
 │  running   │                                                │  from latest │
 │ (steady    │◀───────────────────────────────────────────── │  snapshot,   │
 │  state)    │   destroy (manual OR idle-timeout)             │  or fresh on │
 └────────────┘                                                │  first run)  │
                                                                └──────┬───────┘
                                                                       │
                                                       snapshot-create │ (OS + data disk)
                                                                       ▼
                                                               verify Succeeded
                                                                       │
                                             ┌─────────────────────────┴─────────────────┐
                                             ▼ pass                                       ▼ fail
                                    terraform destroy                           HARD STOP — no destroy
                               (VM → NIC → disk → IP → NSG)                    demo left running; alert
```

The "steady state" is **no billable demo resources running at all** — this is what
realizes the cost savings the ephemeral pattern is meant to deliver. The first
cycle is the one-time bootstrap that produces the initial snapshot pair that all
subsequent demos restore from.

## 3. Trigger model

### 3.1 Create

- **Trigger:** manual only, via `workflow_dispatch` on DEMO-01.3's create workflow.
- **Inputs:**
  - `demo_name` (free text, used to tag/name resources and in the audit log)
  - `requested_by` (defaults to the GitHub Actions actor; overridable for someone
    requesting on behalf of another team)
  - `image_tag` (optional; defaults to `:verified` per DEMO-01.7 — can be overridden
    to a specific `sha-<gitsha>` to test an unreleased build)
- **Rationale:** demos are infrequent and planned (sales calls, internal reviews),
  so there's no need for automatic/scheduled creation. Manual trigger also keeps a
  human accountable for every environment that incurs cost.
- **Bootstrap vs. steady-state image source:**
  - **First create (bootstrap):** no snapshot exists yet. DEMO-01.2's Terraform
    module provisions the VM with **fresh disks from a standard base image**
    (`create_option = "FromImage"`), not a snapshot source. The demo is deployed
    and run as normal, then torn down via the standard destroy workflow
    (§5) — this first destroy cycle is what produces the **initial** snapshot
    pair (OS + data) that every later demo restores from.
  - **Every create after that (steady-state):** disks are created from the
    **latest available snapshot** (`create_option = "Copy"`, source =
    most recent OS/data snapshot) rather than a fresh base image — this is what
    carries forward pre-loaded demo data/state across ephemeral sessions.
  - The create workflow does not need special-case logic to tell these apart:
    it always looks for the latest snapshot and falls back to the base image if
    none exists yet (i.e., the very first run for a given demo lineage).

### 3.2 Destroy

Two trigger paths, both converging on the same backup-then-destroy workflow
(DEMO-01.4):

1. **Manual** — `workflow_dispatch`, triggered by whoever requested the demo (or an
   admin), once the demo is no longer needed.
2. **Scheduled idle-timeout (safety net)** — a scheduled workflow (`schedule: cron`,
   running hourly) checks how long the demo environment has been up. If it has
   exceeded **8 hours** since creation, it automatically triggers the same
   backup-then-destroy workflow.
   - 8 hours covers a full working day/demo session with margin, while bounding the
     worst case cost of someone forgetting to tear a demo down overnight or over a
     weekend.
   - This is a safety net, not the primary teardown path — the expectation is that
     most demos are destroyed manually right after use.

Both paths call the **same** destroy workflow — there is only one destroy code
path to keep snapshot-verification-then-destroy sequencing (§5) uniform regardless
of what triggered it.

## 4. Snapshot strategy

| Decision | Value | Rationale |
|---|---|---|
| Snapshot type | **Incremental** (`incremental = true` on `azurerm_managed_disk_snapshot` or equivalent) | Only changed blocks since the last snapshot are stored — materially cheaper than full snapshots for repeated demo cycles. |
| Storage tier | **`Standard_LRS`** | Demo data is non-critical and regionally reproducible from Terraform; Premium/ZRS redundancy is not justified for this cost-sensitive, ephemeral use case. |
| Disks snapshotted | **One snapshot per disk** — OS disk and data disk separately | Keeps restore granular (e.g. if only data disk needs restoring) and matches how `azurerm_managed_disk` `create_option = "Copy"` sources a snapshot per disk in DEMO-01.2. |
| Retention | **Keep last 3 snapshots per disk** | Balances recoverability (can step back if the most recent snapshot is somehow bad) against storage cost — older snapshots beyond 3 are pruned at the end of each successful destroy cycle (DEMO-01.4). |
| Naming | `<demo-name>-<disk-role>-snap-<timestamp>` (e.g. `acme-demo-os-snap-20261117T0800Z`) | Snapshot provenance (which demo cycle produced it, when) is readable without querying Azure metadata separately. |

**What a new demo restores from:** the *latest available snapshot* for each disk
role (OS, data) at the time of creation — i.e., the state left behind by the most
recent successful destroy cycle — **except the very first create for a demo
lineage, which has no snapshot yet and provisions from a fresh base image
instead** (see §3.1). That first destroy cycle is what creates the initial
snapshot pair; every create after that restores from it. This is how no demo
data is lost between ephemeral sessions from the second cycle onward: each
destroy backs up the exact state the next create will restore from.

## 5. Destroy sequencing (hard-blocked ordering)

Destroy is not a single `terraform destroy` call — it's a **sequenced, gated**
procedure:

```
1. snapshot-create   : take incremental snapshot of OS disk
2. snapshot-create   : take incremental snapshot of data disk
3. verify            : poll both snapshots until provisioningState == "Succeeded"
                        (or explicit failure/timeout)
        │
        ├─ any snapshot fails or times out ──▶ HARD STOP
        │                                      - no destroy step runs
        │                                      - demo environment left running
        │                                      - workflow fails loudly, logs which
        │                                        disk/snapshot failed
        │
        └─ both snapshots verified Succeeded
                        ▼
4. terraform destroy, resource order:
     a. VM            (stop compute billing first)
     b. NIC
     c. managed disks  (OS + data — now safely backed up)
     d. public IP
     e. NSG
5. post-destroy check : az resource list --tag demo-name=<name>
                          confirm nothing billable remains
6. prune snapshots     : delete snapshots beyond retention count (3) for this demo
```

**Why this ordering:** a failed or skipped backup step must never be allowed to
proceed to destroy — this is the single rule that actually protects demo data and
is the crux of this entire design. VM is destroyed first (stops the largest cost
driver immediately) but only *after* snapshot verification, never before.

## 6. Cost model

Assumptions: `Standard_D2s_v5` VM (2 vCPU/8GB, suitable for `docker compose up` of
the CloudMax stack), 128GB OS disk + 128GB data disk (`Standard_LRS`), one static
public IP, East US region pricing (revisit if region changes).

| Item | Rate | Demo-hour cost | Idle/month cost |
|---|---|---|---|
| VM compute (`Standard_D2s_v5`) | ~$0.096/hr | $0.096/hr | $0 (destroyed when idle) |
| OS + data disk (while VM running) | ~$0.0095/GB-month × 256GB | ~$0.0033/hr | — |
| Static public IP (while allocated) | ~$0.004/hr | $0.004/hr | $0 (released on destroy) |
| **Snapshots (persist between demos)** | ~$0.05/GB-month, incremental (only changed blocks billed) | — | ~$1–3/month per disk pair, assuming light drift between demo sessions |
| NSG, NIC | No direct charge | — | — |

**Approximate totals:**
- **Per demo-hour (environment up):** ~**$0.10/hr**
- **Idle/month (no demo running, only retained snapshots):** ~**$2–6/month**
  (3 retained snapshots × 2 disks, incremental)

This is a large reduction from the current baseline (long-lived VM + disks + IP
billing 24/7 regardless of demo usage — roughly **$70–90/month** idle for an
equivalent always-on `D2s_v5` + disks + IP). These figures are estimates for
sizing purposes only; revisit once DEMO-01.2's actual VM/disk sizing is finalized.

## 7. Open questions for reviewer sign-off

- Is 8 hours the right idle-timeout safety-net threshold, or should it be shorter
  (e.g. 4 hours) given cost sensitivity?
- Is retaining 3 snapshots sufficient, or should there be a longer-lived "golden"
  snapshot kept outside the rolling retention window?
- Confirm `Standard_D2s_v5` sizing is adequate for running the full CloudMax stack
  via `docker compose up` (backend, frontend, agents, diagnostics MCP server).

## 8. Acceptance criteria mapping (DEMO-01.1)

- [x] Trigger model defined for create (manual `workflow_dispatch` with
      demo name/date input) and destroy (manual, or scheduled after N hours of
      inactivity as a safety net) — §3
- [x] Snapshot strategy defined: incremental snapshots, `Standard_LRS`, one
      snapshot per disk (OS + data), retention count decided (keep last 3) — §4
- [x] Destroy sequencing defined and documented: snapshot-create → verify success
      → terraform destroy (VM → NIC → disk → public IP → NSG), hard-blocked if
      snapshot verification fails — §5
- [x] Cost model documented ($/demo-hour and $/month idle) — §6
- [ ] Design reviewed and approved by repository owner before implementation
      starts — **pending**
