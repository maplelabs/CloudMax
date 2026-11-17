terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.90"
    }
    # Used only for the VM resource itself (Microsoft.Compute/virtualMachines),
    # so the steady-state (snapshot-restored) OS disk can be attached directly
    # via storageProfile.osDisk.managedDisk.id -- azurerm_linux_virtual_machine
    # does not expose this (see main.tf for details).
    azapi = {
      source  = "Azure/azapi"
      version = "~> 1.13"
    }
  }

  # Remote state so Terraform state isn't lost between CI runs (DEMO-01.2
  # acceptance criteria). Backend config values (storage account, container,
  # key) are supplied at `terraform init` time via -backend-config, so this
  # stays environment-agnostic and contains no secrets/identifiers.
  backend "azurerm" {}
}

provider "azurerm" {
  features {}
}
