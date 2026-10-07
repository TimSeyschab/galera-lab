# Galera Kubernetes Lab

Reproduzierbares Testlabor fuer MariaDB Galera auf drei Hetzner-Cloud-VMs und K3s. Das Labor ist fuer Ausfall-, Quorum-, Recovery- und Monitoring-Experimente gedacht. Es ist kein Produktionsdesign.

## 1. Quickstart

### Voraussetzungen

Benoetigt werden OpenTofu (`tofu`), Ansible (`ansible`, `ansible-playbook`), Helm (`helm`), kubectl (`kubectl`), SSH und `curl`.

Der Hetzner-Token wird ausschliesslich ueber `HCLOUD_TOKEN` gelesen. Private Schluessel, Passwoerter und K3s-Tokens werden nicht im Repository gespeichert.

### Variablen

```dotenv
KUBECONFIG=.artifacts/kubeconfig
HCLOUD_TOKEN='...'
ANSIBLE_PRIVATE_KEY_FILE="$HOME/.ssh/hetzner_galera_lab" # optional: this is the default
MARIADB_ROOT_PASSWORD='...'
GRAFANA_ADMIN_PASSWORD='...'
```

Fuer direkte `kubectl`-Aufrufe die Datei laden:

```bash
set -a
source .env
set +a
```

Optional kann `direnv` die `.env` beim Betreten des Repository-Verzeichnisses automatisch laden:

```bash
sudo apt install direnv
echo 'eval "$(direnv hook bash)"' >> ~/.bashrc
source ~/.bashrc
direnv allow
```

Danach werden die Variablen beim Wechsel in dieses Verzeichnis automatisch exportiert. `.envrc` ist versioniert und laedt keine weiteren Dateien; die lokale `.env` bleibt ignoriert.

Die Standardversion von K3s ist `v1.36.4+k3s1` und kann ueberschrieben werden:

```bash
export K3S_VERSION='v1.36.4+k3s1'
```

### Vollstaendiger Start

```bash
make start
```

Der Befehl fuehrt OpenTofu-Pruefungen, Plan und Apply, den Ansible-K3s-Bootstrap, den Kubeconfig-Abruf, die Helm-Installation von MariaDB/Galera, Prometheus und Grafana sowie die Cluster-Verifikation aus. Der SSH-Tunnel wird fuer die Helm-Schritte temporaer im Hintergrund gestartet und danach automatisch geschlossen.

Der Start kann drei kostenpflichtige Hetzner-VMs anlegen. OpenTofu fragt vor dem Apply nach einer Bestaetigung.

### Kubernetes-Tunnel und Grafana

Fuer spaetere Kubernetes- oder Grafana-Aufrufe den Tunnel in einem separaten Terminal offen halten:

```bash
make k3s-tunnel
```

In einem weiteren Terminal die Kubeconfig laden und Grafana weiterleiten:

```bash
set -a
source .env
set +a
kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80
```

Grafana ist unter <http://127.0.0.1:3000> erreichbar. Benutzername ist `admin`; das Passwort entspricht `GRAFANA_ADMIN_PASSWORD`.

Das Dashboard `MariaDB Galera Lab` zeigt Cluster-Groesse, Ready-/Connected-Members, Pod-Restarts, Flow Control, Replikations-Queues, Apply-/Commit-Fenster, Writesets, Node-CPU, Node-Load, Node-Memory, InnoDB-Buffer-Pool, Connections und Queries.

### Pods und Cluster pruefen

```bash
kubectl get nodes -o wide
kubectl get pods -A
kubectl -n mariadb get mariadb,pods,pvc,svc
kubectl -n monitoring get pods
```

Shell in einem Galera-Pod:

```bash
kubectl -n mariadb exec -it mariadb-cluster-0 -c mariadb -- bash
```

MariaDB-Sitzung mit Passwort-Prompt:

```bash
kubectl -n mariadb exec -it mariadb-cluster-0 -c mariadb -- mariadb -uroot -p
```

Logs lesen:

```bash
kubectl -n mariadb logs mariadb-cluster-0 -c mariadb --tail=100
```

### Ausfallszenarien messen

