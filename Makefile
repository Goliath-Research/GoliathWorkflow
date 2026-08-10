# MethylPipeline developer shortcuts (requires repo-root .venv)
# Make uses /bin/sh by default (often dash); prefer bash for recipes that need it.
SHELL := /bin/bash
.PHONY: help venv install test test-ci schemas diagrams docs docs-serve docs-pdf docs-customer check-docs check-layout bootstrap-verify

VENV := .venv/bin
PY := $(VENV)/python
PIP := $(VENV)/pip
MKDOCS := $(VENV)/mkdocs

help:
	@echo "Targets: venv install test test-ci schemas diagrams docs docs-serve docs-pdf docs-customer check-docs check-layout bootstrap-verify"

venv:
	bash scripts/setup_host.sh --with-deps

install:
	bash scripts/install_all.sh

test:
	PATH="$(CURDIR)/$(VENV):$$PATH" bash scripts/run_tests.sh

test-ci:
	PATH="$(CURDIR)/$(VENV):$$PATH" bash scripts/run_tests_ci.sh

schemas:
	PATH="$(CURDIR)/$(VENV):$$PATH" bash scripts/export_config_schemas.sh
	PATH="$(CURDIR)/$(VENV):$$PATH" methyl-export-task-schemas
	PATH="$(CURDIR)/$(VENV):$$PATH" methyl-export-action-catalog
	PATH="$(CURDIR)/$(VENV):$$PATH" methyl-export-domain-schemas

diagrams:
	bash scripts/render_diagrams.sh

docs:
	$(PIP) install -q -r docs-requirements.txt
	$(MKDOCS) build --strict

docs-serve:
	$(PIP) install -q -r docs-requirements.txt
	$(MKDOCS) serve

docs-customer:
	$(PIP) install -q -r docs-requirements.txt
	$(MKDOCS) build -f mkdocs.customer.yml --strict

docs-pdf:
	bash scripts/build_docs_pdf.sh

check-docs:
	bash scripts/check_doc_links.sh
	bash scripts/check_doc_freshness.sh
	$(PIP) install -q -r docs-requirements.txt
	$(MKDOCS) build --strict
	$(PY) scripts/check_no_step_config.py

check-layout:
	bash scripts/verify_work_layout.sh

bootstrap-verify:
	bash scripts/bootstrap_distributed_workers.sh --verify
