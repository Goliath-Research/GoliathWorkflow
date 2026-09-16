variable "release_bundle_url" {
  type        = string
  description = "HTTPS URL to a scripts/runtime seed tarball (extracted to /opt/methyl). Runtime remains /work/goliath/current on QNAP."
}

variable "release_bundle_sha256" {
  type        = string
  description = "SHA-256 checksum of the seed tarball."
}

variable "gateway_api_base" {
  type        = string
  description = "Worker WORKER_API_BASE / METHYL_API_BASE (gateway /v1 URL)."
}

variable "cluster_key" {
  type        = string
  default     = "goliath"
  description = "wf.cluster cluster_key for registration."
}

variable "goliath_root" {
  type        = string
  default     = "/work/goliath"
  description = "Shared GoliathOmics root on QNAP-mounted /work."
}

variable "prepare_only" {
  type        = bool
  default     = true
  description = "If true (default), cloud-init runs join prepare only; Arc approve + finish-enroll are operator follow-ups."
}

variable "finish_enroll_on_boot" {
  type        = bool
  default     = false
  description = "If true and prepare_only is false, cloud-init enrolls when Arc is already Connected (uncommon)."
}

output "cloud_init" {
  value       = local.cloud_init
  description = "cloud-init user_data for worker VMs."
}

locals {
  provision_flags = var.prepare_only ? "--prepare-only" : (
    var.finish_enroll_on_boot ? "--finish-enroll --require-arc --enroll-worker --enable-systemd --detect-capabilities" : "--require-arc --enroll-worker --enable-systemd --detect-capabilities"
  )

  cloud_init = <<-EOT
    #cloud-config
    write_files:
      - path: /etc/methyl/bootstrap.env
        permissions: '0644'
        content: |
          RELEASE_BUNDLE_URL=${var.release_bundle_url}
          RELEASE_BUNDLE_SHA256=${var.release_bundle_sha256}
          WORKER_API_BASE=${var.gateway_api_base}
          METHYL_API_BASE=${var.gateway_api_base}
          CLUSTER_KEY=${var.cluster_key}
          GOLIATH_ROOT=${var.goliath_root}
      - path: /usr/local/sbin/methyl-worker-cloud-init.sh
        permissions: '0755'
        content: |
          #!/bin/bash
          set -euo pipefail
          # shellcheck disable=SC1091
          source /etc/methyl/bootstrap.env
          export WORKER_API_BASE METHYL_API_BASE CLUSTER_KEY GOLIATH_ROOT
          mkdir -p /opt/methyl /var/log/methyl
          curl -fsSL -o /tmp/goliath-seed.tgz "$RELEASE_BUNDLE_URL"
          echo "$RELEASE_BUNDLE_SHA256  /tmp/goliath-seed.tgz" | sha256sum -c -
          tar -xzf /tmp/goliath-seed.tgz -C /opt/methyl
          SCRIPTS=""
          for cand in /opt/methyl/scripts /opt/methyl/runtime-bundle/scripts "$GOLIATH_ROOT/current/runtime-bundle/scripts"; do
            if [[ -x "$cand/provision_worker_node.sh" ]]; then
              SCRIPTS="$cand"
              break
            fi
          done
          if [[ -z "$SCRIPTS" ]]; then
            echo "provision_worker_node.sh not found under /opt/methyl or $GOLIATH_ROOT/current" >&2
            exit 1
          fi
          bash "$SCRIPTS/preflight_worker_join.sh" --root "$GOLIATH_ROOT" --gpu --require-current --require-api
          # Default: join-only prepare (Docker/CTK/host). Arc approval + finish-enroll are manual.
          # See docs/deployment/lambda_worker_join.md
          bash "$SCRIPTS/provision_worker_node.sh" \
            --gpu --join-mode auto --cluster "$CLUSTER_KEY" \
            --root "$GOLIATH_ROOT" \
            ${provision_flags}
    runcmd:
      - [ -x /usr/local/sbin/methyl-worker-cloud-init.sh ]
      - /usr/local/sbin/methyl-worker-cloud-init.sh
  EOT
}
