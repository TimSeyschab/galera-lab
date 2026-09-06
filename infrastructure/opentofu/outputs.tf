output "server_public_ipv4" {
  description = "Provider-reported public IPv4 per node name, stored in state. Used as ansible_host by bootstrap/ansible/inventory/tofu_inventory.py and by scenario SSH; not a reachability check."
  value = {
    for name, server in hcloud_server.node :
    name => server.ipv4_address
  }
}

output "server_public_ipv6" {
  description = "Provider-reported first public IPv6 address per node, not the whole assigned prefix. Informational; the current Ansible inventory uses IPv4."
  value = {
    for name, server in hcloud_server.node :
    name => server.ipv6_address
  }
}

output "server_private_ipv4" {
  description = "Intended private IPv4 per node, derived from node_definitions rather than live interface discovery. Consumed by Ansible for private_ip and K3s setup; guest configuration must be verified separately."
  value = {
    for name, node in var.node_definitions :
    name => node.private_ip
  }
}

output "node_roles" {
  description = "Configured role per node from node_definitions. The dynamic Ansible inventory maps admin/worker to k3s_admin/k3s_workers; this output does not install K3s."
  value = {
    for name, node in var.node_definitions :
    name => node.role
  }
}

output "network_id" {
  description = "Provider-assigned ID of hcloud_network.private for inspection and integration; not a subnet CIDR or Kubernetes network ID."
  value       = hcloud_network.private.id
}

output "firewall_id" {
  description = "Provider-assigned ID of the shared public SSH firewall referenced by every server's firewall_ids."
  value       = hcloud_firewall.ssh.id
}
