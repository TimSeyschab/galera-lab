# Public-interface policy: allow inbound SSH only. No outbound allow-list is defined.
resource "hcloud_firewall" "ssh" {
  name   = "${var.project_name}-ssh"
  labels = local.common_labels

  rule {
    direction   = "in"
    protocol    = "tcp"
    port        = "22"
    source_ips  = [var.admin_cidr]
    description = "SSH from admin CIDR only"
  }
}
