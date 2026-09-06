terraform {
  # CLI compatibility floor, not an exact CLI version pin.
  required_version = ">= 1.8.0"

  required_providers {
    hcloud = {
      source = "hetznercloud/hcloud"
      # Allows >= 1.68.0 and < 2.0.0; .terraform.lock.hcl records the exact selection.
      version = "~> 1.68"
    }
  }
}

# Authentication is supplied only through HCLOUD_TOKEN in the process environment.
provider "hcloud" {}
