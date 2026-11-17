# DEMO-01.2 — Terraform module: ephemeral demo environment
#
# Provisions a single demo VM with OS + data disks restored from the latest
# snapshot (steady-state) or a fresh base image (bootstrap create, no
# snapshot exists yet — see DEMO-01.1 §3.1/§4), attached to a static public
# IP and an NSG that allows only 443/80 inbound (no open SSH — access is via
# `az vm run-command`, per DEMO-01.2 acceptance criteria).
#
# Re-running `terraform apply` against an already-provisioned demo is
# idempotent: every resource is named deterministically from `var.demo_name`,
# so Terraform converges to the same state rather than duplicating resources.

locals {
  name_prefix = "demo-${var.demo_name}"

  common_tags = merge(var.tags, {
    managed-by = "terraform"
    component  = "cloudmax-demo-env"
    demo-name  = var.demo_name
  })

  # Bootstrap vs. steady-state: restore from snapshot if one was supplied,
  # otherwise fall back to a fresh disk (DEMO-01.1 §3.1).
  restore_from_snapshot = var.os_disk_snapshot_id != null && var.data_disk_snapshot_id != null
}

data "azurerm_resource_group" "demo" {
  name = var.resource_group_name
}

# --- Networking --------------------------------------------------------------

resource "azurerm_public_ip" "demo" {
  name                = "${local.name_prefix}-pip"
  resource_group_name = data.azurerm_resource_group.demo.name
  location            = var.location
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.common_tags
}

resource "azurerm_network_security_group" "demo" {
  name                = "${local.name_prefix}-nsg"
  resource_group_name = data.azurerm_resource_group.demo.name
  location            = var.location
  tags                = local.common_tags

  security_rule {
    name                       = "allow-https"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-http"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # No SSH rule by design — management access is via `az vm run-command`,
  # not direct inbound SSH (DEMO-01.2 acceptance criteria).
}

resource "azurerm_virtual_network" "demo" {
  name                = "${local.name_prefix}-vnet"
  resource_group_name = data.azurerm_resource_group.demo.name
  location            = var.location
  address_space       = ["10.90.0.0/24"]
  tags                = local.common_tags
}

resource "azurerm_subnet" "demo" {
  name                 = "${local.name_prefix}-subnet"
  resource_group_name  = data.azurerm_resource_group.demo.name
  virtual_network_name = azurerm_virtual_network.demo.name
  address_prefixes     = ["10.90.0.0/27"]
}

resource "azurerm_network_interface" "demo" {
  name                = "${local.name_prefix}-nic"
  resource_group_name = data.azurerm_resource_group.demo.name
  location            = var.location
  tags                = local.common_tags

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.demo.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.demo.id
  }
}

resource "azurerm_network_interface_security_group_association" "demo" {
  network_interface_id     = azurerm_network_interface.demo.id
  network_security_group_id = azurerm_network_security_group.demo.id
}

# --- Disks: snapshot-restored (steady-state) or fresh (bootstrap) -----------

resource "azurerm_managed_disk" "os" {
  name                 = "${local.name_prefix}-os-disk"
  resource_group_name  = data.azurerm_resource_group.demo.name
  location             = var.location
  storage_account_type = "Standard_LRS"
  create_option        = local.restore_from_snapshot ? "Copy" : "FromImage"
  source_resource_id   = local.restore_from_snapshot ? var.os_disk_snapshot_id : null
  disk_size_gb         = local.restore_from_snapshot ? null : var.os_disk_size_gb
  os_type              = "Linux"
  tags                 = local.common_tags
}

resource "azurerm_managed_disk" "data" {
  name                 = "${local.name_prefix}-data-disk"
  resource_group_name  = data.azurerm_resource_group.demo.name
  location             = var.location
  storage_account_type = "Standard_LRS"
  create_option        = local.restore_from_snapshot ? "Copy" : "Empty"
  source_resource_id   = local.restore_from_snapshot ? var.data_disk_snapshot_id : null
  disk_size_gb         = var.data_disk_size_gb
  tags                 = local.common_tags
}

# --- VM -----------------------------------------------------------------------

resource "azurerm_linux_virtual_machine" "demo" {
  name                = "${local.name_prefix}-vm"
  resource_group_name = data.azurerm_resource_group.demo.name
  location            = var.location
  size                = var.vm_size
  admin_username      = var.admin_username
  tags                = local.common_tags

  network_interface_ids = [azurerm_network_interface.demo.id]

  admin_ssh_key {
    username   = var.admin_username
    public_key = var.admin_ssh_public_key
  }

  # KNOWN LIMITATION (flagged for review, not yet resolved in this draft):
  # azurerm_linux_virtual_machine's `os_disk` block always provisions a NEW
  # managed disk for the VM; it cannot attach the pre-existing
  # `azurerm_managed_disk.os` (snapshot-restored or fresh) created above as
  # the VM's actual OS disk. Resolving the steady-state "restore OS disk from
  # snapshot" path correctly requires one of:
  #   (a) azapi_resource for Microsoft.Compute/virtualMachines with an
  #       explicit `storageProfile.osDisk.managedDisk.id` pointing at
  #       azurerm_managed_disk.os.id, or
  #   (b) building a custom azurerm_image from the OS snapshot and using that
  #       as the VM's os_disk source image.
  # Tracked as a follow-up before this module is used for a real steady-state
  # (snapshot-restore) create; bootstrap (FromImage) path below is unaffected.
  os_disk {
    name                 = "${local.name_prefix}-os-disk-attached"
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  dynamic "source_image_reference" {
    for_each = local.restore_from_snapshot ? [] : [var.base_image]
    content {
      publisher = source_image_reference.value.publisher
      offer     = source_image_reference.value.offer
      sku       = source_image_reference.value.sku
      version   = source_image_reference.value.version
    }
  }

  identity {
    type = "SystemAssigned"
  }

  lifecycle {
    # Re-running apply against an already-provisioned demo must not recreate
    # the VM due to disk/image drift (idempotency, per acceptance criteria).
    ignore_changes = [source_image_reference]
  }
}

resource "azurerm_virtual_machine_data_disk_attachment" "data" {
  managed_disk_id    = azurerm_managed_disk.data.id
  virtual_machine_id = azurerm_linux_virtual_machine.demo.id
  lun                = 0
  caching            = "ReadWrite"
}

# --- Managed identity access: AcrPull + Key Vault get/list ------------------

resource "azurerm_role_assignment" "acr_pull" {
  scope                = var.container_registry_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_linux_virtual_machine.demo.identity[0].principal_id
}

resource "azurerm_key_vault_access_policy" "demo_vm" {
  key_vault_id = var.key_vault_id
  tenant_id    = azurerm_linux_virtual_machine.demo.identity[0].tenant_id
  object_id    = azurerm_linux_virtual_machine.demo.identity[0].principal_id

  secret_permissions = ["Get", "List"]
}
