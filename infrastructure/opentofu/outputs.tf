output "server_public_ipv4" {
  description = "Public IPv4 addresses of all configured K3s nodes, keyed by node name."
  value = {
    for name, server in hcloud_server.node :
    name => server.ipv4_address
  }
}

output "server_public_ipv6" {
  description = "Public IPv6 addresses of all configured K3s nodes, keyed by node name."
  value = {
    for name, server in hcloud_server.node :
    name => server.ipv6_address
  }
}

output "server_private_ipv4" {
  description = "Fixed private IPv4 addresses assigned to all configured K3s nodes, keyed by node name."
  value = {
    for name, node in var.node_definitions :
    name => node.private_ip
  }
}

output "node_roles" {
  description = "K3s role assigned to each configured node, keyed by node name."
  value = {
    for name, node in var.node_definitions :
    name => node.role
  }
}

output "network_id" {
  description = "Hetzner Cloud private network ID."
  value       = hcloud_network.private.id
}

output "firewall_id" {
  description = "Hetzner Cloud firewall ID attached to all nodes."
  value       = hcloud_firewall.ssh.id
}
