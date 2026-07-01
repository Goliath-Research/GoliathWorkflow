variable "release_bundle_url" {
  type        = string
  description = "HTTPS URL to epimethyl release tarball."
}

variable "release_bundle_sha256" {
  type        = string
  description = "SHA-256 checksum of release bundle."
}

variable "gateway_api_base" {
  type        = string
  description = "Worker METHYL_API_BASE (gateway /v1 URL)."
}

variable "key_vault_uri" {
  type        = string
  description = "Key Vault URI for WORKER_TOKEN secret."
}

variable "cluster_key" {
  type        = string
  default     = "epimethyl"
  description = "wf.cluster cluster_key for registration."
}

output "cloud_init" {
  value       = local.cloud_init
  description = "cloud-init user_data for worker VMs."
}

locals {
  cloud_init = <<-EOT
    #cloud-config
    write_files:
      - path: /etc/methyl/bootstrap.env
        permissions: '0644'
        content: |
          RELEASE_BUNDLE_URL=${var.release_bundle_url}
          RELEASE_BUNDLE_SHA256=${var.release_bundle_sha256}
          METHYL_API_BASE=${var.gateway_api_base}
          KEY_VAULT_URI=${var.key_vault_uri}
          CLUSTER_KEY=${var.cluster_key}
    runcmd:
      - curl -fsSL -o /tmp/epimethyl.tgz "$RELEASE_BUNDLE_URL"
      - echo "${var.release_bundle_sha256}  /tmp/epimethyl.tgz" | sha256sum -c -
      - bash /opt/methyl/scripts/provision_worker_node.sh --register-worker --enable-systemd --detect-capabilities --require-arc
    EOT
}
