.PHONY: help install install-dev test lint format clean docker-build docker-run docker-shell

help: ## Show this help message
	@echo "MethylModeler - Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install the package in development mode
	poetry install

install-dev: ## Install the package with development dependencies
	poetry install --with dev

test: ## Run tests
	poetry run pytest tests/ -v

test-cov: ## Run tests with coverage
	poetry run pytest tests/ --cov=methyl_modeler --cov-report=html --cov-report=term

lint: ## Run linting checks
	poetry run flake8 methyl_modeler/
	poetry run mypy methyl_modeler/

format: ## Format code with black and isort
	poetry run black methyl_modeler/ tests/
	poetry run isort methyl_modeler/ tests/

clean: ## Clean up generated files
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf htmlcov/
	find . -type d -name __pycache__ -delete
	find . -type f -name "*.pyc" -delete

docker-build: ## Build Docker image
	docker compose build

docker-run: ## Run Docker container
	docker compose up -d

docker-shell: ## Open shell in running Docker container
	docker compose exec methyl-modeler bash

docker-stop: ## Stop Docker container
	docker compose down

check: format lint test ## Run all checks (format, lint, test)

build: clean ## Build distribution packages
	poetry build

publish: ## Publish to PyPI (use with caution)
	poetry publish

# Development helpers
create-data-dirs: ## Create data and results directories
	mkdir -p data results

example-run: ## Run example analysis (requires sample data)
	poetry run python examples/usage_example.py

cli-help: ## Show CLI help
	poetry run methyl-modeler --help

run: ## Run MethylModeler with config file
	@if [ -z "$(CONFIG)" ]; then \
		echo "Error: CONFIG variable is required"; \
		echo "Usage: make run CONFIG=path/to/config.json"; \
		exit 1; \
	fi
	python run_methyl_modeler.py $(CONFIG)

run-verbose: ## Run MethylModeler with verbose logging
	@if [ -z "$(CONFIG)" ]; then \
		echo "Error: CONFIG variable is required"; \
		echo "Usage: make run-verbose CONFIG=path/to/config.json"; \
		exit 1; \
	fi
	python run_methyl_modeler.py $(CONFIG) --verbose 