variable "demo_name" {
  description = "Short identifier for this demo (used to name/tag all resources, e.g. 'acme-poc')."
  type        = string
}

variable "location" {
  # Must match the region of the resource group this module provisions into
  # (and, for the snapshot-restore path, the region of the source snapshots
  # -- Azure requires a disk Copy to be created in the same region as its
  # source snapshot). The 'cloudmax' resource group is in eastus2, so that
  # is the correct default here, not a generic eastus placeholder.
  description = "Azure region for the demo environment. Must match the resource group's region and, for snapshot-restore creates, the source snapshots' region."
  type        = string
  default     = "eastus2"
}

variable "resource_group_name" {
  description = "Existing resource group the demo environment is provisioned into (per DEMO-01's scoped 'cloudmax' RG)."
  type        = string
  default     = "cloudmax"
}

# --- Sizing (parameterized per DEMO-01.2 acceptance criteria) ---------------

variable "vm_size" {
  description = <<-EOT
    Azure VM size for the demo host. Defaults to Standard_B2s (Standard BS
    Family) because the subscription currently has 0 quota for the DSv5/DASv5
    families (confirmed via a real failed apply: "exceeding approved
    standardDSv5Family Cores quota ... Current Limit: 0") -- `az vm
    list-usage --location eastus2` showed 10 cores available in Standard BS
    Family at the time this default was set. Revisit if/when a quota
    increase is approved (see DEMO-01.1's cost model section) or a different
    region/family is preferred.
  EOT
  type        = string
  default     = "Standard_B2s"
}

variable "os_disk_size_gb" {
  description = "Size in GB for the OS disk when no snapshot exists yet (bootstrap create)."
  type        = number
  default     = 128
}

variable "data_disk_size_gb" {
  description = "Size in GB for the data disk when no snapshot exists yet (bootstrap create)."
  type        = number
  default     = 128
}

# --- Snapshot-restore source (steady-state create, per DEMO-01.1 §3.1) -----

variable "os_disk_snapshot_id" {
  description = <<-EOT
    Resource ID of the latest OS-disk snapshot to restore from. Leave null for
    the bootstrap create (first run for this demo lineage), which provisions
    a fresh OS disk from a base image instead (DEMO-01.1 §3.1/§4).
  EOT
  type        = string
  default     = null
}

variable "data_disk_snapshot_id" {
  description = <<-EOT
    Resource ID of the latest data-disk snapshot to restore from. Leave null
    for the bootstrap create (first run for this demo lineage), which
    provisions a fresh empty data disk instead (DEMO-01.1 §3.1/§4).
  EOT
  type        = string
  default     = null
}

variable "base_image" {
  description = "Marketplace base image reference used only for the bootstrap create (no snapshot available yet)."
  type = object({
    publisher = string
    offer     = string
    sku       = string
    version   = string
  })
  default = {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }
}

# --- Identity / access (AcrPull + Key Vault get/list, per acceptance crit.) -

variable "container_registry_id" {
  description = "Resource ID of the ACR instance the demo VM's managed identity needs AcrPull on."
  type        = string
}

variable "key_vault_id" {
  description = "Resource ID of the Key Vault the demo VM's managed identity needs secret get/list on."
  type        = string
}

variable "admin_username" {
  description = "Local admin username for the VM (no password auth; SSH key only, used solely for az vm run-command access, not direct inbound SSH per DEMO-01.2's NSG policy)."
  type        = string
  default     = "cloudmaxadmin"
}

variable "admin_ssh_public_key" {
  description = "SSH public key installed on the VM for az vm run-command access."
  type        = string
}

variable "tags" {
  description = "Common tags applied to every resource this module creates."
  type        = map(string)
  default     = {}
}
