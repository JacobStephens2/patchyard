variable "eta_zone_id" {
  description = "Route 53 hosted zone for example.com."
  type        = string
  default     = "Z3O3FWL0L1O9AE"
}

variable "control_plane_ipv4" {
  description = "Generated from the DigitalOcean state by infra/tofu.sh; never hand-transcribed."
  type        = string

  validation {
    condition     = can(cidrhost("${var.control_plane_ipv4}/32", 0))
    error_message = "control_plane_ipv4 must be an IPv4 address."
  }
}