Die README-Todos sind als reproduzierbare Szenarien unter `scenarios/` umgesetzt. Das operative Playbook fuer Ausloesen, Metriken, manuelle Analyse und Reparatur liegt in `scenarios/PLAYBOOK.md`.

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
make scenario-export
```

Die Ergebnisse werden vor dem Loeschen der Umgebung unter `.artifacts/scenarios/` als JSON exportiert. Enthalten sind Pod- und Node-Zustand, Galera-Status, Quorum-Indikatoren, IST-/SST-Hinweise aus Logs, Wiederanlaufzeit und Probe-Fehlerrate.

`scenario-pod` loescht einen einzelnen Galera-Pod und zeigt Kubernetes-Recreation, StatefulSet-Identitaet, PVC-Wiederverwendung und Galera-Rejoin; die vertiefte Studienhilfe liegt in `scenarios/pod-delete.md`. `scenario-network-double` isoliert den doppelt belegten Worker und macht das Quorum-Risiko des Zwei-Worker-Layouts mit Netzwerkfehlern sichtbar. `scenario-network-degrade` fuegt dem privaten Worker-Interface Latenz und Paketverlust hinzu und entfernt diese Stoerung nach der Messung automatisch. `scenario-overload-flow-control` ueberlastet gezielt einen Worker und erzeugt parallel Schreiblast, damit Flow-Control-Verhalten sichtbar wird; die vertiefte Studienhilfe liegt in `scenarios/overload-flow-control.md`. `scenario-certification-conflict` erzeugt konkurrierende Writes gegen mehrere Galera-Member und misst Zertifizierungskonflikte. Node- und Netzwerk-Szenarien greifen per SSH auf bestehende Worker zu, veraendern aber keine Hetzner-Ressourcen.

### Vollstaendiger Abbau

```bash
make scenario-export
make stop
```

`make stop` fuehrt `make destroy` aus und entfernt danach lokale Kubeconfig-, lab-spezifische Known-Hosts- und OpenTofu-State-Artefakte. Der Destroy-Plan wird zuerst angezeigt, danach fragt OpenTofu vor dem Loeschen. Entfernt werden Server, Netzwerk, Firewall und Placement Group. Damit verschwinden auch alle MariaDB-Daten auf den Test-VMs. Szenario-Exports unter `.artifacts/scenarios/` bleiben lokal erhalten.

## 2. Befehle nach Kontext

Alle Ziele koennen aus dem Repository-Root ausgefuehrt werden. Die fachlichen Makefiles koennen alternativ direkt in ihren Unterverzeichnissen verwendet werden.

### Cluster: `cluster/`

| Befehl | Zweck |
| --- | --- |
| `make cluster-repos` | Helm-Repositories hinzufuegen und aktualisieren |
| `make cluster-operator` | MariaDB-CRDs und Operator installieren oder aktualisieren |
| `make cluster-monitoring` | Prometheus-Stack und Grafana installieren oder aktualisieren |
| `make cluster-dashboard` | Galera-Dashboard als ConfigMap provisionieren |
| `make cluster-galera` | MariaDB-Galera-Cluster installieren oder aktualisieren |
| `make cluster-install` | Monitoring und Galera vollstaendig installieren |
| `make cluster-verify` | MariaDB, Pods, PVCs, Services, Monitoring und Dashboard pruefen |

Versionen koennen beim Aufruf ueberschrieben werden:

```bash
make cluster-install MARIADB_OPERATOR_VERSION=26.6.0 PROMETHEUS_STACK_VERSION=88.0.1
```

Versionierte Cluster-Konfiguration:

- `cluster/galera/values.yaml`
- `cluster/mariadb-operator/values.yaml`
- `cluster/monitoring/values.yaml`
- `cluster/monitoring/galera-dashboard.json`

### Szenarien: `scenarios/`

| Befehl | Zweck |
| --- | --- |
| `make scenarios-list` | verfuegbare Ausfallszenarien anzeigen |
| `make scenario-pod` | Galera-Pod loeschen und Recovery messen |
| `make scenario-process` | MariaDB-Prozess in einem Pod beenden und Recovery messen |
| `make scenario-node-single` | Ausfall des einfach belegten Workers simulieren |
| `make scenario-node-double` | Ausfall des doppelt belegten Workers simulieren |
| `make scenario-network` | privaten Netzwerkverkehr eines Workers blockieren |
| `make scenario-network-double` | privaten Netzwerkverkehr des doppelt belegten Workers blockieren |
| `make scenario-network-degrade` | privaten Netzwerkverkehr mit Latenz und Paketverlust degradieren |
| `make scenario-overload-flow-control` | Worker-Ueberlast mit Schreiblast fuer Flow-Control-Nachstellung |
| `make scenario-certification-conflict` | konkurrierende Galera-Writes fuer Zertifizierungskonflikte erzeugen |
| `make scenario-export` | aktuellen Cluster-, Galera- und Event-Zustand exportieren |

### Infrastruktur: `infrastructure/opentofu/`

| Befehl | Zweck |
| --- | --- |
| `make tofu-tfvars` | Lokale `terraform.tfvars` mit dynamischer Admin-IP erzeugen |
| `make tofu-refresh-admin-cidr` | bestehende lokale `admin_cidr` auf die aktuelle oeffentliche IPv4 aktualisieren |
| `make tofu-fmt` | OpenTofu-Dateien pruefen |
| `make tofu-init` | Provider ohne Backend initialisieren |
| `make tofu-validate` | OpenTofu-Konfiguration validieren |
| `make tofu-plan` | Infrastrukturplan anzeigen |
| `make tofu-check` | Formatierung, Init, Validierung und optional TFLint |
| `make clean-local` | lokale Kubeconfig-, lab-spezifische Known-Hosts-, State-, Plan- und Crash-Artefakte entfernen |
| `tofu -chdir=infrastructure/opentofu apply` | Infrastruktur nach Plan anwenden |
| `tofu -chdir=infrastructure/opentofu destroy` | Infrastruktur nach Plan entfernen |

Fuer den kompletten Lebenszyklus `make start` und `make stop` verwenden.

### Bootstrap: `bootstrap/ansible/`

| Befehl | Zweck |
| --- | --- |
| `make ansible-check` | Ansible-Syntax pruefen |
| `make ansible-inventory` | Dynamisches Inventory aus OpenTofu-Outputs anzeigen |
| `make ansible-bootstrap` | Betriebssystem, private Netzwerkschnittstelle und K3s installieren |
| `make ansible-kubeconfig` | Kubeconfig sicher vom Admin abrufen |
| `make k3s-tunnel` | SSH-Tunnel zur privaten K3s-API starten |

Das dynamische Inventory benoetigt einen vorhandenen OpenTofu-State nach `tofu apply`. Ansible konfiguriert genau einen K3s-Admin und alle definierten Worker als Agents.

## 3. Architekturuebersicht

```text
                         lokaler Rechner
                              |
              SSH TCP 6443 ueber oeffentliche Admin-IP
                              |
                    +---------+---------+
                    | k3s-admin         |
                    | Control Plane     |
                    | embedded etcd     |
                    | kein Galera-Pod   |
                    +---------+---------+
                              |
                 privates Hetzner-Netz 10.20.0.0/16
                              |
             +----------------+----------------+
             |                                 |
   +---------+---------+             +---------+---------+
   | k3s-worker-1      |             | k3s-worker-2      |
   | K3s Agent         |             | K3s Agent         |
   | Galera-Pods       |             | Galera-Pods       |
   +-------------------+             +-------------------+

   MariaDB Galera: 3 Replikate, Startlayout auf 2 Workern
   Prometheus und Grafana: interne ClusterIP-Services
