data "digitalocean_vpc" "factory" {
  name = var.vpc_name
}

resource "digitalocean_ssh_key" "management" {
  name       = "patchyard-conductor"
  public_key = var.management_ssh_public_key
}

locals {
  cloud_init = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    management_public_key = digitalocean_ssh_key.management.public_key
  })
}

resource "digitalocean_droplet" "control_plane" {
  name          = "factory-control.example.com"
  region        = var.region
  size          = var.control_plane_size
  image         = var.image
  vpc_uuid      = data.digitalocean_vpc.factory.id
  ssh_keys      = [digitalocean_ssh_key.management.id]
  tags          = var.existing_eta_tag_names
  user_data     = local.cloud_init
  backups       = true
  monitoring    = true
  droplet_agent = true
  ipv6          = false

  backup_policy {
    plan    = "weekly"
    weekday = "SUN"
    hour    = 8
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "digitalocean_droplet" "worker" {
  name          = "factory-worker.example.com"
  region        = var.region
  size          = var.worker_size
  image         = var.image
  vpc_uuid      = data.digitalocean_vpc.factory.id
  ssh_keys      = [digitalocean_ssh_key.management.id]
  tags          = var.existing_eta_tag_names
  user_data     = local.cloud_init
  backups       = false
  monitoring    = true
  droplet_agent = true
  ipv6          = false

  lifecycle {
    create_before_destroy = true
  }
}

resource "digitalocean_firewall" "control_plane" {
  name        = "patchyard-control-plane"
  droplet_ids = [digitalocean_droplet.control_plane.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = [var.orchestration_public_cidr]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "9100"
    source_addresses = [var.monitoring_private_cidr]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "9187"
    source_addresses = [var.monitoring_private_cidr]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "5432"
    source_addresses = [var.monitoring_private_cidr]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "all"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "all"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}

resource "digitalocean_firewall" "worker" {
  name        = "patchyard-worker"
  droplet_ids = [digitalocean_droplet.worker.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = [var.orchestration_public_cidr]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "9100"
    source_addresses = [var.monitoring_private_cidr]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "9187"
    source_addresses = [var.monitoring_private_cidr]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "all"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "all"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}
