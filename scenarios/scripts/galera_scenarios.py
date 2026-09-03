#!/usr/bin/env python3
"""Run reproducible Galera failure scenarios and export measurements."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TOFU_DIR = ROOT / "infrastructure" / "opentofu"
DEFAULT_ARTIFACT_DIR = ROOT / ".artifacts" / "scenarios"
ARTIFACT_DIR = ROOT / ".artifacts"
KNOWN_HOSTS = ARTIFACT_DIR / "known_hosts"
MARIADB_NAMESPACE = os.environ.get("MARIADB_NAMESPACE", "mariadb")
MONITORING_NAMESPACE = os.environ.get("MONITORING_NAMESPACE", "monitoring")
MARIADB_LABEL = os.environ.get(
    "MARIADB_LABEL",
    "app.kubernetes.io/instance=mariadb-cluster,app.kubernetes.io/name=mariadb",
)
NETWORK_COMMENT = "galera-lab-scenario-network"
OVERLOAD_LABEL = "galera-lab-scenario-overload"


class ScenarioError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_command(
    command: list[str],
    *,
    check: bool = True,
    input_text: str | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        rendered = " ".join(shlex.quote(part) for part in command)
        details = result.stderr.strip() or result.stdout.strip() or "no output"
        raise ScenarioError(f"Command failed: {rendered}\n{details}")
    return result


def kubectl(args: list[str], *, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return run_command(["kubectl", *args], check=check, timeout=timeout)


def kubectl_json(args: list[str], *, check: bool = True) -> dict[str, Any]:
    result = kubectl([*args, "-o", "json"], check=check)
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    return json.loads(result.stdout)


def tofu_output() -> dict[str, Any]:
    result = run_command(["tofu", f"-chdir={TOFU_DIR}", "output", "-json"])
    return json.loads(result.stdout)


def output_value(outputs: dict[str, Any], name: str) -> Any:
    try:
        return outputs[name]["value"]
    except KeyError as error:
        raise ScenarioError(f"Required OpenTofu output is missing: {name}") from error


def ssh_base(host: str) -> list[str]:
    ARTIFACT_DIR.mkdir(mode=0o700, exist_ok=True)
    key = os.environ.get("ANSIBLE_PRIVATE_KEY_FILE")
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"UserKnownHostsFile={KNOWN_HOSTS}",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=10",
    ]
    if key:
        command.extend(["-i", key])
    command.append(f"root@{host}")
    return command


def ssh(host: str, remote_command: str, *, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return run_command([*ssh_base(host), remote_command], check=check, timeout=timeout)


def mariadb_pods() -> list[dict[str, Any]]:
    data = kubectl_json(["-n", MARIADB_NAMESPACE, "get", "pods", "-l", MARIADB_LABEL])
    pods = data.get("items", [])
    if not pods:
        raise ScenarioError(
            f"No MariaDB pods found in namespace {MARIADB_NAMESPACE} with label {MARIADB_LABEL}"
        )
    return pods


def pod_name(pod: dict[str, Any]) -> str:
    return pod["metadata"]["name"]


def pod_node(pod: dict[str, Any]) -> str:
    return pod.get("spec", {}).get("nodeName", "")


def ready_container_count(pod: dict[str, Any]) -> tuple[int, int]:
    statuses = pod.get("status", {}).get("containerStatuses", [])
    ready = len([status for status in statuses if status.get("ready")])
    return ready, len(statuses)


def is_pod_ready(pod: dict[str, Any]) -> bool:
    phase = pod.get("status", {}).get("phase")
    ready, total = ready_container_count(pod)
    return phase == "Running" and total > 0 and ready == total


def placement() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for pod in mariadb_pods():
        node = pod_node(pod)
        if node:
            result.setdefault(node, []).append(pod_name(pod))
    return {node: sorted(pods) for node, pods in sorted(result.items())}


def target_worker(kind: str) -> str:
    current = placement()
    if not current:
        raise ScenarioError("Cannot determine MariaDB pod placement.")
    ordered = sorted(current, key=lambda node: (len(current[node]), node))
    if kind == "single":
        return ordered[0]
    if kind == "double":
        return ordered[-1]
    raise ScenarioError(f"Unknown worker target kind: {kind}")


def pod_on_worker(worker_kind: str) -> str:
    target = target_worker(worker_kind)
    pods = placement()[target]
    return sorted(pods)[0]


def collect_status() -> dict[str, Any]:
    pods = mariadb_pods()
    nodes = kubectl_json(["get", "nodes"])
    pod_rows = []
    for pod in pods:
        ready, total = ready_container_count(pod)
        pod_rows.append(
            {
                "name": pod_name(pod),
                "node": pod_node(pod),
                "phase": pod.get("status", {}).get("phase"),
                "ready_containers": ready,
                "total_containers": total,
                "restarts": sum(
                    status.get("restartCount", 0)
                    for status in pod.get("status", {}).get("containerStatuses", [])
                ),
            }
        )
    node_rows = []
    for node in nodes.get("items", []):
        conditions = {
            condition.get("type"): condition.get("status")
            for condition in node.get("status", {}).get("conditions", [])
        }
        node_rows.append(
            {
                "name": node["metadata"]["name"],
                "ready": conditions.get("Ready"),
                "unschedulable": node.get("spec", {}).get("unschedulable", False),
            }
        )
    return {
        "timestamp": utc_now(),
        "pods": sorted(pod_rows, key=lambda row: row["name"]),
        "nodes": sorted(node_rows, key=lambda row: row["name"]),
        "placement": placement(),
        "galera": galera_status(),
    }


def galera_status() -> dict[str, Any]:
    password = os.environ.get("MARIADB_ROOT_PASSWORD")
    if not password:
        return {"available": False, "reason": "MARIADB_ROOT_PASSWORD is not set"}
    mysql_env = f"MYSQL_PWD={shlex.quote(password)}"
    for pod in sorted(pod_name(pod) for pod in mariadb_pods()):
        query = (
            "SHOW GLOBAL STATUS WHERE Variable_name IN "
            "('wsrep_cluster_status','wsrep_cluster_size','wsrep_local_state_comment',"
            "'wsrep_ready','wsrep_connected','wsrep_flow_control_paused',"
            "'wsrep_flow_control_sent','wsrep_flow_control_recv',"
            "'wsrep_local_recv_queue','wsrep_local_send_queue',"
            "'wsrep_cert_deps_distance','wsrep_apply_window','wsrep_commit_window',"
            "'wsrep_replicated','wsrep_received','wsrep_replicated_bytes','wsrep_received_bytes');"
        )
        result = kubectl(
            [
                "-n",
                MARIADB_NAMESPACE,
                "exec",
                pod,
                "-c",
                "mariadb",
                "--",
                "sh",
                "-c",
                f"{mysql_env} mariadb -uroot -N -e " + shlex.quote(query),
            ],
            check=False,
            timeout=30,
        )
        if result.returncode == 0:
            values = {}
            for line in result.stdout.splitlines():
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    values[parts[0]] = parts[1]
            return {"available": True, "pod": pod, "status": values}
    return {"available": False, "reason": "No MariaDB pod accepted a status query"}


def probe_once() -> bool:
    password = os.environ.get("MARIADB_ROOT_PASSWORD")
    if not password:
        return False
    mysql_env = f"MYSQL_PWD={shlex.quote(password)}"
    for pod in sorted(pod_name(pod) for pod in mariadb_pods()):
        result = kubectl(
            [
                "-n",
                MARIADB_NAMESPACE,
                "exec",
                pod,
                "-c",
                "mariadb",
                "--",
                "sh",
                "-c",
                f"{mysql_env} mariadb -uroot -N -e 'SELECT 1'",
            ],
            check=False,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip() == "1":
            return True
    return False


def write_probe_once() -> bool:
    password = os.environ.get("MARIADB_ROOT_PASSWORD")
    if not password:
        return False
    rows = int(os.environ.get("SCENARIO_WRITE_ROWS", "100"))
    bytes_per_row = int(os.environ.get("SCENARIO_WRITE_BYTES", "2048"))
    mysql_env = f"MYSQL_PWD={shlex.quote(password)}"
    sql = (
        "CREATE DATABASE IF NOT EXISTS galera_lab_scenarios; "
        "CREATE TABLE IF NOT EXISTS galera_lab_scenarios.flow_control_probe "
        "(id BIGINT AUTO_INCREMENT PRIMARY KEY, created_at DATETIME(6) NOT NULL, "
        "source VARCHAR(128) NOT NULL, payload VARBINARY(8192) NOT NULL) ENGINE=InnoDB;"
    )
    insert_sql = (
        "INSERT INTO galera_lab_scenarios.flow_control_probe "
        f"(created_at, source, payload) VALUES (NOW(6), @@hostname, REPEAT('x', {bytes_per_row}));"
    )
    shell = (
        "set -eu; "
        f"{{ printf '%s\\n' {shlex.quote(sql)}; "
        f"i=0; while [ \"$i\" -lt {rows} ]; do printf '%s\\n' {shlex.quote(insert_sql)}; i=$((i + 1)); done; }} "
        f"| {mysql_env} mariadb -uroot"
    )
    for pod in sorted(pod_name(pod) for pod in mariadb_pods()):
        result = kubectl(
            [
                "-n",
                MARIADB_NAMESPACE,
                "exec",
                pod,
                "-c",
                "mariadb",
                "--",
                "sh",
                "-c",
                shell,
            ],
            check=False,
            timeout=60,
        )
        if result.returncode == 0:
            return True
    return False


def status_float(galera: dict[str, Any], key: str) -> float:
    try:
        return float(galera.get("status", {}).get(key, 0))
    except (TypeError, ValueError):
        return 0.0


def probe_window(seconds: int, poll_seconds: int, *, write_load: bool = False) -> dict[str, Any]:
    deadline = time.monotonic() + seconds
    attempts = 0
    failures = 0
    timeline = []
    max_flow_control_paused = 0.0
    max_recv_queue = 0.0
    max_send_queue = 0.0
    while time.monotonic() < deadline:
        attempts += 1
        ok = write_probe_once() if write_load else probe_once()
        if not ok:
            failures += 1
        galera = galera_status()
        flow_control_paused = status_float(galera, "wsrep_flow_control_paused")
        recv_queue = status_float(galera, "wsrep_local_recv_queue")
        send_queue = status_float(galera, "wsrep_local_send_queue")
        max_flow_control_paused = max(max_flow_control_paused, flow_control_paused)
        max_recv_queue = max(max_recv_queue, recv_queue)
        max_send_queue = max(max_send_queue, send_queue)
        timeline.append(
            {
                "timestamp": utc_now(),
                "ok": ok,
                "write_load": write_load,
                "galera": galera,
                "flow_control_paused": flow_control_paused,
                "recv_queue": recv_queue,
                "send_queue": send_queue,
            }
        )
        time.sleep(poll_seconds)
    return {
        "attempts": attempts,
        "failures": failures,
        "failure_rate": failures / attempts if attempts else None,
        "write_load": write_load,
        "flow_control_observed": max_flow_control_paused > 0 or max_recv_queue > 0 or max_send_queue > 0,
        "max_flow_control_paused": max_flow_control_paused,
        "max_recv_queue": max_recv_queue,
        "max_send_queue": max_send_queue,
        "timeline": timeline,
    }


def wait_mariadb_ready(timeout_seconds: int = 300, poll_seconds: int = 5) -> dict[str, Any]:
    started = time.monotonic()
    timeline = []
    while time.monotonic() - started <= timeout_seconds:
        pods = mariadb_pods()
        ready = sum(1 for pod in pods if is_pod_ready(pod))
        total = len(pods)
        galera = galera_status()
        timeline.append(
            {
                "timestamp": utc_now(),
                "ready_pods": ready,
                "total_pods": total,
                "galera": galera,
            }
        )
        cluster_status = galera.get("status", {}).get("wsrep_cluster_status")
        wsrep_ready = galera.get("status", {}).get("wsrep_ready")
        if ready == total and cluster_status == "Primary" and wsrep_ready == "ON":
            return {
                "ready": True,
                "seconds": round(time.monotonic() - started, 3),
                "timeline": timeline,
            }
        time.sleep(poll_seconds)
    return {
        "ready": False,
        "seconds": round(time.monotonic() - started, 3),
        "timeline": timeline,
    }


def transfer_events(since: str | None = None) -> dict[str, Any]:
    args = ["-n", MARIADB_NAMESPACE, "logs", "-l", MARIADB_LABEL, "-c", "mariadb", "--tail=400"]
    if since:
        args.append(f"--since-time={since}")
    result = kubectl(args, check=False, timeout=60)
    lines = []
    for line in result.stdout.splitlines():
        upper = line.upper()
        if "IST" in upper or "SST" in upper or "STATE TRANSFER" in upper:
            lines.append(line[-500:])
    return {
        "available": result.returncode == 0,
        "ist_observed": any("IST" in line.upper() for line in lines),
        "sst_observed": any("SST" in line.upper() for line in lines),
        "lines": lines[-80:],
    }


def export_snapshot(artifact_dir: Path) -> Path:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "timestamp": utc_now(),
        "status": collect_status(),
        "mariadb_resources": kubectl_json(["-n", MARIADB_NAMESPACE, "get", "mariadb,pods,pvc,svc"], check=False),
        "monitoring_pods": kubectl_json(["-n", MONITORING_NAMESPACE, "get", "pods"], check=False),
        "events": kubectl_json(["get", "events", "-A"], check=False),
        "transfer_events": transfer_events(),
    }
    path = artifact_dir / f"export-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(path)
    return path


def public_ip_for_node(node: str) -> str:
    outputs = tofu_output()
    addresses = output_value(outputs, "server_public_ipv4")
    try:
        return addresses[node]
    except KeyError as error:
        raise ScenarioError(f"No public IPv4 found for node {node}") from error


def induce_pod_delete(context: dict[str, Any]) -> None:
    pod = pod_on_worker("single")
    context["target_pod"] = pod
    kubectl(["-n", MARIADB_NAMESPACE, "delete", "pod", pod])


def induce_process_kill(context: dict[str, Any]) -> None:
    pod = pod_on_worker("single")
    context["target_pod"] = pod
    result = kubectl(
        [
            "-n",
            MARIADB_NAMESPACE,
            "exec",
            pod,
            "-c",
            "mariadb",
            "--",
            "sh",
            "-c",
            "pkill -TERM mariadbd || pkill -TERM mysqld",
        ],
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        raise ScenarioError(result.stderr.strip() or result.stdout.strip() or "Could not kill MariaDB process")


def induce_node_stop(context: dict[str, Any], worker_kind: str) -> None:
    node = target_worker(worker_kind)
    context["target_node"] = node
    kubectl(["cordon", node], check=False)
    ssh(public_ip_for_node(node), "systemctl stop k3s-agent")


def induce_network_isolate(context: dict[str, Any]) -> None:
    node = target_worker("single")
    context["target_node"] = node
    outputs = tofu_output()
    private_addresses = output_value(outputs, "server_private_ipv4")
    network = os.environ.get("SCENARIO_NETWORK_CIDR", "10.20.0.0/16")
    private_ip = private_addresses[node]
    command = (
        "iptables -I INPUT 1 -s {network} -m comment --comment {comment} -j DROP; "
        "iptables -I OUTPUT 1 -d {network} -m comment --comment {comment} -j DROP; "
        "echo isolated {private_ip}"
    ).format(
        network=shlex.quote(network),
        comment=shlex.quote(NETWORK_COMMENT),
        private_ip=shlex.quote(private_ip),
    )
    ssh(public_ip_for_node(node), command)


def apply_manifest(manifest: dict[str, Any]) -> None:
    run_command(["kubectl", "apply", "-f", "-"], input_text=json.dumps(manifest), timeout=120)


def induce_node_overload(context: dict[str, Any]) -> None:
    worker_kind = os.environ.get("SCENARIO_OVERLOAD_WORKER", "double")
    if worker_kind not in {"single", "double"}:
        raise ScenarioError("SCENARIO_OVERLOAD_WORKER must be 'single' or 'double'")
    node = target_worker(worker_kind)
    duration = int(os.environ.get("SCENARIO_OVERLOAD_SECONDS", "120"))
    cpu_workers = int(os.environ.get("SCENARIO_OVERLOAD_CPU_WORKERS", "4"))
    image = os.environ.get("SCENARIO_OVERLOAD_IMAGE", "busybox:1.36.1")
    job_name = f"galera-node-overload-{int(time.time())}"
    context.update(
        {
            "target_node": node,
            "target_kind": worker_kind,
            "job": job_name,
            "duration_seconds": duration,
            "cpu_workers": cpu_workers,
            "write_rows_per_probe": int(os.environ.get("SCENARIO_WRITE_ROWS", "100")),
            "write_bytes_per_row": int(os.environ.get("SCENARIO_WRITE_BYTES", "2048")),
        }
    )
    shell = (
        "set -eu; "
        "echo overload-start $(date -Iseconds); "
        f"i=0; while [ \"$i\" -lt {cpu_workers} ]; do "
        "(while :; do :; done) & i=$((i + 1)); done; "
        f"sleep {duration}; "
        "echo overload-stop $(date -Iseconds)"
    )
    manifest = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": job_name,
            "namespace": MARIADB_NAMESPACE,
            "labels": {"app.kubernetes.io/name": OVERLOAD_LABEL},
        },
        "spec": {
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": 300,
            "template": {
                "metadata": {"labels": {"app.kubernetes.io/name": OVERLOAD_LABEL}},
                "spec": {
                    "nodeName": node,
                    "restartPolicy": "Never",
                    "terminationGracePeriodSeconds": 0,
                    "containers": [
                        {
                            "name": "cpu",
                            "image": image,
                            "imagePullPolicy": "IfNotPresent",
                            "command": ["sh", "-c", shell],
                            "resources": {"requests": {"cpu": "10m", "memory": "16Mi"}},
                        }
                    ],
                },
            },
        },
    }
    apply_manifest(manifest)
    kubectl(
        [
            "-n",
            MARIADB_NAMESPACE,
            "wait",
            "--for=condition=Ready",
            "pod",
            "-l",
            f"app.kubernetes.io/name={OVERLOAD_LABEL}",
            "--timeout=60s",
        ],
        check=False,
        timeout=75,
    )


SCENARIOS = {
    "pod-delete": {
        "description": "Delete one MariaDB pod and measure replacement/recovery.",
        "induce": induce_pod_delete,
        "self_recovering": True,
    },
    "process-kill": {
        "description": "Terminate the MariaDB server process in one pod.",
        "induce": induce_process_kill,
        "self_recovering": True,
    },
    "node-stop-single": {
        "description": "Stop k3s-agent on the worker with the fewest Galera pods.",
        "induce": lambda context: induce_node_stop(context, "single"),
        "self_recovering": False,
    },
    "node-stop-double": {
        "description": "Stop k3s-agent on the worker with the most Galera pods.",
        "induce": lambda context: induce_node_stop(context, "double"),
        "self_recovering": False,
    },
    "network-isolate-single": {
        "description": "Drop private network traffic on the worker with the fewest Galera pods.",
        "induce": induce_network_isolate,
        "self_recovering": False,
    },
    "node-overload-flow-control": {
        "description": "Overload a worker while generating Galera write load to observe flow control.",
        "induce": induce_node_overload,
        "self_recovering": True,
        "write_load": True,
    },
}


def run_scenario(name: str, observe_seconds: int, poll_seconds: int, artifact_dir: Path) -> Path:
    if name not in SCENARIOS:
        raise ScenarioError(f"Unknown scenario: {name}")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    context: dict[str, Any] = {}
    started_at = utc_now()
    result: dict[str, Any] = {
        "scenario": name,
        "description": SCENARIOS[name]["description"],
        "started_at": started_at,
        "before": collect_status(),
    }
    SCENARIOS[name]["induce"](context)
    result["target"] = context
    result["after_induce"] = collect_status()
    result["probe"] = probe_window(
        observe_seconds,
        poll_seconds,
        write_load=bool(SCENARIOS[name].get("write_load", False)),
    )
    if SCENARIOS[name].get("self_recovering", False):
        result["recovery"] = wait_mariadb_ready(poll_seconds=poll_seconds)
    else:
        result["recovery"] = {
            "measured": False,
            "reason": "Scenario intentionally leaves the failure active for manual analysis and repair.",
        }
    result["after_observation"] = collect_status()
    result["transfer_events"] = transfer_events(started_at)
    result["finished_at"] = utc_now()
    path = artifact_dir / f"{name}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(path)
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("scenario", choices=sorted(SCENARIOS))
    run_parser.add_argument("--observe-seconds", type=int, default=45)
    run_parser.add_argument("--poll-seconds", type=int, default=5)
    run_parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "list":
            for name, scenario in sorted(SCENARIOS.items()):
                print(f"{name}\t{scenario['description']}")
        elif args.command == "run":
            run_scenario(args.scenario, args.observe_seconds, args.poll_seconds, args.artifact_dir)
        elif args.command == "export":
            export_snapshot(args.artifact_dir)
        return 0
    except (ScenarioError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
