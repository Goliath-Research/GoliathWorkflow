variable "instance_count" {
  type    = number
  default = 1
}

variable "cloud_init" {
  type        = string
  description = "cloud-init from worker-common module."
}

# Lambda Cloud worker placeholder — community provider (lambdaops/lambda), version-pinned.
# Supply-chain: review provider releases; pin in deploy/terraform/versions.tf.

output "worker_placeholder" {
  value = {
    instance_count = var.instance_count
    user_data      = var.cloud_init
    provider_note  = "Community lambda provider — no vendor SLA; pin and audit."
  }
}
