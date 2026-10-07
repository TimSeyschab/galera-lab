# Galera Failure Playbook

Dieses Playbook beschreibt, wie die Lab-Szenarien ausgeloest, anhand von Metriken erkannt und manuell repariert werden. Alle Befehle werden aus dem Repository-Root ausgefuehrt, sofern nicht anders angegeben.

## Voraussetzungen

```bash
set -a
source .env
set +a
make k3s-tunnel
```

In einem zweiten Terminal:

```bash
kubectl get nodes -o wide
kubectl -n mariadb get pods -o wide
make scenarios-list
```

Wenn der Cluster schon vor dieser Aenderung lief, das aktualisierte Dashboard anwenden:

```bash
make cluster-dashboard
```

Die Szenario-Ergebnisse liegen unter `.artifacts/scenarios/`. Vor `make stop` immer den aktuellen Zustand sichern:

```bash
make scenario-export
```

## Node- und IP-Zuordnung

Die Szenarien waehlen Worker anhand der aktuellen Galera-Pod-Verteilung. Vor manuellen Reparaturen immer Ziel-Node und oeffentliche IP notieren:

```bash
kubectl -n mariadb get pods -o wide
kubectl get nodes -o wide
tofu -chdir=infrastructure/opentofu output server_public_ipv4
```

Fuer manuelle SSH-Reparaturen dieselbe lab-lokale Known-Hosts-Datei wie Ansible, Tunnel und Szenario-Runner verwenden:

```bash
ssh -o UserKnownHostsFile=.artifacts/known_hosts -o StrictHostKeyChecking=accept-new root@<worker-public-ip>
```

Der einfach belegte Worker ist der Worker mit einem Galera-Pod. Der doppelt belegte Worker ist der Worker mit zwei Galera-Pods. Im Zwei-Worker-Layout ist der doppelt belegte Worker das Quorum-Risiko.

## Basisdiagnose

Pod-Verteilung:

```bash
kubectl -n mariadb get pods -o wide
```

Galera-Status aus einem Pod:

```bash
kubectl -n mariadb exec -it mariadb-cluster-0 -c mariadb -- mariadb -uroot -p -e "
SHOW GLOBAL STATUS WHERE Variable_name IN (
  'wsrep_cluster_status',
  'wsrep_cluster_size',
  'wsrep_local_state_comment',
  'wsrep_ready',
  'wsrep_flow_control_paused',
  'wsrep_flow_control_sent',
  'wsrep_flow_control_recv',
  'wsrep_local_recv_queue',
  'wsrep_local_send_queue',
  'wsrep_cert_deps_distance',
  'wsrep_local_cert_failures',
  'wsrep_local_bf_aborts',
  'wsrep_apply_window',
  'wsrep_commit_window'
);"
```

Wichtige Signale:

| Signal | Gesund | Problemhinweis |
| --- | --- | --- |
| `wsrep_cluster_status` | `Primary` | `non-Primary` oder keine Antwort |
| `wsrep_cluster_size` | erwartete Replikatanzahl | kleiner als erwartet |
| `wsrep_ready` | `ON` | `OFF` |
| `wsrep_local_state_comment` | `Synced` | `Joining`, `Donor`, `Initialized` |
| `wsrep_flow_control_paused` | nahe `0` | dauerhaft groesser `0` |
| `wsrep_local_recv_queue` | nahe `0` | wachsend oder dauerhaft hoch |
| `wsrep_local_send_queue` | nahe `0` | wachsend oder dauerhaft hoch |
| `wsrep_local_cert_failures` | stabil oder langsam wachsend | deutlicher Anstieg bei konkurrierenden Writes |
| `wsrep_local_bf_aborts` | stabil oder langsam wachsend | deutlicher Anstieg bei lokalen Transaktionsabbruechen |

Prometheus/Grafana:

```bash
kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80
```

Im Dashboard `MariaDB Galera Lab` besonders auf diese Panels achten:

