terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    nebius = {
      source  = "nebius/nebius"
      version = "~> 0.4"
    }
    lambda = {
      source  = "lambdaops/lambda"
      version = "1.5.0"
    }
  }
}
