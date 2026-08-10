# MethylPipeline developer shortcuts (requires repo-root .venv)
.PHONY: help venv install test test-ci schemas diagrams docs docs-serve docs-pdf docs-customer check-docs check-layout bootstrap-verify

VENV := .venv/bin
PY := $(VENV)/python

help:
	@echo "Targets: venv install test test-ci schemas diagrams docs docs-serve docs-pdf docs-customer check-docs check-layout bootstrap-verify"

venv:
	bash scripts/setup_host.sh --with-deps

install:
	bash scripts/install_all.sh

test:
	source .venv/bin/activate && bash scripts/run_tests.sh

test-ci:
	source .venv/bin/activate && bash scripts/run_tests_ci.sh

schemas:
	source .venv/bin/activate && bash scripts/export_config_schemas.sh && methyl-export-task-schemas && methyl-export-action-catalog && methyl-export-domain-schemas

diagrams:
	bash scripts/render_diagrams.sh

docs:
	source .venv/bin/activate && pip install -q -r docs-requirements.txt && mkdocs build --strict

docs-serve:
	source .venv/bin/activate && pip install -q -r docs-requirements.txt && mkdocs serve

docs-customer:
	source .venv/bin/activate && pip install -q -r docs-requirements.txt && mkdocs build -f mkdocs.customer.yml --strict

docs-pdf:
	bash scripts/build_docs_pdf.sh

check-docs:
	bash scripts/check_doc_links.sh
	bash scripts/check_doc_freshness.sh
	source .venv/bin/activate && pip install -q -r docs-requirements.txt && mkdocs build --strict
	python scripts/check_no_step_config.py

check-layout:
	bash scripts/verify_work_layout.sh

bootstrap-verify:
	bash scripts/bootstrap_distributed_workers.sh --verify