| Panel | Bedeutung |
| --- | --- |
| `Galera Cluster Size` | wie viele Galera-Member im aktuellen Component sichtbar sind |
| `Galera Ready Members` | wie viele Member `wsrep_ready=ON` melden |
| `Galera Connected Members` | wie viele Member mit dem Cluster verbunden sind |
| `MariaDB Ready Pods` | Kubernetes-Readiness der MariaDB-Pods |
| `MariaDB Restarts 15m` | Prozess-/Container-Neustarts im Beobachtungsfenster |
| `Flow Control Paused By Instance` | Anteil der Zeit, in der Writes gebremst wurden |
| `Flow Control Sent And Received` | welche Instanz Flow Control ausloest oder empfaengt |
| `Galera Local Queues` | lokale Receive-/Send-Queues, wichtig bei langsamen Nodes |
| `Galera Apply And Commit Windows` | Apply-/Commit-Verhalten und Zertifizierungsabstand |
| `Galera Replication Bytes` | Replikationsvolumen pro Instanz |
| `Galera Writesets` | replizierte und empfangene Writesets pro Instanz |
| `Node CPU Busy` | CPU-Saettigung des ueberlasteten Workers |
| `Node Load Per CPU` | Run-Queue-Druck relativ zur CPU-Anzahl |
| `Node Memory Used` | Speicherdruck als Nebenursache |
| `MariaDB Container Memory Working Set` | cgroup-Working-Set des MariaDB-Containers pro Pod; fuer Allocator-Vergleiche Baseline, Peak und Recovery vergleichen |

## Pod-Ausfall

Ausloesen:

```bash
make scenario-pod
```

Manuell ausloesen:

```bash
kubectl -n mariadb delete pod mariadb-cluster-0
```

Feststellen:

```bash
kubectl -n mariadb get pods -o wide --watch
kubectl -n mariadb logs mariadb-cluster-0 -c mariadb --tail=200
```

Reparatur:

```bash
kubectl -n mariadb get pods -o wide
kubectl -n mariadb describe pod mariadb-cluster-0
```

Ein geloeschter StatefulSet-Pod sollte ohne manuelle Reparatur neu erstellt werden. Manuell eingreifen musst du erst, wenn der Ersatz-Pod nicht `Running` und `Ready` wird oder Galera nicht wieder `Synced` erreicht.

Wenn der Pod nicht neu startet, Events und PVC-Zuordnung pruefen:

```bash
kubectl -n mariadb get events --sort-by=.lastTimestamp
kubectl -n mariadb get pvc
```

## Prozess-Ausfall

Ausloesen:

```bash
make scenario-process
```

Manuell ausloesen:

```bash
kubectl -n mariadb exec mariadb-cluster-0 -c mariadb -- sh -c 'pkill -TERM mariadbd || pkill -TERM mysqld'
```

Feststellen:

```bash
kubectl -n mariadb get pod mariadb-cluster-0 -o jsonpath='{.status.containerStatuses[*].restartCount}{"\n"}'
kubectl -n mariadb logs mariadb-cluster-0 -c mariadb --previous --tail=200
kubectl -n mariadb logs mariadb-cluster-0 -c mariadb --tail=200
```

Reparatur:

```bash
kubectl -n mariadb delete pod mariadb-cluster-0
kubectl -n mariadb get pods -o wide --watch
```

Der Container sollte durch Kubernetes neu gestartet werden. Den Pod loeschen solltest du nur, wenn der Container haengt, Readiness nicht zurueckkommt oder die Logs einen blockierten lokalen Zustand zeigen. Danach Galera-Status pruefen. `wsrep_cluster_status=Primary`, `wsrep_ready=ON` und `wsrep_local_state_comment=Synced` muessen wieder erreicht werden.

## Einfach Belegter Worker

Ausloesen:

```bash
make scenario-node-single
```

Der Runner stoppt `k3s-agent` auf dem Worker mit den wenigsten Galera-Pods.

Feststellen:

```bash
kubectl get nodes
kubectl -n mariadb get pods -o wide
kubectl -n mariadb get events --sort-by=.lastTimestamp
```

Erwartung im Zwei-Worker-Layout: Die zwei Replikate auf dem anderen Worker koennen Quorum halten. Trotzdem sind Scheduling und Recovery eingeschraenkt.

Reparatur:

```bash
ssh -o UserKnownHostsFile=.artifacts/known_hosts -o StrictHostKeyChecking=accept-new root@<worker-public-ip> 'systemctl start k3s-agent'
kubectl uncordon <worker-name>
kubectl get nodes
kubectl -n mariadb get pods -o wide
```

Danach Galera pruefen:

```bash
kubectl -n mariadb exec -it mariadb-cluster-0 -c mariadb -- mariadb -uroot -p -e "
SHOW GLOBAL STATUS WHERE Variable_name IN ('wsrep_cluster_status','wsrep_cluster_size','wsrep_ready','wsrep_local_state_comment');"
```

