# Galera Kubernetes Lab

Reproduzierbares Testlabor für MariaDB Galera auf Hetzner Cloud und K3s. Es dient Ausfall-, Quorum-, Recovery- und Monitoring-Tests; es ist kein Produktionsdesign.

## Überblick

Das Standardlayout besteht aus drei `cx23`-VMs in `nbg1` mit Ubuntu 24.04:

```text
Lokaler Rechner
    │ SSH / Tunnel
    ▼
k3s-admin (Control Plane, embedded etcd, kein Galera-Pod)
    │ privates Hetzner-Netz 10.20.0.0/16
    ├── k3s-worker-1 (K3s Agent, Galera-Pods)
    └── k3s-worker-2 (K3s Agent, Galera-Pods)
```

OpenTofu erstellt Netzwerk, Subnetz (`10.20.0.0/24`), Firewall, Spread-Placement-Group und Server. Ansible installiert K3s. Helm und der MariaDB Operator verwalten danach Operator, Galera und Monitoring.

Öffentlich eingehend ist nur SSH aus `admin_cidr` erlaubt. MariaDB-, Galera-, Kubernetes-, etcd- und Flannel-Ports bleiben geschlossen. Kubernetes-API und Grafana werden über SSH-Tunnel erreicht; es gibt keine Load Balancer.

## Voraussetzungen

Benötigt werden `tofu`, `ansible`, `ansible-playbook`, `helm`, `kubectl`, `ssh`, `curl` und Python 3. `tflint` wird verwendet, falls es unter `~/go/bin/tflint` installiert ist.

Im Hetzner-Projekt muss bereits ein öffentlicher SSH-Key existieren. Sein Name wird in der lokalen Datei `infrastructure/opentofu/terraform.tfvars` referenziert; der private Schlüssel bleibt lokal. Der Hetzner-Token wird ausschließlich aus `HCLOUD_TOKEN` gelesen.

```bash
cp .env.example .env
# .env: sichere Werte für HCLOUD_TOKEN, MARIADB_ROOT_PASSWORD und GRAFANA_ADMIN_PASSWORD eintragen

set -a
source .env
set +a

make tofu-tfvars SSH_KEY_NAME='Name des vorhandenen Hetzner-SSH-Keys'
```

`make tofu-tfvars` ermittelt die aktuelle öffentliche IPv4-Adresse und schreibt `admin_cidr` als `/32` in die nicht versionierte `terraform.tfvars`. Ist die Datei bereits vorhanden, überschreibt das Ziel sie nicht. Nach einem Netzwerkwechsel:

```bash
make tofu-refresh-admin-cidr
```

Standardpfad für den privaten Schlüssel ist `~/.ssh/hetzner_galera_lab`. Einen anderen Pfad setzt `ANSIBLE_PRIVATE_KEY_FILE` in `.env`.

Optional kann `direnv` `.env` beim Betreten des Repositorys exportieren. Die versionierte `.envrc` lädt dabei keine Geheimnisse; die lokale `.env` bleibt ignoriert.

## Infrastruktur prüfen und bereitstellen

Vor einem kostenpflichtigen Vorgang prüfen:

```bash
make preflight
make tofu-check
make tofu-plan
```

`make tofu-check` führt `tofu fmt -check -recursive`, `tofu init -backend=false`, `tofu validate` und gegebenenfalls `tflint` aus. `make tofu-plan` zeigt nur Änderungen an.

```bash
make start
```

`make start` aktualisiert `admin_cidr`, prüft und plant die Infrastruktur, führt anschließend den OpenTofu-Apply nach Bestätigung aus, bootstrapped K3s, holt die Kubeconfig und installiert Monitoring sowie Galera. Der Vorgang kann drei kostenpflichtige VMs anlegen.

Die Standard-K3s-Version ist `v1.36.4+k3s1`; sie kann einmalig überschrieben werden:

```bash
make start K3S_VERSION='v1.36.4+k3s1'
```

## Cluster verwenden

Für spätere Kubernetes- oder Grafana-Zugriffe den Tunnel in einem separaten Terminal starten:

```bash
make k3s-tunnel
```

Danach in einem weiteren Terminal:

```bash
set -a; source .env; set +a
kubectl get nodes -o wide
kubectl -n mariadb get mariadb,pods,pvc,svc
kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80
```

Grafana ist dann unter <http://127.0.0.1:3000> erreichbar. Benutzer ist `admin`, das Passwort ist `GRAFANA_ADMIN_PASSWORD`.

Nützliche Diagnosebefehle:

