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
    Azure VM size for the demo host. Defaults to Standard_F8s_v2 (8 vCPU /
    16 GiB) to fit the combined CloudMax + fault-injector hotel-reservation-
    application footprint (deploy_hotel_reservation_app defaults to true in
    demo-create.yml as of this change, adding ~20 extra containers on top of
    CloudMax's own 8). `az vm list-usage --location eastus2` showed 10 cores
    of quota in standardFSv2Family (0 in use) at the time this default was
    set -- 8 vCPU fits with headroom to spare. The previous default,
    Standard_B2s (2 vCPU / 4 GiB, Standard BS Family), is no longer large
    enough now that the hotel app is deployed by default; it remains a valid
    override for CloudMax-only demos (pass a smaller vm_size explicitly).
    Revisit if/when a quota increase is approved for a different family (see
    DEMO-01.1's cost model section).
  EOT
  type        = string
  default     = "Standard_F8s_v2"
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

variable "public_ip_name" {
  description = <<-EOT
    Name of an EXISTING static Standard-SKU public IP resource (in
    resource_group_name) to attach to the demo VM, instead of creating a new
    per-demo IP. Defaults to "cloudmax-vm-ip" (135.232.101.211 at the time
    this default was set), a pre-reserved address that fault-injector's
    hotel-reservation-application frontend has hardcoded as its backend API
    URL (REACT_APP_API_URL, baked in at build time, not overridable at
    runtime) -- so the demo VM must bind this specific IP for that app's
    frontend-to-backend calls to work without a custom rebuild.

    Referenced via a data source (see main.tf), never a Terraform-managed
    resource -- terraform destroy therefore never deletes it; only resources
    Terraform itself creates are ever destroyed.

    Set to "" (empty string) to fall back to the old behavior of creating a
    fresh, Terraform-managed, per-demo static IP instead (named
    "demo-<demo_name>-pip") -- required for running more than one demo
    concurrently, since one public IP can only be attached to one NIC at a
    time.
  EOT
  type        = string
  default     = "cloudmax-vm-ip"
}

variable "tags" {
  description = "Common tags applied to every resource this module creates."
  type        = map(string)
  default     = {}
}