## Doppelt Belegter Worker

Ausloesen:

```bash
make scenario-node-double
```

Vergleich einfach gegen doppelt belegten Worker:

```bash
make scenario-node-single
make scenario-export
# Worker manuell reparieren und Galera-Sync abwarten.
make scenario-node-double
make scenario-export
```

Feststellen:

```bash
kubectl get nodes
kubectl -n mariadb get pods -o wide
kubectl -n mariadb exec -it mariadb-cluster-0 -c mariadb -- mariadb -uroot -p -e "
SHOW GLOBAL STATUS WHERE Variable_name IN ('wsrep_cluster_status','wsrep_cluster_size','wsrep_ready','wsrep_local_state_comment');"
```

Erwartung im Zwei-Worker-Layout: Faellt der doppelt belegte Worker aus, bleibt voraussichtlich nur ein Galera-Replikat erreichbar. Quorum-Verlust ist dann ein erwartetes Ergebnis des Lab-Layouts.

Reparatur:

```bash
ssh -o UserKnownHostsFile=.artifacts/known_hosts -o StrictHostKeyChecking=accept-new root@<worker-public-ip> 'systemctl start k3s-agent'
kubectl uncordon <worker-name>
kubectl get nodes
kubectl -n mariadb get pods -o wide
```

Wenn Galera nicht automatisch in `Primary` zurueckkehrt, zuerst keine Daten loeschen. Logs und letzten Primary-Stand sichern:

```bash
make scenario-export
kubectl -n mariadb logs -l app.kubernetes.io/instance=mariadb-cluster -c mariadb --tail=400
```

Dann pruefen, ob alle Pods wieder laufen und welcher Pod nicht `Synced` ist:

```bash
kubectl -n mariadb get pods -o wide
for pod in $(kubectl -n mariadb get pod -l app.kubernetes.io/instance=mariadb-cluster -o name); do
  kubectl -n mariadb exec "${pod#pod/}" -c mariadb -- mariadb -uroot -p -e "
  SHOW GLOBAL STATUS WHERE Variable_name IN ('wsrep_cluster_status','wsrep_cluster_size','wsrep_ready','wsrep_local_state_comment');"
done
```

## Netzwerk-Isolation

Ausloesen:

```bash
make scenario-network
```

Der Runner blockiert privaten Node-Traffic auf einem Worker mit kommentierten iptables-Regeln.

Quorum-kritische Variante auf dem doppelt belegten Worker:

```bash
make scenario-network-double
```

Erwartung im Zwei-Worker-Layout: Die Single-Worker-Variante sollte haeufig einen Primary Component mit zwei erreichbaren Galera-Membern behalten. Die Double-Worker-Variante kann wie der doppelte Node-Ausfall zum Quorum-Verlust fuehren.

Feststellen:

```bash
kubectl get nodes
kubectl -n mariadb get pods -o wide
kubectl -n mariadb get events --sort-by=.lastTimestamp
```

Auf dem Worker:

```bash
ssh -o UserKnownHostsFile=.artifacts/known_hosts -o StrictHostKeyChecking=accept-new root@<worker-public-ip> 'iptables -S | grep galera-lab-scenario-network'
```

Reparatur auf dem betroffenen Worker:

```bash
ssh -o UserKnownHostsFile=.artifacts/known_hosts -o StrictHostKeyChecking=accept-new root@<worker-public-ip> "
while iptables -D INPUT -s 10.20.0.0/16 -m comment --comment galera-lab-scenario-network -j DROP 2>/dev/null; do :; done
while iptables -D OUTPUT -d 10.20.0.0/16 -m comment --comment galera-lab-scenario-network -j DROP 2>/dev/null; do :; done
systemctl start k3s-agent
"
kubectl uncordon <worker-name>
```

Danach sicherstellen, dass keine Szenario-Regeln mehr aktiv sind:

```bash
ssh -o UserKnownHostsFile=.artifacts/known_hosts -o StrictHostKeyChecking=accept-new root@<worker-public-ip> 'iptables -S | grep galera-lab-scenario-network || true'
kubectl get nodes
kubectl -n mariadb get pods -o wide
```

## Degradiertes Privates Netzwerk

Ziel: Statt eines harten Netzwerkausfalls kontrollierte Latenz und Paketverlust auf dem privaten Worker-Interface erzeugen.

Ausloesen:

```bash
make scenario-network-degrade
```

Parameter:

