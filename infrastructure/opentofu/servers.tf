# Read an existing public-key object; its lifecycle stays outside this module.
data "hcloud_ssh_key" "admin" {
  name = var.ssh_key_name
}

# Separates VMs on physical hosts, not Galera pods within one worker VM.
resource "hcloud_placement_group" "spread" {
  name   = "${var.project_name}-spread"
  type   = "spread"
  labels = local.common_labels
}

resource "hcloud_server" "node" {
  # Keys are persistent resource identities, e.g. node["k3s-worker-1"].
  for_each = var.node_definitions

  name        = each.key
  image       = var.image
  server_type = var.server_type
  location    = var.location
  labels = merge(local.common_labels, {
    role = each.value.role
  })

  ssh_keys           = [data.hcloud_ssh_key.admin.id]
  firewall_ids       = [hcloud_firewall.ssh.id]
  placement_group_id = hcloud_placement_group.spread.id

  public_net {
    # Public IPv4 is used by Ansible/SSH; enabling an IP does not open firewall ports.
    ipv4_enabled = true
    ipv6_enabled = true
  }

  network {
    subnet_id = hcloud_network_subnet.private.id
    ip        = each.value.private_ip
    # Explicit empty aliases avoid the network diff issue documented by the provider.
    alias_ips = []
  }

  # Graceful shutdown attempt before deletion is not a backup or a Kubernetes drain.
  backups                  = false
  shutdown_before_deletion = true

  # Also expressed by subnet_id above; kept as an explicit attachment prerequisite.
  depends_on = [
    hcloud_network_subnet.private
  ]
}
