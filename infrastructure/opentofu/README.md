# OpenTofu: Konfigurationsreferenz Des Labs

Dieses Root-Modul verwaltet die Hetzner-Infrastruktur des Galera-Labs. Es definiert einen K3s-Admin und standardmaessig zwei Worker, ein privates Netzwerk mit Subnetz, eine SSH-Firewall und eine Spread Placement Group. Betriebssystem-Konfiguration und K3s folgen durch Ansible; MariaDB und Monitoring durch Helm und Operatoren.

Hier steht, **welche Einstellung wo definiert ist und was sie bewirkt**. 

## Dateien Und Verantwortlichkeiten

Alle `.tf`-Dateien in diesem Verzeichnis bilden zusammen ein Root-Modul; ihre Dateinamen legen keine Ausfuehrungsreihenfolge fest.

| Datei | Definitionen | Verantwortung |
| --- | --- | --- |
| [versions.tf](versions.tf) | `terraform`, `required_providers`, `provider.hcloud` | CLI-Untergrenze, Provider-Version und Authentifizierung aus der Umgebung. |
| [variables.tf](variables.tf) | Zehn `variable`-Bloecke | Eingabetypen, Defaults und lokale Validierungsregeln. |
| [terraform.tfvars.example](terraform.tfvars.example) | Beispielbelegung aller Eingaben | Vorlage; wird wegen `.example` nicht automatisch geladen. |
| Lokale `terraform.tfvars` | Installationsspezifische Werte | Wird automatisch geladen und bleibt unversioniert. Nicht mit echten Werten committen. |
| [locals.tf](locals.tf) | `local.common_labels` | Wiederverwendete Cloud-Labels `managed_by`, `phase`, `project`. |
| [network.tf](network.tf) | `hcloud_network.private`, `hcloud_network_subnet.private` | Node-Underlay und konkretes Cloud-Subnetz. |
| [firewall.tf](firewall.tf) | `hcloud_firewall.ssh` | Gemeinsame Firewall fuer oeffentlichen SSH-Zugriff. |
| [servers.tf](servers.tf) | SSH-Key-Data-Source, Placement Group, `hcloud_server.node` | VM-Erzeugung pro Map-Eintrag und Netzwerk-/Firewall-Anbindung. |
| [outputs.tf](outputs.tf) | Sechs Outputs | Schnittstelle zu Inventory, Tunneln, Szenarien und Diagnose. |
| [.terraform.lock.hcl](.terraform.lock.hcl) | Gewaehlter Provider und Pruefsummen | Versioniertes Installations-Lockfile, kein Infrastruktur-State. |
| [Makefile](Makefile) | Variablendatei-Erzeugung und CLI-Wrapper | Lokale Hilfsablaeufe; einzelne Ziele koennen Dateien oder Cloud-Ressourcen veraendern. |

## Eingaben Mit Herkunft Und Wirkung

Die Deklarationen und alle Defaults stehen in [variables.tf](variables.tf). Die Tabelle beschreibt Repository-Defaults, keine aus einem laufenden State ausgelesenen Ist-Werte.

