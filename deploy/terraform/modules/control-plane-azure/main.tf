variable "environment" {
  type        = string
  description = "Deployment environment name (dev, prod)."
}

variable "location" {
  type        = string
  description = "Azure region for control plane."
  default     = "eastus"
}

variable "gateway_allowed_worker_cidrs" {
  type        = list(string)
  description = "CIDR blocks allowed to POST /v1/workers/* on the gateway."
  default     = []
}

variable "sql_admin_login" {
  type        = string
  description = "Azure SQL admin login (use Key Vault secret for password)."
}

variable "key_vault_name" {
  type        = string
  description = "Key Vault name for worker tokens and cloud API keys."
}

output "gateway_fqdn" {
  value       = azurerm_public_ip.gateway.fqdn
  description = "Gateway public hostname (TLS terminates on nginx VM)."
}

output "sql_server_fqdn" {
  value       = azurerm_mssql_server.wf.fully_qualified_domain_name
  description = "Azure SQL FQDN (private endpoint only)."
}

output "key_vault_uri" {
  value       = azurerm_key_vault.main.vault_uri
  description = "Key Vault URI for worker token bootstrap."
}

resource "azurerm_resource_group" "control" {
  name     = "rg-methyl-${var.environment}-control"
  location = var.location
}

resource "azurerm_public_ip" "gateway" {
  name                = "pip-methyl-gateway-${var.environment}"
  location            = azurerm_resource_group.control.location
  resource_group_name = azurerm_resource_group.control.name
  allocation_method   = "Static"
  sku                 = "Standard"
  domain_name_label   = "methyl-gw-${var.environment}"
}

resource "azurerm_network_security_group" "gateway" {
  name                = "nsg-methyl-gateway-${var.environment}"
  location            = azurerm_resource_group.control.location
  resource_group_name = azurerm_resource_group.control.name

  security_rule {
    name                       = "allow-https-workers"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefixes    = length(var.gateway_allowed_worker_cidrs) > 0 ? var.gateway_allowed_worker_cidrs : ["0.0.0.0/0"]
    destination_address_prefix = "*"
  }
}

resource "azurerm_mssql_server" "wf" {
  name                         = "sql-methyl-${var.environment}"
  location                     = azurerm_resource_group.control.location
  resource_group_name          = azurerm_resource_group.control.name
  version                      = "12.0"
  administrator_login          = var.sql_admin_login
  administrator_login_password = "REPLACE_VIA_KEYVAULT_OR_VAR"
  minimum_tls_version          = "1.2"
  public_network_access_enabled = false
}

resource "azurerm_key_vault" "main" {
  name                       = var.key_vault_name
  location                   = azurerm_resource_group.control.location
  resource_group_name        = azurerm_resource_group.control.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = true
  rbac_authorization_enabled = true
}

data "azurerm_client_config" "current" {}