```

### Verantwortlichkeiten

| Bereich | Werkzeug | Inhalt |
| --- | --- | --- |
| Hetzner-Infrastruktur | OpenTofu | Netzwerk, Subnetz, Firewall, Placement Group, Server und IPs |
| Betriebssystem und K3s | Ansible | private Netzwerkschnittstelle, K3s-Admin, K3s-Worker, Kubeconfig |
| MariaDB und Galera | Helm und MariaDB Operator | CRDs, Operator, MariaDB-CR, Replikate, Storage und Platzierung |
| Monitoring | Helm, Prometheus Operator und Grafana | Scraping, ServiceMonitors und Dashboard |
| Tests | spaetere Ansible-/Skripte | Pod-, Prozess-, Node-, Netzwerk- und Quorum-Ausfaelle |

### Netzwerk und Sicherheit

- Hetzner-Netzwerk: `10.20.0.0/16`
- Subnetz: `10.20.0.0/24`
- Initiale private Node-IP-Adressen: `10.20.0.2`, `10.20.0.3`, `10.20.0.4`
- Oeffentlich eingehend ist nur SSH aus `admin_cidr` erlaubt.
- MariaDB-, Galera-, Kubernetes-, etcd- und Flannel-Ports sind nicht oeffentlich freigegeben.
- Die Kubernetes-API wird ueber einen SSH-Tunnel erreicht.
- MariaDB und Grafana verwenden interne `ClusterIP`-Services; es werden keine LoadBalancer erzeugt.
- Private Schluessel, API-Tokens, Passwoerter, K3s-Tokens, State-Dateien und lokale Variablen werden nicht versioniert.

### Galera-Startlayout und Skalierung

Der Cluster startet mit drei Galera-Replikaten auf zwei Workern. Deshalb liegen mindestens zwei Replikate auf einem Worker. Das ist ein bewusstes Ausfall- und Quorum-Szenario und keine hochverfuegbare Produktionsverteilung.

Die Platzierung nutzt Worker-Labels, weiche Anti-Affinity und `ScheduleAnyway`. Bei zusaetzlichen Workern kann die Node-Abbildung in OpenTofu erweitert werden; die Helm-Platzierungsregeln erlauben dann eine gleichmaessigere Verteilung.

### Kosten und Lebenszyklus

- Jeder weitere Worker erzeugt einen weiteren kostenpflichtigen Hetzner-Server.
- Es werden aktuell keine Load Balancer, Volumes, Backups oder Snapshots durch OpenTofu angelegt.
- `make start` kann neue Infrastruktur erstellen.
- `make stop` beziehungsweise `make destroy` entfernt die gesamte Testumgebung und ihre Daten.
- Kostenrelevante oder loeschende Aktionen erfordern eine manuelle Bestaetigung.

## Verzeichnisstruktur

```text
galera-lab/
├── .env.example
├── Makefile
├── README.md
├── infrastructure/opentofu/
├── bootstrap/ansible/
├── cluster/
│   ├── Makefile
│   ├── galera/
│   ├── mariadb-operator/
│   └── monitoring/
└── scenarios/
    ├── Makefile
    ├── PLAYBOOK.md
    └── scripts/
```