| Variable | Default / Pflicht | Verwendung | Wirkung und Aenderungsfolge |
| --- | --- | --- | --- |
| `project_name` | `galera-lab` | `locals.tf`, `network.tf`, `firewall.tf`, `servers.tf` | Praefix fuer Netzwerk-, Firewall- und Placement-Group-Namen, ausserdem Cloud-Label. Waehlt kein Hetzner-Projekt und praefixiert keine Servernamen. |
| `ssh_key_name` | Pflicht | `data.hcloud_ssh_key.admin.name` in `servers.tf` | Sucht einen bestehenden oeffentlichen SSH-Key im Projekt des Tokens. Die resultierende ID wird bei VM-Erzeugung injiziert; eine andere Key-ID kann alle Server ersetzen. |
| `admin_cidr` | Pflicht | `rule.source_ips` in `firewall.tf` | Eine erlaubte Quelladresse beziehungsweise ein Quellnetz fuer oeffentliches TCP/22. IPv4-Einzelhost: `/32`, IPv6-Einzelhost: `/128`. Falsche Quelle verhindert neue SSH-Verbindungen. |
| `location` | `nbg1` | `hcloud_server.node.location` | Standort aller VMs. Muss zur Network Zone, Kapazitaet und Hardware passen. Standortwechsel ersetzt Server. |
| `server_type` | `cx23` | `hcloud_server.node.server_type` | Hardwareklasse aller VMs, einschliesslich Admin. Aendert Kapazitaet und Kosten; Resizing kann Server ausschalten. |
| `image` | `ubuntu-24.04` | `hcloud_server.node.image` | Ausgangsimage bei Erzeugung. Imagewechsel ist keine Paketaktualisierung im Gast, sondern kann alle VMs ersetzen. |
| `network_cidr` | `10.20.0.0/16` | `hcloud_network.private.ip_range` | Gesamter privater Node-Adressraum. Unabhaengig vom K3s-Pod-/Service-CIDR. Aenderungen mit Subnetz, Node-IP-Map und Szenario-CIDRs koordinieren. |
| `subnet_cidr` | `10.20.0.0/24` | `hcloud_network_subnet.private.ip_range` | Subnetz fuer die festen privaten Node-IP-Adressen; muss innerhalb des Netzwerks liegen. |
| `network_zone` | `eu-central` | `hcloud_network_subnet.private.network_zone` | Hetzner-Routingzone des Subnetzes, nicht Kubernetes-Zone oder einzelnes Rechenzentrum. Muss den Serverstandort umfassen. |
| `node_definitions` | Drei Eintraege, siehe unten | `for_each` und Serverattribute; Outputs | Vollstaendige Map aus Node-Namen zu Rolle und IP. Hinzufuegen erzeugt eine VM; Entfernen oder Umbenennen eines Schluessels kann die bestehende VM loeschen. |

Die Standardsicht von `node_definitions`:

| Map-Schluessel / VM-Name | `role` | `private_ip` | Spaetere Verwendung |
| --- | --- | --- | --- |
| `k3s-admin` | `admin` | `10.20.0.2` | Ansible-Gruppe `k3s_admin`, einzelne K3s-Control-Plane mit embedded etcd. |
| `k3s-worker-1` | `worker` | `10.20.0.3` | Ansible-Gruppe `k3s_workers`, Galera-Workloads zugelassen. |
| `k3s-worker-2` | `worker` | `10.20.0.4` | Zweiter Worker; drei Galera-Pods teilen sich beide Worker. |

### Validierungen

`project_name` muss 3 bis 63 Zeichen lang sein und das definierte Kleinbuchstaben-/Ziffern-/Bindestrichmuster erfuellen. SSH-Key-Name und Image duerfen nicht leer sein. Standort und Servertyp werden nur gegen Namensmuster geprueft, nicht auf reale Verfuegbarkeit. `network_zone` besitzt eine feste Allow-Liste.

Fuer `node_definitions` werden mindestens drei Eintraege, genau ein Admin, mindestens zwei Worker, erlaubte Rollen und unterschiedliche IP-Zeichenketten verlangt. `cidrhost("${node.private_ip}/32", 0)` prueft Parsebarkeit, erzwingt aber entgegen dem bisherigen Fehlertext nicht vollstaendig die IPv4-Adressfamilie. Ebenso fehlen lokale Pruefungen fuer Node-Hostnamen, Zugehoerigkeit der Node-IP zum Subnetz, reservierte Adressen, Subnetz-im-Netzwerk und Standort-in-Network-Zone. Die CIDR-Pruefungen des Netzes akzeptieren syntaktisch auch Werte, die fuer das hier beabsichtigte IPv4-Lab ungeeignet sind.

`admin_cidr` lehnt die beiden literalen Vollnetzangaben `0.0.0.0/0` und `::/0` ab. Das ist keine vollstaendige Sicherheitsrichtlinie fuer Quellnetze: Ein sehr breites, aber anders angegebenes Netz wird damit nicht grundsaetzlich verhindert. Die Wirkung einer Eingabe ist vor einer Anwendung weiterhin fachlich zu pruefen. Die Dokumentation beschreibt diese Grenzen; die Validierungslogik wurde nicht erweitert.

