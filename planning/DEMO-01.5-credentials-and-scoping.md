# DEMO-01.5 — Secure Demo Environment Credentials with OIDC & Least-Privilege Scoping

| | |
|---|---|
| **Status** | **As-built** — identity, roles, and Key Vault have been created; see §3/§4 for the actual (not originally proposed) configuration |
| **Applies to** | `maplelabs/CloudMax` ephemeral demo environment (DEMO-01) |
| **Related** | IMG-01.4 (registry credentials pattern) · DEMO-01.1 (lifecycle strategy) · DEMO-01.2 (Terraform module, merged in #66) · DEMO-01.3/01.4 (create/destroy workflows — depend on this) |

## 1. Purpose

DEMO-01.2's Terraform module already references two forms of credential need
that don't yet have a real identity or secret-delivery path behind them:

1. **CI/CD → Azure auth** — DEMO-01.3's create workflow and DEMO-01.4's
   destroy workflow need to authenticate to Azure to run
   `terraform apply`/`destroy`, snapshot operations, and resource cleanup.
2. **VM → application secrets** — the demo VM's managed identity (already
   wired into the Terraform module as `AcrPull` + Key Vault `get`/`list`)
   needs an actual Key Vault to pull real runtime secrets from (DB passwords,
   LLM API keys, etc.) once `docker compose up` brings the CloudMax stack
   online on that VM.

This document defines how both are secured, following the same no-stored-
secrets pattern already used in IMG-01.4 (ACR push via OIDC, no registry
password).

## 2. Two distinct identity *concerns* — now served by one actual identity

The original design (below, as proposed) called for two **separate** App
Registrations -- one scoped to `AcrPush` only (reused from IMG-01), one scoped
to `Contributor` for demo infra. **What was actually built is a single App
Registration, `CloudMaX-App-GitHub-Int`, holding both scopes.** This is a
deliberate simplification accepted in practice: one identity, one federated
credential, one set of GitHub secrets to manage, at the cost of a larger
blast radius per credential (a compromise of this one app can both push
images *and* create/destroy infrastructure in `cloudmax`, rather than just
one or the other).

| | CI/CD → Azure auth | VM runtime identity (built in DEMO-01.2, unaffected by this) |
|---|---|---|
| **What it is** | `CloudMaX-App-GitHub-Int` (single App Registration, federated credential) | VM's system-assigned managed identity (created automatically when the VM is provisioned) |
| **Used by** | GitHub Actions -- both `image-build-push.yml` (IMG-01) and `demo-create.yml`/`demo-destroy.yml` (DEMO-01.3/01.4) | The CloudMax application processes running on the demo VM |
| **Used for** | `AcrPush` (image publish) **and** `terraform apply`/`destroy`, snapshot ops, resource cleanup | Pulling images from ACR (`AcrPull`), fetching app secrets from Key Vault (`get`/`list`) |
| **Actual role assignments (verified via `az role assignment list`)** | `Contributor` on `/resourceGroups/cloudmax`; `AcrPush` on `registrycloudmax` | `AcrPull` on `registrycloudmax`; Key Vault `Get`/`List` on `cloudmax-kv` |

## 3. Track A — CI/CD → Azure authentication (as-built)

