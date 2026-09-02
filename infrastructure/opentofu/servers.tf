data "hcloud_ssh_key" "admin" {
  name = var.ssh_key_name
}

resource "hcloud_placement_group" "spread" {
  name   = "${var.project_name}-spread"
  type   = "spread"
  labels = local.common_labels
}

resource "hcloud_server" "node" {
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
    ipv4_enabled = true
    ipv6_enabled = true
  }

  network {
    subnet_id = hcloud_network_subnet.private.id
    ip        = each.value.private_ip
    alias_ips = []
  }

  backups                  = false
  shutdown_before_deletion = true

  depends_on = [
    hcloud_network_subnet.private
  ]
}
