SHELL := /bin/bash

KUBECTL ?= kubectl
TOFU ?= tofu
SSH ?= ssh
SCENARIO_RUNNER ?= python3 scripts/galera_scenarios.py
SCENARIO ?= pod-delete
OBSERVE_SECONDS ?= 45
POLL_SECONDS ?= 5
ARTIFACT_DIR ?= ../.artifacts/scenarios
OVERLOAD_SECONDS ?= 120
OVERLOAD_OBSERVE_SECONDS ?= 120
OVERLOAD_CPU_WORKERS ?= 4
OVERLOAD_TARGET ?= double
OVERLOAD_WRITE_ROWS ?= 100
OVERLOAD_WRITE_BYTES ?= 2048

-include ../.env
export KUBECONFIG
export ANSIBLE_PRIVATE_KEY_FILE
export MARIADB_ROOT_PASSWORD

.PHONY: list run pod process network node-single node-double overload-flow-control export

list:
	$(SCENARIO_RUNNER) list

run:
	$(SCENARIO_RUNNER) run $(SCENARIO) --observe-seconds $(OBSERVE_SECONDS) --poll-seconds $(POLL_SECONDS) --artifact-dir $(ARTIFACT_DIR)

pod:
	$(MAKE) run SCENARIO=pod-delete

process:
	$(MAKE) run SCENARIO=process-kill

network:
	$(MAKE) run SCENARIO=network-isolate-single

node-single:
	$(MAKE) run SCENARIO=node-stop-single

node-double:
	$(MAKE) run SCENARIO=node-stop-double

overload-flow-control:
	SCENARIO_OVERLOAD_SECONDS=$(OVERLOAD_SECONDS) \
	SCENARIO_OVERLOAD_CPU_WORKERS=$(OVERLOAD_CPU_WORKERS) \
	SCENARIO_OVERLOAD_WORKER=$(OVERLOAD_TARGET) \
	SCENARIO_WRITE_ROWS=$(OVERLOAD_WRITE_ROWS) \
	SCENARIO_WRITE_BYTES=$(OVERLOAD_WRITE_BYTES) \
	$(SCENARIO_RUNNER) run node-overload-flow-control --observe-seconds $(OVERLOAD_OBSERVE_SECONDS) --poll-seconds $(POLL_SECONDS) --artifact-dir $(ARTIFACT_DIR)

export:
	$(SCENARIO_RUNNER) export --artifact-dir $(ARTIFACT_DIR)