```bash
kubectl get pods -A
kubectl -n mariadb exec -it mariadb-cluster-0 -c mariadb -- mariadb -uroot -p
kubectl -n mariadb logs mariadb-cluster-0 -c mariadb --tail=100
make cluster-verify
```

Die versionierte Clusterkonfiguration liegt in `cluster/galera/values.yaml`, `cluster/mariadb-operator/values.yaml` und `cluster/monitoring/values.yaml`. Das Grafana-Dashboard liegt in `cluster/monitoring/galera-dashboard.json`.

## Ausfallszenarien

```bash
make scenarios-list
make scenario-pod
make scenario-process
make scenario-node-single
make scenario-node-double
make scenario-network
make scenario-network-double
make scenario-network-degrade
make scenario-overload-flow-control
make scenario-certification-conflict
make scenario-allocator-memory
make scenario-export
```

Die Szenarien erfassen Cluster- und Galera-Status, Wiederanlaufzeit, Probes, Logs und – sofern Prometheus erreichbar ist – Zeitreihen. Ergebnisse liegen lokal unter `.artifacts/scenarios/`; `scenarios/PLAYBOOK.md` beschreibt Ausführung, Analyse und Wiederherstellung.

Node- und Netzwerkszenarien verändern nur die bestehenden Worker per SSH, nicht Hetzner-Ressourcen. `scenario-network-degrade` räumt Latenz- und Paketverlustregeln nach der Messung auf. Das doppelt belegte Worker-Szenario demonstriert gezielt das Quorum-Risiko.

## Galera-Layout, Skalierung und Kosten

Der Startcluster hat drei Galera-Replikate auf zwei Workern. Mindestens zwei Replikate liegen deshalb auf einem Worker. Das ist absichtlich für Quorum-Ausfalltests gewählt und bietet keine hochverfügbare Produktionsverteilung. Die Platzierung nutzt Worker-Labels und weiche Anti-Affinity mit `ScheduleAnyway`.

Weitere Worker werden explizit in `node_definitions` in `infrastructure/opentofu/terraform.tfvars` ergänzt. Jeder neue Eintrag erstellt einen weiteren Server und verursacht Kosten. Beispiel:

```hcl
node_definitions = {
  k3s-admin = { role = "admin", private_ip = "10.20.0.2" }
  k3s-worker-1 = { role = "worker", private_ip = "10.20.0.3" }
  k3s-worker-2 = { role = "worker", private_ip = "10.20.0.4" }
  k3s-worker-3 = { role = "worker", private_ip = "10.20.0.5" }
}
```

Die Map wird vollständig überschrieben: Beim Ersetzen der Standardwerte müssen Admin und bestehende Worker ebenfalls enthalten bleiben. Vor jeder Änderung `make tofu-plan` ausführen. Entfernen oder Umbenennen eines Eintrags kann einen Server löschen.

Phase 1 erstellt keine Volumes, Backups, Snapshots oder Load Balancer. `make stop` zeigt zuerst einen Destroy-Plan und entfernt nach Bestätigung Infrastruktur und Daten auf den Lab-VMs; lokale Szenario-Exporte bleiben erhalten:

```bash
make scenario-export
make stop
```

## Befehlsübersicht

| Bereich | Wichtige Ziele |
| --- | --- |
| Gesamtlauf | `make start`, `make stop`, `make preflight` |
| OpenTofu | `make tofu-tfvars`, `make tofu-refresh-admin-cidr`, `make tofu-check`, `make tofu-plan` |
| Ansible/K3s | `make ansible-check`, `make ansible-inventory`, `make ansible-bootstrap`, `make ansible-kubeconfig`, `make k3s-tunnel` |
| Cluster | `make cluster-operator`, `make cluster-monitoring`, `make cluster-galera`, `make cluster-install`, `make cluster-verify` |
| Szenarien | `make scenarios-list`, `make scenario-…`, `make scenario-export` |

Für gezielte Cluster-Updates können die fachlichen Makefiles direkt in `cluster/`, `scenarios/`, `bootstrap/ansible/` und `infrastructure/opentofu/` ausgeführt werden.

## Sicherheitsregeln

- Keine Tokens, privaten Schlüssel, Passwörter, K3s-Tokens, State-, Plan- oder lokalen tfvars-Dateien committen.
- Vor `apply` oder `destroy` immer den angezeigten Plan prüfen.
- Die OpenTofu-Konfiguration verwaltet keine Kubernetes- oder Helm-Ressourcen; diese bleiben in versionierten Helm-Werten und beim MariaDB Operator.
