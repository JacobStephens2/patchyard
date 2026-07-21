variable "region" {
  description = "Region shared with the fleet monitoring droplet for private scrape traffic."
  type        = string
  default     = "nyc3"
}

variable "vpc_name" {
  description = "Existing Patchyard VPC in the selected region."
  type        = string
  default     = "default-nyc3"
}

variable "image" {
  description = "Rocky Linux image used across the Patchyard fleet."
  type        = string
  default     = "rockylinux-9-x64"
}

variable "control_plane_size" {
  description = "Control-plane capacity for PostgreSQL, Rust services, Caddy, and headless Chromium."
  type        = string
  default     = "s-4vcpu-8gb"
}

variable "worker_size" {
  description = "Disposable build-worker capacity for Fieldbook, local MySQL, and Rust/PHP verification."
  type        = string
  default     = "s-8vcpu-16gb"
}

variable "management_ssh_key_name" {
  description = "Existing public identity attached at droplet creation; private material stays on orchestration."
  type        = string
  default     = "conductor@conductor.example.com"
}

variable "orchestration_public_cidr" {
  description = "Only source allowed to manage either host over SSH."
  type        = string
  default     = "142.93.121.94/32"
}

variable "monitoring_private_cidr" {
  description = "Fleet Prometheus private address; the only exporter scrape source."
  type        = string
  default     = "10.132.0.14/32"
}
