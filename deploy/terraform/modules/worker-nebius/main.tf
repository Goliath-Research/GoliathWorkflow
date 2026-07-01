variable "instance_count" {
  type    = number
  default = 1
}

variable "cloud_init" {
  type        = string
  description = "cloud-init from worker-common module."
}

# Nebius GPU worker placeholder — wire official nebius/nebius resources in operator env.
# Instance types, networks, and disks are set per deployment tfvars.

output "worker_placeholder" {
  value = {
    instance_count = var.instance_count
    user_data      = var.cloud_init
  }
}
