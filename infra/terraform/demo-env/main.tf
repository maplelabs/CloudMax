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
  #
  # Checks for both null AND empty string: callers that supply this value
  # via a CI step output (e.g. demo-create.yml's snapshot-lookup step) get
  # an empty string "", not an absent/null value, when no prior snapshot
  # exists -- confirmed via a real failed apply where "" was treated as
  # present, causing Terraform to attempt Copy from a null source resource
  # ID ("LinkedInvalidPropertyId: Property id 'null' ... is invalid").
  restore_from_snapshot = (
    var.os_disk_snapshot_id != null && var.os_disk_snapshot_id != "" &&
    var.data_disk_snapshot_id != null && var.data_disk_snapshot_id != ""
  )
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
  network_interface_id      = azurerm_network_interface.demo.id
  network_security_group_id = azurerm_network_security_group.demo.id
}

# --- Disks: snapshot-restored (steady-state) or fresh (bootstrap) -----------
#
# OS disk: only pre-created here for the steady-state (snapshot-restore)
# path, where `Copy` from an existing snapshot is a valid standalone managed
# disk operation that can then be attached to the VM via `Attach` (see VM
# resource below). The bootstrap path (no snapshot yet) does NOT pre-create
# an OS disk here -- `FromImage` against a marketplace image is only valid
# as part of VM creation itself (it needs the VM's osProfile to provision
# the OS), not as a standalone azurerm_managed_disk. For bootstrap, the VM
# resource creates its OS disk inline from `var.base_image`.

resource "azurerm_managed_disk" "os" {
  count                = local.restore_from_snapshot ? 1 : 0
  name                 = "${local.name_prefix}-os-disk"
  resource_group_name  = data.azurerm_resource_group.demo.name
  location             = var.location
  storage_account_type = "Standard_LRS"
  create_option        = "Copy"
  source_resource_id   = var.os_disk_snapshot_id
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
#
# Defined via azapi_resource (raw Microsoft.Compute/virtualMachines), not
# azurerm_linux_virtual_machine, because the steady-state (snapshot-restore)
# path needs storageProfile.osDisk.createOption = "Attach" against the
# pre-existing azurerm_managed_disk.os[0] -- azurerm_linux_virtual_machine's
# os_disk block cannot attach an existing disk, it only ever provisions a new
# one. The bootstrap path instead sets createOption = "FromImage" with an
# inline imageReference, letting the VM provision its own fresh OS disk.

resource "azapi_resource" "demo_vm" {
  type      = "Microsoft.Compute/virtualMachines@2023-09-01"
  name      = "${local.name_prefix}-vm"
  location  = var.location
  parent_id = data.azurerm_resource_group.demo.id
  tags      = local.common_tags

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {
      hardwareProfile = {
        vmSize = var.vm_size
      }

      # osProfile is only required/valid when the OS disk is provisioned
      # fresh (bootstrap, FromImage) -- it must be omitted entirely when
      # attaching a pre-existing (already-provisioned) OS disk.
      osProfile = local.restore_from_snapshot ? null : {
        computerName  = "${local.name_prefix}-vm"
        adminUsername = var.admin_username
        # Only applies to the bootstrap (FromImage) path -- a future
        # snapshot-restored VM already has these baked in from this same
        # cloud-init having run once during the original bootstrap.
        #
        # Confirmed via a real deployed VM that the stock marketplace Ubuntu
        # image has neither Docker nor the Azure CLI preinstalled (the
        # deploy workflow's `docker compose ...` / `az login --identity`
        # commands silently no-op'd as "command not found", masked by a
        # separate bug where `set -euo pipefail` failed under dash and so
        # never actually stopped the script on error -- see demo-create.yml's
        # deploy step fix for that part).
        customData = base64encode(<<-CLOUDINIT
          #cloud-config
          package_update: true
          packages:
            - docker.io
            - docker-compose-v2
            - git
          runcmd:
            - systemctl enable --now docker
            - curl -sL https://aka.ms/InstallAzureCLIDeb | bash
          CLOUDINIT
        )
        linuxConfiguration = {
          disablePasswordAuthentication = true
          ssh = {
            publicKeys = [
              {
                path    = "/home/${var.admin_username}/.ssh/authorized_keys"
                keyData = var.admin_ssh_public_key
              }
            ]
          }
        }
      }

      # Both branches must be the exact same shape (same keys, nested
      # objects included) -- Terraform requires the true/false results of a
      # conditional expression to unify to one type. Unused fields are left
      # `null`; azapi omits null attributes when serializing the ARM request
      # body, so this doesn't change what's actually sent to Azure.
      storageProfile = {
        # imageReference belongs directly under storageProfile, not nested
        # inside storageProfile.osDisk -- confirmed via a real failed apply:
        # azapi's embedded schema validation rejected
        # `properties.storageProfile.osDisk.imageReference` outright
        # ("is not expected here").
        imageReference = local.restore_from_snapshot ? null : {
          publisher = var.base_image.publisher
          offer     = var.base_image.offer
          sku       = var.base_image.sku
          version   = var.base_image.version
        }

        osDisk = {
          createOption = local.restore_from_snapshot ? "Attach" : "FromImage"
          osType       = local.restore_from_snapshot ? "Linux" : null
          caching      = "ReadWrite"
          diskSizeGB   = local.restore_from_snapshot ? null : var.os_disk_size_gb
          managedDisk = {
            id                 = local.restore_from_snapshot ? azurerm_managed_disk.os[0].id : null
            storageAccountType = local.restore_from_snapshot ? null : "Standard_LRS"
          }
        }

        dataDisks = [
          {
            lun          = 0
            createOption = "Attach"
            caching      = "ReadWrite"
            managedDisk = {
              id = azurerm_managed_disk.data.id
            }
          }
        ]
      }

      networkProfile = {
        networkInterfaces = [
          {
            id = azurerm_network_interface.demo.id
          }
        ]
      }
    }
  }

  # Re-running apply against an already-provisioned demo must not recreate
  # the VM due to image/OS-disk drift (idempotency, per acceptance criteria).
  lifecycle {
    ignore_changes = [body.properties.storageProfile.imageReference]
  }

  depends_on = [
    azurerm_network_interface_security_group_association.demo,
  ]
}

# --- Managed identity access: AcrPull + Key Vault get/list ------------------

resource "azurerm_role_assignment" "acr_pull" {
  scope                = var.container_registry_id
  role_definition_name = "AcrPull"
  principal_id         = azapi_resource.demo_vm.identity[0].principal_id
}

# cloudmax-kv uses Azure RBAC authorization (not the legacy Access Policy
# model) -- Azure rejects azurerm_key_vault_access_policy writes against an
# RBAC-mode vault outright, so the VM's managed identity is granted via a
# role assignment instead. "Key Vault Secrets User" is the least-privilege
# built-in role covering read-only secret Get/List, matching the original
# Get/List-only intent.
resource "azurerm_role_assignment" "demo_vm_kv_secrets" {
  scope                = var.key_vault_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azapi_resource.demo_vm.identity[0].principal_id
}