## Fest Eingebaute Ressourcen-Einstellungen

Diese Werte sind keine `var.*`-Eingaben. Eine Aenderung erfolgt im jeweiligen `.tf`-Block.

| Einstellung | Definition | Bedeutung |
| --- | --- | --- |
| `required_version = ">= 1.8.0"` | `versions.tf` | Mindestversion der CLI, keine exakte Versionsbindung und keine automatische Installation. Im Projekt wird `tofu` verwendet. |
| `source = "hetznercloud/hcloud"` | `versions.tf` | Provider-Adresse; unter OpenTofu hier als `registry.opentofu.org/hetznercloud/hcloud` gelockt. |
| `version = "~> 1.68"` | `versions.tf` | Erlaubt `>= 1.68.0` und `< 2.0.0`, nicht nur `1.68.x`. Das Lockfile waehlt derzeit konkret `1.68.0`. |
| `provider "hcloud" {}` | `versions.tf` | Leerer Block nutzt Provider-Defaults und `HCLOUD_TOKEN` aus der Prozessumgebung. Keine Token-Variable in HCL. |
| Kein Backend-Block | Gesamtes Modul | Standardmaessig lokaler State; kein eingerichteter Remote-State und keine konfigurierte State-Verschluesselung. |
| `managed_by`, `phase`, `project` | `locals.tf` | Cloud-Metadaten: `opentofu`, `phase-1`, `var.project_name`. Keine Kubernetes-Labels oder automatische Zugriffsregeln. |
| Subnetz-`type = "cloud"` | `network.tf` | Cloud-Subnetz fuer Cloud-Server. |
| Placement-`type = "spread"` | `servers.tf` | Unterschiedliche physische Hosts fuer VMs derselben Gruppe. Garantiert keine Trennung zweier Pods innerhalb einer Worker-VM. |
| `for_each = var.node_definitions` | `servers.tf` | Eine Serverinstanz je stabilen Map-Schluessel. |
| `name = each.key` | `servers.tf` | Servername entspricht dem Map-Schluessel, ohne `project_name`-Praefix. |
| `merge(..., { role = ... })` | `servers.tf` | Ergaenzt gemeinsame Cloud-Labels um die konfigurierte Rolle. |
| `ssh_keys = [...]` | `servers.tf` | Verwendet die ID des bestehenden Public Keys fuer die Initialisierung aller VMs. Kein Key-Rotationsmechanismus im laufenden Gast. |
| `firewall_ids = [...]` | `servers.tf` | Direkte Zuordnung der gemeinsamen Firewall; kein Label-Selector notwendig. |
| `placement_group_id = ...` | `servers.tf` | Fuegt jede konfigurierte VM derselben Spread-Gruppe hinzu. |
| `ipv4_enabled`, `ipv6_enabled = true` | `servers.tf`, `public_net` | Oeffentliche Adressen werden zugewiesen; IPv4 wird fuer Inventory und SSH verwendet. Keine separate `hcloud_primary_ip`-Ressource modelliert. |
| `network.subnet_id` | `servers.tf` | Referenziert das konkrete Subnetz statt einer impliziten Subnetzauswahl. |
| `network.ip` | `servers.tf` | Feste private Adresse aus der Node-Map. Gast-Netzkonfiguration erfolgt spaeter durch Ansible. |
| `alias_ips = []` | `servers.tf` | Explizit keine zusaetzlichen Alias-IP-Adressen; vermeidet den in der Provider-Dokumentation beschriebenen Netzwerk-Diff-Sonderfall. |
| `backups = false` | `servers.tf` | Keine automatischen Hetzner-Serverbackups. Keine Aussage ueber Replikationskonsistenz oder logische DB-Backups. |
| `shutdown_before_deletion = true` | `servers.tf` | Provider versucht geordnetes Herunterfahren vor VM-Loeschung. Kein Kubernetes-Drain, keine Quorum-gerechte Reihenfolge und keine Datensicherung. |
| `depends_on = [subnet]` | `servers.tf` | Explizite Abhaengigkeit vom Subnetz; im aktuellen Code auch durch `subnet_id` bereits implizit gegeben. |
| `direction="in"`, `protocol="tcp"`, `port="22"` | `firewall.tf` | Einzige explizite eingehende Freigabe fuer normalen oeffentlichen Client-Traffic. `source_ips` kommt aus `admin_cidr`; `description` ist nur Dokumentation. |

