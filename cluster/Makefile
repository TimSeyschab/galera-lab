HELM ?= helm
KUBECTL ?= kubectl
-include ../.env
export KUBECONFIG
CLUSTER_DIR := $(abspath $(CURDIR))
KUBECONFIG ?= $(CLUSTER_DIR)/../.artifacts/kubeconfig
ifneq ($(filter-out /%,$(KUBECONFIG)),)
KUBECONFIG := $(abspath $(CLUSTER_DIR)/../$(KUBECONFIG))
endif

MARIADB_OPERATOR_REPO ?= https://mariadb-operator.github.io/mariadb-operator
MARIADB_OPERATOR_VERSION ?= 26.6.0
PROMETHEUS_REPO ?= https://prometheus-community.github.io/helm-charts
PROMETHEUS_STACK_VERSION ?= 88.0.1

MARIADB_NAMESPACE ?= mariadb
MONITORING_NAMESPACE ?= monitoring
MARIADB_ROOT_SECRET ?= mariadb-root
GRAFANA_ADMIN_SECRET ?= grafana-admin
GRAFANA_ADMIN_USER ?= admin
ALLOCATOR ?= system
ALLOCATOR_IMAGE ?=

.PHONY: repos namespaces secret grafana-secret dashboard operator monitoring galera allocator install verify

repos:
	$(HELM) repo add mariadb-operator $(MARIADB_OPERATOR_REPO) --force-update
	$(HELM) repo add prometheus-community $(PROMETHEUS_REPO) --force-update
	$(HELM) repo update

namespaces:
	KUBECONFIG=$(KUBECONFIG) $(KUBECTL) create namespace $(MARIADB_NAMESPACE) --dry-run=client -o yaml | KUBECONFIG=$(KUBECONFIG) $(KUBECTL) apply -f -
	KUBECONFIG=$(KUBECONFIG) $(KUBECTL) create namespace $(MONITORING_NAMESPACE) --dry-run=client -o yaml | KUBECONFIG=$(KUBECONFIG) $(KUBECTL) apply -f -

secret: namespaces
	@test -n "$${MARIADB_ROOT_PASSWORD:-}" || (echo "MARIADB_ROOT_PASSWORD must be set and is never stored in the repository" >&2; exit 1)
	KUBECONFIG=$(KUBECONFIG) $(KUBECTL) -n $(MARIADB_NAMESPACE) create secret generic $(MARIADB_ROOT_SECRET) --from-literal=root-password="$${MARIADB_ROOT_PASSWORD}" --dry-run=client -o yaml | KUBECONFIG=$(KUBECONFIG) $(KUBECTL) apply -f -

grafana-secret: namespaces
	@test -n "$${GRAFANA_ADMIN_PASSWORD:-}" || (echo "GRAFANA_ADMIN_PASSWORD must be set and is never stored in the repository" >&2; exit 1)
	KUBECONFIG=$(KUBECONFIG) $(KUBECTL) -n $(MONITORING_NAMESPACE) create secret generic $(GRAFANA_ADMIN_SECRET) --from-literal=admin-user="$(GRAFANA_ADMIN_USER)" --from-literal=admin-password="$${GRAFANA_ADMIN_PASSWORD}" --dry-run=client -o yaml | KUBECONFIG=$(KUBECONFIG) $(KUBECTL) apply -f -

dashboard: namespaces
	KUBECONFIG=$(KUBECONFIG) $(KUBECTL) -n $(MONITORING_NAMESPACE) create configmap galera-dashboard --from-file=galera-dashboard.json=monitoring/galera-dashboard.json --dry-run=client -o yaml | KUBECONFIG=$(KUBECONFIG) $(KUBECTL) label --local -f - grafana_dashboard=1 -o yaml | KUBECONFIG=$(KUBECONFIG) $(KUBECTL) apply -f -

operator: repos namespaces
	KUBECONFIG=$(KUBECONFIG) $(HELM) upgrade --install mariadb-operator-crds mariadb-operator/mariadb-operator-crds --namespace $(MARIADB_NAMESPACE) --version $(MARIADB_OPERATOR_VERSION) --wait
	KUBECONFIG=$(KUBECONFIG) $(HELM) upgrade --install mariadb-operator mariadb-operator/mariadb-operator --namespace $(MARIADB_NAMESPACE) --version $(MARIADB_OPERATOR_VERSION) --values mariadb-operator/values.yaml --wait

monitoring: repos grafana-secret dashboard
	KUBECONFIG=$(KUBECONFIG) $(HELM) upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack --namespace $(MONITORING_NAMESPACE) --version $(PROMETHEUS_STACK_VERSION) --values monitoring/values.yaml --wait

galera: operator secret
	KUBECONFIG=$(KUBECONFIG) $(HELM) upgrade --install mariadb-cluster mariadb-operator/mariadb-cluster --namespace $(MARIADB_NAMESPACE) --version $(MARIADB_OPERATOR_VERSION) --values galera/values.yaml --wait

allocator: operator secret
	@test -n "$(ALLOCATOR_IMAGE)" || (echo "ALLOCATOR_IMAGE must name the image built from images/mariadb-allocators" >&2; exit 1)
	@test -f "galera/allocator-overlays/$(ALLOCATOR).yaml" || (echo "ALLOCATOR must be one of: system, jemalloc, tcmalloc" >&2; exit 1)
	@echo "Changing the allocator restarts MariaDB/Galera pods. Run one allocator at a time and wait for Synced before measuring."
	KUBECONFIG=$(KUBECONFIG) $(HELM) upgrade --install mariadb-cluster mariadb-operator/mariadb-cluster --namespace $(MARIADB_NAMESPACE) --version $(MARIADB_OPERATOR_VERSION) --values galera/values.yaml --values galera/allocator-overlays/$(ALLOCATOR).yaml --set-string mariadb.image=$(ALLOCATOR_IMAGE) --force-conflicts --wait

install: monitoring galera

verify:
	KUBECONFIG=$(KUBECONFIG) $(KUBECTL) -n $(MARIADB_NAMESPACE) get mariadb,pods,pvc,svc
	KUBECONFIG=$(KUBECONFIG) $(KUBECTL) -n $(MONITORING_NAMESPACE) get pods
	KUBECONFIG=$(KUBECONFIG) $(KUBECTL) -n $(MONITORING_NAMESPACE) get configmap galera-dashboard
