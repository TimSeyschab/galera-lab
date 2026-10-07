SHELL := /bin/bash

-include .env
KUBECONFIG ?= .artifacts/kubeconfig
export KUBECONFIG

OPENTOFU_DIR := infrastructure/opentofu
ANSIBLE_DIR := bootstrap/ansible
CLUSTER_DIR := cluster
SCENARIOS_DIR := scenarios
KUBECTL ?= kubectl
ANSIBLE_PRIVATE_KEY_FILE ?= $(HOME)/.ssh/hetzner_galera_lab
export ANSIBLE_PRIVATE_KEY_FILE

.PHONY: start preflight stop destroy clean-local tofu-tfvars tofu-refresh-admin-cidr tofu-fmt tofu-init tofu-validate tofu-plan tofu-check tflint ansible-inventory ansible-check ansible-bootstrap ansible-kubeconfig k3s-tunnel cluster-repos cluster-operator cluster-monitoring cluster-galera cluster-dashboard cluster-install cluster-verify cluster-allocator scenarios-list scenario scenario-pod scenario-process scenario-network scenario-network-double scenario-network-degrade scenario-node-single scenario-node-double scenario-overload-flow-control scenario-certification-conflict scenario-allocator-memory scenario-export

preflight:
	@test -n "$${HCLOUD_TOKEN:-}" || (echo "HCLOUD_TOKEN must be exported" >&2; exit 1)
	@test -n "$${MARIADB_ROOT_PASSWORD:-}" || (echo "MARIADB_ROOT_PASSWORD must be exported" >&2; exit 1)
	@test -n "$${GRAFANA_ADMIN_PASSWORD:-}" || (echo "GRAFANA_ADMIN_PASSWORD must be exported" >&2; exit 1)
	@test -r "$(ANSIBLE_PRIVATE_KEY_FILE)" || (echo "SSH private key is not readable: $(ANSIBLE_PRIVATE_KEY_FILE)" >&2; exit 1)

start: preflight
	$(MAKE) tofu-refresh-admin-cidr
	$(MAKE) tofu-check
	$(MAKE) tofu-plan
	$(MAKE) -C $(OPENTOFU_DIR) apply
	$(MAKE) ansible-bootstrap
	$(MAKE) ansible-kubeconfig
	$(MAKE) k3s-tunnel & tunnel_pid=$$!; \
	trap 'kill "$$tunnel_pid" 2>/dev/null || true' EXIT; \
	for attempt in $$(seq 1 20); do \
		if ! kill -0 "$$tunnel_pid" 2>/dev/null; then \
			echo "K3s SSH tunnel stopped before the API became reachable" >&2; exit 1; \
		fi; \
		if KUBECONFIG="$(KUBECONFIG)" $(KUBECTL) get --raw=/version >/dev/null 2>&1; then break; fi; \
		sleep 1; \
	done; \
	if ! KUBECONFIG="$(KUBECONFIG)" $(KUBECTL) get --raw=/version >/dev/null 2>&1; then \
		echo "K3s API did not become reachable through the SSH tunnel" >&2; exit 1; \
	fi; \
	$(MAKE) cluster-install; \
	$(MAKE) cluster-verify

stop: destroy clean-local

destroy:
	@echo "This destroys the Hetzner infrastructure and all data on the lab nodes."
	$(MAKE) -C $(OPENTOFU_DIR) plan-destroy
	$(MAKE) -C $(OPENTOFU_DIR) destroy

clean-local:
	@echo "Removing local kubeconfig and OpenTofu state artifacts; keeping scenario exports."
	rm -f .artifacts/kubeconfig .artifacts/kubeconfig.* .artifacts/known_hosts .artifacts/known_hosts.* kubeconfig kubeconfig.*
	rm -f $(OPENTOFU_DIR)/terraform.tfstate $(OPENTOFU_DIR)/terraform.tfstate.backup
	rm -f $(OPENTOFU_DIR)/*.tfplan $(OPENTOFU_DIR)/*.plan $(OPENTOFU_DIR)/crash.log $(OPENTOFU_DIR)/crash.*.log
	rm -f $(OPENTOFU_DIR)/.terraform.tfstate.lock.info

tofu-tfvars:
	$(MAKE) -C $(OPENTOFU_DIR) tofu-tfvars

tofu-refresh-admin-cidr:
	$(MAKE) -C $(OPENTOFU_DIR) tofu-refresh-admin-cidr

tofu-fmt:
	$(MAKE) -C $(OPENTOFU_DIR) tofu-fmt

tofu-init:
	$(MAKE) -C $(OPENTOFU_DIR) tofu-init

tofu-validate:
	$(MAKE) -C $(OPENTOFU_DIR) tofu-validate

tofu-plan:
	$(MAKE) -C $(OPENTOFU_DIR) tofu-plan

tflint:
	$(MAKE) -C $(OPENTOFU_DIR) tflint

tofu-check:
	$(MAKE) -C $(OPENTOFU_DIR) tofu-check

ansible-inventory:
	$(MAKE) -C $(ANSIBLE_DIR) inventory-graph

ansible-check:
	$(MAKE) -C $(ANSIBLE_DIR) syntax-check

ansible-bootstrap:
	$(MAKE) -C $(ANSIBLE_DIR) bootstrap

ansible-kubeconfig:
	$(MAKE) -C $(ANSIBLE_DIR) kubeconfig

k3s-tunnel:
	$(MAKE) -C $(ANSIBLE_DIR) tunnel

cluster-repos:
	$(MAKE) -C $(CLUSTER_DIR) repos

cluster-operator:
	$(MAKE) -C $(CLUSTER_DIR) operator

cluster-monitoring:
	$(MAKE) -C $(CLUSTER_DIR) monitoring

cluster-galera:
	$(MAKE) -C $(CLUSTER_DIR) galera

cluster-allocator:
	$(MAKE) -C $(CLUSTER_DIR) allocator

cluster-dashboard:
	$(MAKE) -C $(CLUSTER_DIR) dashboard

cluster-install:
	$(MAKE) -C $(CLUSTER_DIR) install

cluster-verify:
	$(MAKE) -C $(CLUSTER_DIR) verify

scenarios-list:
	$(MAKE) -C $(SCENARIOS_DIR) list

scenario:
	$(MAKE) -C $(SCENARIOS_DIR) run

scenario-pod:
	$(MAKE) -C $(SCENARIOS_DIR) pod

scenario-process:
	$(MAKE) -C $(SCENARIOS_DIR) process

scenario-network:
	$(MAKE) -C $(SCENARIOS_DIR) network

scenario-network-double:
	$(MAKE) -C $(SCENARIOS_DIR) network-double

scenario-network-degrade:
	$(MAKE) -C $(SCENARIOS_DIR) network-degrade

scenario-node-single:
	$(MAKE) -C $(SCENARIOS_DIR) node-single

scenario-node-double:
	$(MAKE) -C $(SCENARIOS_DIR) node-double

scenario-overload-flow-control:
	$(MAKE) -C $(SCENARIOS_DIR) overload-flow-control

scenario-certification-conflict:
	$(MAKE) -C $(SCENARIOS_DIR) certification-conflict

scenario-allocator-memory:
	$(MAKE) -C $(SCENARIOS_DIR) allocator-memory

scenario-export:
	$(MAKE) -C $(SCENARIOS_DIR) export
