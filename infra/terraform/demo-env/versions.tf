terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.90"
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
