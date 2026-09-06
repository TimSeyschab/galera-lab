locals {
  # Cloud metadata only; Kubernetes node labels are configured later by Ansible.
  common_labels = {
    managed_by = "opentofu"
    phase      = "phase-1"
    project    = var.project_name
  }
}
