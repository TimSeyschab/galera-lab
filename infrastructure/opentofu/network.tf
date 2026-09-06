# Underlay network for node communication, separate from K3s Pod/Service CIDRs.
resource "hcloud_network" "private" {
  name     = "${var.project_name}-network"
  ip_range = var.network_cidr
  labels   = local.common_labels
}

# Explicit subnet attachment avoids choosing an arbitrary subnet of the network.
resource "hcloud_network_subnet" "private" {
  network_id   = hcloud_network.private.id
  type         = "cloud"
  network_zone = var.network_zone
  ip_range     = var.subnet_cidr
}
