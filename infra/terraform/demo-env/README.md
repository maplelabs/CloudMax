# DEMO-01.2 — Demo environment Terraform module

Provisions the Azure infrastructure for a single ephemeral CloudMax demo: VM,
OS + data disks (snapshot-restored or fresh — see
[DEMO-01.1 lifecycle strategy](../../../planning/DEMO-01-lifecycle-and-snapshot-strategy.md)),
NIC, NSG (443/80 only), static public IP, and a system-assigned managed
identity with `AcrPull` + Key Vault secret `get`/`list`.

**Status:** draft scaffold for review. The VM is defined via the `azapi`
provider (raw `Microsoft.Compute/virtualMachines`) rather than
`azurerm_linux_virtual_machine`, specifically so the steady-state
(snapshot-restore) path can attach the pre-existing, snapshot-copied OS disk
directly (`storageProfile.osDisk.createOption = "Attach"`) — something
`azurerm_linux_virtual_machine`'s `os_disk` block does not support, since it
always provisions a brand-new disk. The bootstrap (first-run, no snapshot
yet) path instead provisions the OS disk inline from `var.base_image`
(`createOption = "FromImage"`), since a standalone managed disk cannot be
created directly from a marketplace image outside of VM creation.

Note: the `azapi` provider requires Terraform CLI/plan access to validate —
this has not yet been run (`terraform validate`/`plan`) in this environment;
do so before merging.

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
