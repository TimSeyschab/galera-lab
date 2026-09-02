locals {
  common_labels = {
    managed_by = "opentofu"
    phase      = "phase-1"
    project    = var.project_name
  }
}