Die genaue Bedeutung der Serverfelder beschreibt der [Provider fuer Version 1.68.0](https://github.com/hetznercloud/terraform-provider-hcloud/blob/v1.68.0/docs/resources/server.md). Hetzner-Firewalls erlauben ohne ausgehende Regeln grundsaetzlich ausgehende Verbindungen und zugehoerigen Rueckverkehr; sie filtern kein privates Cloud-Netzwerk. Details und Infrastruktur-Ausnahmen stehen in der [Firewall-FAQ](https://docs.hetzner.com/cloud/firewalls/faq/).

## Variablen Setzen Und Prioritaeten Verstehen

Der Make-Helper erzeugt bei fehlender Datei nur `ssh_key_name` und `admin_cidr` in `terraform.tfvars`; die weiteren Werte kommen dann aus den Defaults. Eine bereits existierende Datei wird nicht ueberschrieben. Die Beispieldatei zeigt dagegen alle Eingaben.

Die uebliche Prioritaet im Root-Modul ist, von niedrig nach hoch: `default`, `TF_VAR_<name>` aus der Umgebung, `terraform.tfvars`, `terraform.tfvars.json`, lexikographisch sortierte `*.auto.tfvars`/`*.auto.tfvars.json` und zuletzt explizite `-var`/`-var-file` in Aufrufreihenfolge. Ein Map-Wert aus einer hoeheren Quelle **ersetzt die gesamte Map**, statt einzelne Eintraege in den Default zu mergen. Siehe [OpenTofu Input Variables](https://opentofu.org/docs/language/values/variables/).

Die Shell-Datei `.env` ist keine von OpenTofu automatisch geladene Variablendatei. Fuer direkte Aufrufe werden benoetigte Umgebungsvariablen gemaess Projekt-README exportiert. `HCLOUD_TOKEN` ist eine Provider-Umgebungsvariable, kein `TF_VAR_*`-Wert. `ANSIBLE_PRIVATE_KEY_FILE`, `K3S_VERSION`, `KUBECONFIG` und MariaDB-/Grafana-Passwoerter gehoeren anderen Schichten an.

| Make-Variable | Definition / Default | Wirkung |
| --- | --- | --- |
| `TOFU` | Lokales `Makefile`: `tofu` | CLI fuer diese Make-Ziele; Projektregel bleibt OpenTofu. |
| `TFVARS` | Lokales `Makefile`: `terraform.tfvars` | Dateiname fuer Erzeugung/Aktualisierung. Ein anderer Name wird nicht automatisch per `-var-file` an Plan/Apply uebergeben. |
| `SSH_KEY_NAME` | Lokales `Makefile`: `hetzner-galera-lab (laptop)` | Wird nur beim Generieren der Variablendatei als `ssh_key_name` geschrieben. Aendert keine existierende Datei. |
| `ADMIN_IP_URL` | Lokales `Makefile`: `https://api.ipify.org` | Ermittelt die oeffentliche IPv4 des ausgehenden HTTP-Pfads. VPN/Proxy koennen dazu fuehren, dass SSH eine andere Quell-IP verwendet. |
| `OPENTOFU_DIR` | Root-`Makefile`: `infrastructure/opentofu` | Zielverzeichnis der delegierten Befehle. |

`tofu-refresh-admin-cidr` aktualisiert lokal eine am Zeilenanfang erwartete `admin_cidr`-Zuweisung per Textmuster oder haengt sie an. Es ist kein vollstaendiger HCL-Editor. Bei manuell anders formatierten Dateien die Aenderung auf doppelte Definitionen pruefen. Der Helper stellt Dateirechte auf `0600`; er aendert damit noch keine Cloud-Firewall.

## Outputs Und Ihre Konsumenten

Alle Outputs stehen in [outputs.tf](outputs.tf). `tofu output` liest gespeicherte Ergebnisse aus State und ist kein Live-Cloud- oder SSH-Check.

| Output | Quelle | Verwendung |
| --- | --- | --- |
| `server_public_ipv4` | Provider-Attribute der Server | Dynamisches Ansible-Inventory, SSH-Tunnel und Szenario-SSH. |
| `server_public_ipv6` | Provider-Attribute der Server | Erste Adresse des zugewiesenen IPv6-Netzes; aktuell informativ. |
| `server_private_ipv4` | Eingabe `node_definitions` | Ansible-`private_ip`, K3s-Kommunikation und Szenario-Zieladresse. Kein aus dem Gast verifizierter Wert. |
| `node_roles` | Eingabe `node_definitions` | Inventory-Gruppen `k3s_admin` und `k3s_workers`. |
| `network_id` | `hcloud_network.private.id` | Cloud-Netzwerkidentitaet fuer Diagnose/Integration. |
| `firewall_id` | `hcloud_firewall.ssh.id` | Identitaet der an alle Server gebundenen Firewall. |

Der Vertrag ist in [tofu_inventory.py](../../bootstrap/ansible/inventory/tofu_inventory.py) nachvollziehbar. Public-IP-, Private-IP- und Rollen-Maps muessen dieselben Node-Schluessel enthalten. Eine Umbenennung von Output oder Rolle kann deshalb nachgelagerte Werkzeuge brechen, auch wenn `tofu validate` erfolgreich bleibt.

## Befehle Und Nebenwirkungen

Die folgenden Aufrufe beziehen sich auf das Repository-Root. Schreibende Cloud-Operationen beduerfen einer ausdruecklichen Freigabe fuer den konkreten Vorgang.

| Befehl | Lokale Wirkung | Cloud-Wirkung |
| --- | --- | --- |
| `tofu fmt -check -recursive` | Prueft Formatierung. | Keine. |
| `tofu -chdir=infrastructure/opentofu init -backend=false` | Installiert Provider, kann `.terraform/` und Lockfile aktualisieren; Backend-Initialisierung ausgesetzt. | Keine Ressourcen-Erzeugung. |
| `tofu -chdir=infrastructure/opentofu validate` | Prueft Konfiguration und Provider-Schema. | Kein Nachweis realer Cloud-Verfuegbarkeit. |
| `make tofu-tfvars` | Erzeugt lokale Variablendatei, fragt externe IP-Seite ab. | Keine Hetzner-Aenderung. |
| `make tofu-refresh-admin-cidr` | Schreibt aktuelle `/32`-Quelle lokal. | Keine Hetzner-Aenderung bis Apply. |
| `make tofu-plan` | Kann tfvars erzeugen und Init ausfuehren, zeigt anschliessend Plan. | Liest normalerweise Cloud-Zustand; wendet keine Ressourcen-Aenderung an. |
| `tofu -chdir=infrastructure/opentofu output server_public_ipv4` | Liest State-Output. | Kein Live-Refresh. |
| `make -C infrastructure/opentofu apply` | Initialisiert/prueft und plant erneut, fragt Bestaetigung. | Erstellt, aendert oder loescht gemaess neuem Plan. |
| `make start` | Aktualisiert Admin-CIDR, prueft, plant, ruft Apply und danach Ansible/Helm auf. | Vollstaendiger schreibender Aufbauablauf. |
| `make destroy` | Zeigt Destroy-Plan, startet danach gesonderten Destroy mit Bestaetigung. | Loescht verwaltete Infrastruktur und lokale VM-Daten. |
| `make stop` | Fuehrt Destroy und anschliessend lokale Bereinigung aus, bei normalem seriellen Make. | Wie Destroy. Nicht mit `make -j` ausfuehren: beide Voraussetzungen koennten parallel laufen. |
| `make clean-local` | Loescht unter anderem lokalen State und Kubeconfig. | Loescht keine Cloud-Ressourcen; kann die Verwaltung laufender Ressourcen erschweren. |

Das optionale TFLint-Ziel sucht aktuell gezielt `~/go/bin/tflint`. Ein nur anderswo im `PATH` installiertes TFLint wird dort nicht erkannt; fuer eine manuelle Pruefung den tatsaechlichen Installationspfad verwenden. Keine neue Pflichtabhaengigkeit erforderlich.