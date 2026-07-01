terraform {
  backend "azurerm" {
    resource_group_name  = "rg-methyl-tfstate"
    storage_account_name = "stmethyltfstate"
    container_name       = "tfstate"
    key                  = "dev.terraform.tfstate"
  }
}

module "control_plane" {
  source       = "../../modules/control-plane-azure"
  environment  = var.environment
  location     = var.location
  sql_admin_login = var.sql_admin_login
  key_vault_name  = var.key_vault_name
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "location" {
  type    = string
  default = "eastus"
}

variable "sql_admin_login" {
  type    = string
  default = "methyladmin"
}

variable "key_vault_name" {
  type    = string
  default = "kv-methyl-dev"
}
