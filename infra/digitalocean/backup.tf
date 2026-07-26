resource "digitalocean_spaces_key" "backup_management" {
  name = "patchyard-backup-management"

  grant {
    bucket     = ""
    permission = "fullaccess"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "digitalocean_spaces_bucket" "factory_backups" {
  name          = "patchyard-backups"
  region        = var.region
  acl           = "private"
  force_destroy = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    id      = "factory-backup-retention"
    enabled = true
    prefix  = "generations/"

    expiration {
      days = 90
    }

    noncurrent_version_expiration {
      days = 7
    }

    abort_incomplete_multipart_upload_days = 1
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [digitalocean_spaces_key.backup_management]
}

resource "digitalocean_spaces_key" "factory_backup_runtime" {
  name = "patchyard-backup-runtime"

  grant {
    bucket     = digitalocean_spaces_bucket.factory_backups.name
    permission = "readwrite"
  }
}

# The control plane receives only this public half. Recovery obtains the
# OpenSSH private half from the client-side-encrypted OpenTofu state.
resource "tls_private_key" "factory_backup_recovery" {
  algorithm = "ED25519"
}

output "factory_backup_bucket" {
  value = digitalocean_spaces_bucket.factory_backups.name
}

output "factory_backup_endpoint" {
  value = "https://${digitalocean_spaces_bucket.factory_backups.endpoint}"
}

output "factory_backup_runtime_access_key" {
  value     = digitalocean_spaces_key.factory_backup_runtime.access_key
  sensitive = true
}

output "factory_backup_runtime_secret_key" {
  value     = digitalocean_spaces_key.factory_backup_runtime.secret_key
  sensitive = true
}

output "factory_backup_management_access_key" {
  value     = digitalocean_spaces_key.backup_management.access_key
  sensitive = true
}

output "factory_backup_management_secret_key" {
  value     = digitalocean_spaces_key.backup_management.secret_key
  sensitive = true
}

output "factory_backup_age_recipient" {
  value = trimspace(tls_private_key.factory_backup_recovery.public_key_openssh)
}

output "factory_backup_age_identity" {
  value     = tls_private_key.factory_backup_recovery.private_key_openssh
  sensitive = true
}
