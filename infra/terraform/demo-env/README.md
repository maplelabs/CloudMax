# DEMO-01.2 — Demo environment Terraform module

Provisions the Azure infrastructure for a single ephemeral CloudMax demo: VM,
OS + data disks (snapshot-restored or fresh — see
[DEMO-01.1 lifecycle strategy](../../../planning/DEMO-01-lifecycle-and-snapshot-strategy.md)),
NIC, NSG (443/80 only), static public IP, and a system-assigned managed
identity with `AcrPull` + Key Vault secret `get`/`list`.

**Status:** draft scaffold for review — see the `KNOWN LIMITATION` comment in
`main.tf` regarding attaching a snapshot-restored OS disk to
`azurerm_linux_virtual_machine`; this needs to be resolved (via `azapi` or a
custom image) before this module is used for a real steady-state
(snapshot-restore) create.

## Usage

```hcl
module "demo" {
  source = "./infra/terraform/demo-env"

  demo_name             = "acme-poc"
  container_registry_id = "<ACR resource ID>"
  key_vault_id          = "<Key Vault resource ID>"
  admin_ssh_public_key  = file("~/.ssh/id_ed25519.pub")

  # Omit for bootstrap (first) create; set both for steady-state restores.
  os_disk_snapshot_id   = null
  data_disk_snapshot_id = null
}
```

## Remote state

This module uses the `azurerm` backend with no inline config — supply backend
settings at `terraform init` time, e.g.:

```sh
terraform init \
  -backend-config="resource_group_name=<state-rg>" \
  -backend-config="storage_account_name=<state-sa>" \
  -backend-config="container_name=tfstate" \
  -backend-config="key=demo-env/<demo_name>.tfstate"
```

## Idempotency

Resource names are derived deterministically from `var.demo_name`, so
re-running `terraform apply` against an already-provisioned demo converges
rather than duplicating resources.