```bash
make scenario-network-degrade \
  NETEM_WORKER=single \
  NETEM_DELAY_MS=250 \
  NETEM_LOSS_PERCENT=10 \
  OBSERVE_SECONDS=90
```

Feststellen:

```bash
kubectl -n mariadb get pods -o wide
kubectl -n mariadb exec -it mariadb-cluster-0 -c mariadb -- mariadb -uroot -p -e "
SHOW GLOBAL STATUS WHERE Variable_name IN (
  'wsrep_cluster_status',
  'wsrep_ready',
  'wsrep_flow_control_paused',
  'wsrep_local_recv_queue',
  'wsrep_local_send_queue',
  'wsrep_local_state_comment'
);"
```

Auf dem Worker:

```bash
ssh -o UserKnownHostsFile=.artifacts/known_hosts -o StrictHostKeyChecking=accept-new root@<worker-public-ip> 'tc qdisc show'
```

Der Runner entfernt die `tc netem`-Regel nach der Messung automatisch. Manuelle Reparatur, falls der Lauf abbricht:

```bash
ssh -o UserKnownHostsFile=.artifacts/known_hosts -o StrictHostKeyChecking=accept-new root@<worker-public-ip> "
iface=\$(ip -o -4 addr show | awk -v ip='<worker-private-ip>' 'index(\$4, ip \"/\") == 1 {print \$2; exit}')
test -z \"\$iface\" || tc qdisc del dev \"\$iface\" root 2>/dev/null || true
"
```

Danach Galera-Status und Queues pruefen. Interessant sind steigende Queue-Werte, Flow Control und laengere Wiederanlaufzeit ohne vollstaendigen Node-Ausfall.

## Flow-Control Durch Node-Ueberlast

Ziel: Einen Worker gezielt ueberlasten und gleichzeitig Schreiblast erzeugen, damit Galera Flow Control sichtbar wird.

Ausloesen auf dem doppelt belegten Worker:

```bash
make scenario-overload-flow-control
```

Parameter:

```bash
make scenario-overload-flow-control \
  OVERLOAD_TARGET=double \
  OVERLOAD_SECONDS=180 \
  OVERLOAD_OBSERVE_SECONDS=180 \
  OVERLOAD_CPU_WORKERS=6 \
  OVERLOAD_WRITE_ROWS=250 \
  OVERLOAD_WRITE_BYTES=4096
```

Feststellen:

```bash
kubectl -n mariadb get pods -o wide
kubectl -n mariadb get jobs,pods -l app.kubernetes.io/name=galera-lab-scenario-overload
kubectl -n mariadb logs -l app.kubernetes.io/name=galera-lab-scenario-overload --tail=50
```

Galera-Metriken:

```bash
kubectl -n mariadb exec -it mariadb-cluster-0 -c mariadb -- mariadb -uroot -p -e "
SHOW GLOBAL STATUS WHERE Variable_name IN (
  'wsrep_flow_control_paused',
  'wsrep_flow_control_sent',
  'wsrep_flow_control_recv',
  'wsrep_local_recv_queue',
  'wsrep_local_send_queue',
  'wsrep_cert_deps_distance',
  'wsrep_apply_oooe',
  'wsrep_apply_window',
  'wsrep_commit_window'
);"
```

Problem ist nachgestellt, wenn `wsrep_flow_control_paused` wiederholt groesser `0` ist oder `wsrep_local_recv_queue` beziehungsweise `wsrep_local_send_queue` waehrend der Schreiblast wachsen. In Grafana muessen Flow-Control- und Queue-Panels zur gleichen Zeit ausschlagen.

Reparatur:

```bash
kubectl -n mariadb delete job -l app.kubernetes.io/name=galera-lab-scenario-overload --ignore-not-found=true
kubectl -n mariadb get pods -o wide
```

Danach Schreiblast stoppen, Status pruefen und warten, bis Queues abgebaut sind:

```bash
kubectl -n mariadb exec -it mariadb-cluster-0 -c mariadb -- mariadb -uroot -p -e "
SHOW GLOBAL STATUS WHERE Variable_name IN (
  'wsrep_cluster_status',
  'wsrep_ready',
  'wsrep_local_state_comment',
  'wsrep_flow_control_paused',
  'wsrep_local_recv_queue',
  'wsrep_local_send_queue'
);"
```

Falls Queues nicht sinken:

