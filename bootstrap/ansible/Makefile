ANSIBLE ?= ansible
ANSIBLE_INVENTORY ?= ansible-inventory
ANSIBLE_PLAYBOOK ?= ansible-playbook
K3S_VERSION ?= v1.36.4+k3s1

.PHONY: inventory-graph syntax-check bootstrap kubeconfig tunnel

inventory-graph:
	$(ANSIBLE_INVENTORY) --graph

syntax-check:
	$(ANSIBLE_PLAYBOOK) --syntax-check site.yml

bootstrap:
	K3S_VERSION="$(K3S_VERSION)" $(ANSIBLE_PLAYBOOK) site.yml

kubeconfig:
	$(ANSIBLE_PLAYBOOK) access.yml

tunnel:
	python3 scripts/k3s-tunnel.py
