#!/usr/bin/env python3
"""Forward local Kubernetes API traffic through the public SSH endpoint."""

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TOFU_DIR = ROOT / "infrastructure" / "opentofu"
ARTIFACT_DIR = ROOT / ".artifacts"
KNOWN_HOSTS = ARTIFACT_DIR / "known_hosts"


def main():
    ARTIFACT_DIR.mkdir(mode=0o700, exist_ok=True)
    result = subprocess.run(
        ["tofu", f"-chdir={TOFU_DIR}", "output", "-json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    outputs = json.loads(result.stdout)
    roles = outputs["node_roles"]["value"]
    admin = next(name for name, role in roles.items() if role == "admin")
    public_ip = outputs["server_public_ipv4"]["value"][admin]
    private_ip = outputs["server_private_ipv4"]["value"][admin]
    command = [
        "ssh",
        "-F",
        "/dev/null",
        "-N",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        f"UserKnownHostsFile={KNOWN_HOSTS}",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-L",
        f"6443:{private_ip}:6443",
        f"root@{public_ip}",
    ]
    private_key_file = os.environ.get("ANSIBLE_PRIVATE_KEY_FILE")
    if private_key_file:
        command[1:1] = ["-i", private_key_file]
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
