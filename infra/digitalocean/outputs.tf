output "control_plane_ipv4" {
  description = "Public address consumed by Route 53 and orchestration break-glass access."
  value       = digitalocean_droplet.control_plane.ipv4_address
}

output "control_plane_private_ipv4" {
  description = "Private address consumed by monitoring and later factory services."
  value       = digitalocean_droplet.control_plane.ipv4_address_private
}

output "worker_ipv4" {
  value = digitalocean_droplet.worker.ipv4_address
}

output "worker_private_ipv4" {
  value = digitalocean_droplet.worker.ipv4_address_private
}

output "restore_drill_ipv4" {
  description = "Public break-glass address of the temporary recovery drill target, or null when disabled."
  value       = var.restore_drill_enabled ? digitalocean_droplet.restore_drill[0].ipv4_address : null
}

output "restore_drill_private_ipv4" {
  description = "Private address of the temporary recovery drill target, or null when disabled."
  value       = var.restore_drill_enabled ? digitalocean_droplet.restore_drill[0].ipv4_address_private : null
}

output "ansible_inventory" {
  description = "Dynamic inventory consumed verbatim by infra/ansible/inventory/tofu.sh."
  value = {
    all = {
      children = ["control_plane", "worker"]
      vars = {
        ansible_user                 = "conductor"
        ansible_ssh_private_key_file = "/var/lib/conductor/.ssh/id_ed25519"
        monitoring_private_cidr      = var.monitoring_private_cidr
        orchestration_public_cidr    = var.orchestration_public_cidr
        control_plane_private_cidr   = "${digitalocean_droplet.control_plane.ipv4_address_private}/32"
      }
    }
    control_plane = {
      hosts = [digitalocean_droplet.control_plane.name]
    }
    worker = {
      hosts = [digitalocean_droplet.worker.name]
    }
    _meta = {
      hostvars = {
        (digitalocean_droplet.control_plane.name) = {
          ansible_host = digitalocean_droplet.control_plane.ipv4_address
          private_ip   = digitalocean_droplet.control_plane.ipv4_address_private
          factory_role = "control-plane"
        }
        (digitalocean_droplet.worker.name) = {
          ansible_host = digitalocean_droplet.worker.ipv4_address
          private_ip   = digitalocean_droplet.worker.ipv4_address_private
          factory_role = "worker"
        }
      }
    }
  }
}
