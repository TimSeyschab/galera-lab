#!/usr/bin/env python3
"""Build an Ansible inventory from OpenTofu outputs without storing credentials."""

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TOFU_DIR = ROOT / "infrastructure" / "opentofu"
ARTIFACT_DIR = ROOT / ".artifacts"
KNOWN_HOSTS = ARTIFACT_DIR / "known_hosts"


def load_outputs():
    result = subprocess.run(
        ["tofu", f"-chdir={TOFU_DIR}", "output", "-json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error = result.stderr.strip() or "OpenTofu output failed"
        raise RuntimeError(
            f"Cannot read OpenTofu outputs. Run tofu apply first. Details: {error}"
        )
    return json.loads(result.stdout)


def output_value(outputs, name):
    try:
        return outputs[name]["value"]
    except KeyError as error:
        raise RuntimeError(f"Required OpenTofu output is missing: {name}") from error


def build_inventory():
    ARTIFACT_DIR.mkdir(mode=0o700, exist_ok=True)
    outputs = load_outputs()
    public_ipv4 = output_value(outputs, "server_public_ipv4")
    private_ipv4 = output_value(outputs, "server_private_ipv4")
    roles = output_value(outputs, "node_roles")

    names = sorted(roles)
    missing = [name for name in names if name not in public_ipv4 or name not in private_ipv4]
    if missing:
        raise RuntimeError(f"OpenTofu outputs are incomplete for: {', '.join(missing)}")

    hostvars = {
        name: {
            "ansible_host": public_ipv4[name],
            "ansible_user": "root",
            "private_ip": private_ipv4[name],
            "node_role": roles[name],
        }
        for name in names
    }
    private_key_file = os.environ.get("ANSIBLE_PRIVATE_KEY_FILE")
    if private_key_file:
        for hostvars_for_node in hostvars.values():
            hostvars_for_node["ansible_ssh_private_key_file"] = private_key_file
    for hostvars_for_node in hostvars.values():
        hostvars_for_node["ansible_ssh_common_args"] = (
            f"-o UserKnownHostsFile={KNOWN_HOSTS} -o StrictHostKeyChecking=accept-new"
        )
    return {
        "all": {"hosts": names},
        "k3s_admin": {"hosts": [name for name in names if roles[name] == "admin"]},
        "k3s_workers": {"hosts": [name for name in names if roles[name] == "worker"]},
        "_meta": {"hostvars": hostvars},
    }


def main():
    try:
        inventory = build_inventory()
    except (RuntimeError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(inventory, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
