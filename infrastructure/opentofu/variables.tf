variable "project_name" {
  description = "Name prefix for network, firewall and placement group, and project label on supported resources. Does not create/select a Hetzner project or prefix node names."
  type        = string
  default     = "galera-lab"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.project_name))
    error_message = "project_name must be 3-63 characters and contain only lowercase letters, digits, and hyphens."
  }
}

variable "ssh_key_name" {
  description = "Existing SSH key name in the Hetzner project selected by HCLOUD_TOKEN; resolved in servers.tf and injected at server creation. Changing the resolved key can replace servers. No private key is managed here."
  type        = string

  validation {
    condition     = length(trimspace(var.ssh_key_name)) > 0
    error_message = "ssh_key_name must not be empty."
  }
}

variable "admin_cidr" {
  description = "Single source CIDR for public inbound TCP/22 in firewall.tf, e.g. 203.0.113.10/32. The Make helper generates IPv4 /32; direct input can use IPv6, but the current inventory connects over public IPv4."
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
  description = "Location for every server in servers.tf, default nbg1. Must match the subnet network_zone and offer the chosen server_type/image. A location change requires server replacement."
  type        = string
  default     = "nbg1"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*$", var.location))
    error_message = "location must be a non-empty Hetzner Cloud location name."
  }
}

variable "server_type" {
  description = "Compute type for all admins and workers, default cx23. Changes affect every server's capacity and cost and can power servers off during resizing; this is not a rolling Galera upgrade."
  type        = string
  default     = "cx23"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*[0-9]+$", var.server_type))
    error_message = "server_type must look like a Hetzner Cloud server type, for example cx23."
  }
}

variable "image" {
  description = "Creation image name or ID for every server, default ubuntu-24.04. Changing this replaces servers rather than upgrading their installed OS; package/bootstrap configuration belongs to Ansible."
  type        = string
  default     = "ubuntu-24.04"

  validation {
    condition     = length(trimspace(var.image)) > 0
    error_message = "image must not be empty."
  }
}

variable "network_cidr" {
  description = "Address range of hcloud_network.private in network.tf, default 10.20.0.0/16. Use IPv4 for this lab and coordinate subnet, node IPs and scenario CIDRs; this is not the K3s Pod/Service CIDR."
  type        = string
  default     = "10.20.0.0/16"

  validation {
    condition     = can(cidrhost(var.network_cidr, 0))
    error_message = "network_cidr must be a valid CIDR block."
  }
}

variable "subnet_cidr" {
  description = "Cloud subnet within network_cidr, default 10.20.0.0/24. All node_definitions.private_ip values must belong to it. Containment and reserved addresses are not checked by this variable's syntax validation."
  type        = string
  default     = "10.20.0.0/24"

  validation {
    condition     = can(cidrhost(var.subnet_cidr, 0))
    error_message = "subnet_cidr must be a valid CIDR block."
  }
}

variable "network_zone" {
  description = "Routing zone of the cloud subnet in network.tf, default eu-central. Must contain the selected server location; this relationship is not checked by the allow-list validation."
  type        = string
  default     = "eu-central"

  validation {
    condition     = contains(["eu-central", "us-east", "us-west", "ap-southeast"], var.network_zone)
    error_message = "network_zone must be a valid Hetzner Cloud network zone."
  }
}

variable "node_definitions" {
  description = "Complete map of stable server names/for_each keys to role (admin/worker) and intended private IPv4 address. Exactly one admin and at least two workers. Each added key creates a paid server; removing/renaming keys can destroy servers. Overrides replace the entire map."
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
      # cidrhost checks parseability, not IPv4 family or subnet membership.
      alltrue([
        for node in values(var.node_definitions) :
        contains(["admin", "worker"], node.role) && can(cidrhost("${node.private_ip}/32", 0))
      ]) &&
      length(distinct([for node in values(var.node_definitions) : node.private_ip])) == length(var.node_definitions)
    )
    error_message = "node_definitions must contain exactly one admin, at least two workers, valid distinct private IPv4 addresses, and only admin/worker roles."
  }
}