| Item | As proposed | **As actually built** |
|---|---|---|
| App Registration name | `cloudmax-demo-env-cicd` (new, separate) | **`CloudMaX-App-GitHub-Int`** (single app, also used by IMG-01) |
| Credential type | Federated credential (OIDC), no client secret | Same — OIDC federated credential, no client secret generated |
| Federated credential subject | `repo:maplelabs/CloudMax:environment:demo` (Environment-scoped) | `repo:maplelabs/CloudMax:ref:refs/heads/main` (branch-scoped — confirm this is sufficient for `workflow_dispatch`-triggered workflows; GitHub's OIDC subject for `workflow_dispatch` runs still reflects the ref the workflow was dispatched against, so a `main`-ref subject does cover dispatches run against `main`) |
| Role assignment | `Contributor` on `cloudmax` RG only (new identity) | `Contributor` on `cloudmax` RG -- **plus** `AcrPush` on the registry, both on the same identity |
| Storage access for Terraform remote state | Not anticipated in original scope | **Added:** `Storage Blob Data Contributor` on the new `cloudmaxtfstate` storage account (RBAC data-plane access is separate from `Contributor`'s control-plane access) -- principal `ffaac93c-797b-4e5e-95ae-a518191d8b27` |

## 4. Track B — VM runtime secrets (Key Vault provisioning, as-built)

| Item | Decision |
|---|---|
| New resource | 1 Azure Key Vault, **`cloudmax-kv`** (actual name; originally proposed as `cloudmax-demo-kv`), in the `cloudmax` resource group |
| Access model | **Access policy** (matches DEMO-01.2's `azurerm_key_vault_access_policy` resource already written) granting the VM's system-assigned managed identity `Get`/`List` on **secrets** only — no `Set`/`Delete`/`Purge`, no key/certificate permissions |
| What goes in it | Runtime secrets the CloudMax stack needs at `docker compose up` time: DB connection string/password, Azure OpenAI key, Anthropic/Claude key, any other integration credentials currently used by the long-lived manual demo VM |
| How the app retrieves them | At VM boot / container start, the app (or an init step before `docker compose up`) calls Key Vault directly using the VM's managed identity — **no secret is baked into the image, no secret is written to a cloud-init script or the VM's disk as plaintext, no secret is ever present in GitHub** |
| Who populates the Key Vault initially | Out of scope for automation — a one-time manual step by the repository owner/admin, since there's no safe automated path to the *source* of these secrets (they come from existing service accounts/subscriptions, not generated by this pipeline) |

## 5. GitHub configuration

| Item | As proposed | **As actually built** |
|---|---|---|
| GitHub Environment | `demo` (new), secrets scoped to it | **Not created.** `AZURE_CLIENT_ID`/`AZURE_TENANT_ID`/`AZURE_SUBSCRIPTION_ID` were added as **repository-level** secrets instead |
| Secret scope implication | Environment secrets, gated by required reviewers before a workflow run can read them | Repo secrets are readable by **any** workflow in the repo that requests them — including `image-build-push.yml` (expected, same identity now) but also means there is currently **no reviewer gate** between a `workflow_dispatch` trigger and this identity being used for `Contributor`-level infra changes |
| Federated credential subject | `repo:maplelabs/CloudMax:environment:demo` (Environment-scoped) | `repo:maplelabs/CloudMax:ref:refs/heads/main` (branch-scoped, matching IMG-01's pattern) |

**Gap introduced by this simplification:** DEMO-01.4's destroy workflow
acceptance criteria explicitly requires being "gated by a required reviewer"
(destructive action). With repo secrets and no `demo` Environment, that
reviewer gate does not exist yet at the credential level. `demo-create.yml`
already references `environment: demo` in its job config (see
`.github/workflows/demo-create.yml`) -- **that Environment must still be
created in GitHub repo settings** (Settings -> Environments -> New
environment -> `demo`) with required reviewers configured, and the three
secrets moved from repo-level into it, before DEMO-01.4 (destroy) is built
and before relying on review-gating for safety. Tracked as a follow-up, not
blocking DEMO-01.3 (create) from being tested.

## 6. Trigger safety (explicit confirmation required by acceptance criteria)

Both create (DEMO-01.3) and destroy (DEMO-01.4) workflows must be confirmed,
before this identity is wired in, to:
- Trigger **only** on `workflow_dispatch` (manual) or the DEMO-01.1 §3.2
  scheduled idle-timeout check (`schedule: cron`, which is not
  fork/PR-triggerable)
- **Never** trigger on `pull_request` or any event where a fork or untrusted
  branch could invoke them — this is the same trust boundary IMG-01.1 already
  established (PR CI never gets registry/publish credentials; the analogous
  rule here is PR CI never gets `Contributor` access to `cloudmax`)

This is a confirmation step against DEMO-01.3/01.4's actual workflow files
once written — not something DEMO-01.5 itself implements, since those
workflows don't exist yet. Listed here as a gate that must be re-checked
when DEMO-01.3/01.4 are built.

## 7. What DEMO-01.5 does NOT cover

- Does not populate the Key Vault with real secret values (manual, one-time,
  by the repo owner — see §4)
- Does not build the create/destroy workflows themselves (DEMO-01.3/01.4) —
  only prepares the identity/auth those workflows will consume
- Does not change DEMO-01.2's Terraform module — it already references
  `var.key_vault_id`/`var.container_registry_id` correctly; this task's job
  is making those IDs resolve to real resources

## 8. Open questions / accepted trade-offs (updated post-implementation)

- **Resolved:** Key Vault is named `cloudmax-kv` (not `cloudmax-demo-kv` as
  originally proposed) -- no conflict, just noting the actual name for
  anyone cross-referencing this doc against Terraform variables/workflow
  configuration.
- **Accepted trade-off (not resolved as "separate identity"):** a single
  identity (`CloudMaX-App-GitHub-Int`) now holds both `AcrPush` and
  `Contributor` on `cloudmax`, rather than the two independently-scoped
  identities originally proposed in §2/§3. This was a deliberate operational
  simplification. Revisit if/when the blast-radius trade-off becomes a
  concern (e.g., before CloudMax reaches a stage where compromise of CI
  credentials would be high-impact) -- splitting later means: register a
  second app, move the `Contributor` role assignment to it, update
  `demo-create.yml`/`demo-destroy.yml`'s Environment secrets.
- Confirm who will do the one-time manual Key Vault secret population, and
  which specific secrets the current long-lived demo VM uses today (an
  inventory of this doesn't exist yet in this design).

## 9. Acceptance criteria mapping (DEMO-01.5) — updated against as-built state

- [x] Azure AD App Registration + federated credential (OIDC) scoped to this
      repo/workflow only, no client secret generated — §3 (as `CloudMaX-App-GitHub-Int`,
      not a dedicated per-purpose app, but the criterion itself is met: no
      secret, OIDC-only, scoped to this repo)
- [x] Role assignment is least-privilege: `Contributor` scoped to the
      dedicated demo resource group only — §3 (met, though the same identity
      also separately holds `AcrPush` — see §2/§8 trade-off note)
- [x] Runtime secrets delivered via Key Vault + VM managed identity at boot,
      never baked into the VM image or committed — §4
- [ ] GitHub Environment (`demo`) holds Azure tenant/subscription/client IDs
      as Environment secrets, not repo secrets or plain workflow YAML —
      **not met as-built**: secrets are currently repo-level, no `demo`
      Environment exists yet — see §5 for the gap and required follow-up
- [ ] Confirmed neither create nor destroy workflows run on
      `pull_request`/fork-triggerable events — **pending**, re-check against
      DEMO-01.3/01.4's actual workflow files once written (§6). Note:
      `demo-create.yml` (DEMO-01.3) is already written and confirmed
      `workflow_dispatch`-only -- this item remains open pending DEMO-01.4
      (destroy) and the `demo` Environment/reviewer-gate follow-up above.
