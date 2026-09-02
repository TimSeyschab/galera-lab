variable "project_name" {
  description = "Name prefix and project label for all Phase 1 Hetzner Cloud resources."
  type        = string
  default     = "galera-lab"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.project_name))
    error_message = "project_name must be 3-63 characters and contain only lowercase letters, digits, and hyphens."
  }
}

variable "ssh_key_name" {
  description = "Name of the existing Hetzner Cloud SSH key to attach to all nodes. The private key is not managed here."
  type        = string

  validation {
    condition     = length(trimspace(var.ssh_key_name)) > 0
    error_message = "ssh_key_name must not be empty."
  }
}

variable "admin_cidr" {
  description = "Single IPv4 or IPv6 CIDR allowed to reach SSH on the public interfaces, for example 203.0.113.10/32."
  type        = string

  validation {
    condition = (
      can(cidrhost(var.admin_cidr, 0)) &&
      !contains(["0.0.0.0/0", "::/0"], var.admin_cidr)
    )
    error_message = "admin_cidr must be a valid IPv4 or IPv6 CIDR and must not allow the whole internet."
  }
}

variable "location" {
  description = "Hetzner Cloud location for all servers. Use locations such as nbg1, fsn1, hel1, ash, hil, or sin."
  type        = string
  default     = "nbg1"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*$", var.location))
    error_message = "location must be a non-empty Hetzner Cloud location name."
  }
}

variable "server_type" {
  description = "Hetzner Cloud server type for all nodes. The default cx23 keeps Phase 1 cost low."
  type        = string
  default     = "cx23"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*[0-9]+$", var.server_type))
    error_message = "server_type must look like a Hetzner Cloud server type, for example cx23."
  }
}

variable "image" {
  description = "Operating system image for all nodes."
  type        = string
  default     = "ubuntu-24.04"

  validation {
    condition     = length(trimspace(var.image)) > 0
    error_message = "image must not be empty."
  }
}

variable "network_cidr" {
  description = "Private Hetzner Cloud network CIDR for the lab."
  type        = string
  default     = "10.20.0.0/16"

  validation {
    condition     = can(cidrhost(var.network_cidr, 0))
    error_message = "network_cidr must be a valid CIDR block."
  }
}

variable "subnet_cidr" {
  description = "Private subnet CIDR used by the three lab nodes."
  type        = string
  default     = "10.20.0.0/24"

  validation {
    condition     = can(cidrhost(var.subnet_cidr, 0))
    error_message = "subnet_cidr must be a valid CIDR block."
  }
}

variable "network_zone" {
  description = "Hetzner Cloud network zone for the private subnet."
  type        = string
  default     = "eu-central"

  validation {
    condition     = contains(["eu-central", "us-east", "us-west", "ap-southeast"], var.network_zone)
    error_message = "network_zone must be a valid Hetzner Cloud network zone."
  }
}

variable "node_definitions" {
  description = "Explicit mapping of K3s node names to roles and fixed private IPv4 addresses. Add worker entries to expand the cluster; each entry creates a paid server."
  type = map(object({
    role       = string
    private_ip = string
  }))
  default = {
    k3s-admin = {
      role       = "admin"
      private_ip = "10.20.0.2"
    }
    k3s-worker-1 = {
      role       = "worker"
      private_ip = "10.20.0.3"
    }
    k3s-worker-2 = {
      role       = "worker"
      private_ip = "10.20.0.4"
    }
  }

  validation {
    condition = (
      length(var.node_definitions) >= 3 &&
      length([for node in values(var.node_definitions) : node if node.role == "admin"]) == 1 &&
      length([for node in values(var.node_definitions) : node if node.role == "worker"]) >= 2 &&
      alltrue([
        for node in values(var.node_definitions) :
        contains(["admin", "worker"], node.role) && can(cidrhost("${node.private_ip}/32", 0))
      ]) &&
      length(distinct([for node in values(var.node_definitions) : node.private_ip])) == length(var.node_definitions)
    )
    error_message = "node_definitions must contain exactly one admin, at least two workers, valid distinct private IPv4 addresses, and only admin/worker roles."
  }
}