```bash
kubectl -n mariadb get pods -o wide
kubectl -n mariadb describe pod <auffaelliger-pod>
kubectl -n mariadb logs <auffaelliger-pod> -c mariadb --tail=300
```

Den auffaelligen Pod nur nach Export und Logpruefung neu starten:

```bash
make scenario-export
kubectl -n mariadb delete pod <auffaelliger-pod>
```

Wenn der Cluster danach nicht sauber wird, nicht weiter an einzelnen Pods drehen. Zustand sichern und die Lab-Umgebung kontrolliert abbauen:

```bash
make scenario-export
make stop
```

## Zertifizierungskonflikte Durch Konkurrierende Writes

Ziel: Mehrere kurzlebige Writer-Jobs schreiben parallel gegen unterschiedliche Galera-Pod-IPs auf dieselbe Tabellenzeile. Dadurch lassen sich Galera-Zertifizierungskonflikte und lokale Abbrueche beobachten, ohne Nodes oder Pods gezielt ausfallen zu lassen.

Ausloesen:

```bash
make scenario-certification-conflict
```

Parameter:

```bash
make scenario-certification-conflict \
  CERT_CONFLICT_SECONDS=90 \
  OBSERVE_SECONDS=90
```

Feststellen:

```bash
kubectl -n mariadb get jobs,pods -l app.kubernetes.io/name=galera-lab-scenario-conflict
kubectl -n mariadb logs -l app.kubernetes.io/name=galera-lab-scenario-conflict --tail=50
kubectl -n mariadb exec -it mariadb-cluster-0 -c mariadb -- mariadb -uroot -p -e "
SHOW GLOBAL STATUS WHERE Variable_name IN (
  'wsrep_cluster_status',
  'wsrep_ready',
  'wsrep_local_state_comment',
  'wsrep_local_cert_failures',
  'wsrep_local_bf_aborts',
  'wsrep_cert_deps_distance',
  'wsrep_apply_window',
  'wsrep_commit_window'
);"
```

Erwartung: Der Cluster bleibt `Primary` und `Synced`, waehrend die Konfliktzaehler oder Writer-Fehler steigen koennen. Das Szenario ist damit eher ein Konsistenz- und Lasttest als ein Ausfalltest.

Reparatur:

```bash
kubectl -n mariadb delete job -l app.kubernetes.io/name=galera-lab-scenario-conflict --ignore-not-found=true
kubectl -n mariadb get pods -o wide
```

## Memory-Allocator-Vergleich

Ziel: Den Default-Systemallocator, jemalloc und tcmalloc bei identischer MariaDB-Version vergleichen. Das Szenario befuellt eine lokale `TEMPORARY`-Tabelle mit `ENGINE=MEMORY`, behaelt sie fuer eine feste Dauer und entfernt sie wieder. Gemessen wird ausschliesslich `container_memory_working_set_bytes` des MariaDB-Containers.

```bash
export ALLOCATOR_IMAGE=registry.example/galera/mariadb-allocators:<tag>

make cluster-allocator ALLOCATOR=system ALLOCATOR_IMAGE="$ALLOCATOR_IMAGE"
make scenario-allocator-memory ALLOCATOR=system

make cluster-allocator ALLOCATOR=jemalloc ALLOCATOR_IMAGE="$ALLOCATOR_IMAGE"
make scenario-allocator-memory ALLOCATOR=jemalloc

make cluster-allocator ALLOCATOR=tcmalloc ALLOCATOR_IMAGE="$ALLOCATOR_IMAGE"
make scenario-allocator-memory ALLOCATOR=tcmalloc
```

`cluster-allocator` rollt MariaDB/Galera bewusst neu aus. Nach jedem Wechsel muessen alle Member wieder `Synced` und `wsrep_ready=ON` sein, bevor der naechste Lauf startet. Im Grafana-Panel **MariaDB Container Memory Working Set** pro Lauf Baseline, Peak, Wert direkt nach `DROP TEMPORARY TABLE` und Zeit bis zur Rueckkehr in die Naehe der Baseline notieren.

Abbruch und Artefaktsicherung:

```bash
kubectl -n mariadb delete job \
  -l app.kubernetes.io/name=galera-lab-scenario-allocator-memory \
  --ignore-not-found=true
make scenario-export
```

## Abschluss

Nach jedem Szenario:

```bash
make scenario-export
kubectl -n mariadb get pods -o wide
kubectl get nodes
```

Vor dem Loeschen:

```bash
make scenario-export
make stop
```
