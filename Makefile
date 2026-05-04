.PHONY: help install docker-build test lint clean helper-query paste-compare compare docker-compare \
        _check_compare _check_schema

.DEFAULT_GOAL := help

# Default output path for generated SQL. Override with: make compare ... OUT=foo/bar.sql
OUT ?= out/compare.sql

help: ## Show this help and the standard workflow
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	    awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Standard workflow (local, macOS):"
	@echo "  1. make install                                   # one-time setup"
	@echo "  2. make helper-query                              # paste output into DBeaver, run, copy result cell"
	@echo "  3. make paste-compare OLD=public.old_view \\"
	@echo "                        NEW=public.new_view \\"
	@echo "                        KEY=id"
	@echo "                                                    # reads the JSON from your clipboard"
	@echo "  4. open $(OUT) in DBeaver and run each section"
	@echo ""
	@echo "Cross-platform / teammates (Docker):"
	@echo "  1. make docker-build                              # one-time"
	@echo "  2. make helper-query                              # (host needs uv) — or copy from README"
	@echo "  3. save DBeaver result to schemas/old_view.json"
	@echo "  4. make docker-compare OLD=public.old_view \\"
	@echo "                         NEW=public.new_view \\"
	@echo "                         KEY=id \\"
	@echo "                         SCHEMA=schemas/old_view.json"
	@echo ""
	@echo "Variables:"
	@echo "  OLD     fully-qualified old view/table  (e.g. public.patient_view)"
	@echo "  NEW     fully-qualified new view/table  (e.g. public.patient_view_v2)"
	@echo "  KEY     join key, comma-separated for composite (e.g. id  or  patient_id,visit_date)"
	@echo "  SCHEMA  path to JSON file (compare / docker-compare only)"
	@echo "  OUT     output SQL path                 (default: $(OUT))"
	@echo ""

install: ## One-time setup: install uv if needed, create .venv, install dev deps
	@command -v uv >/dev/null 2>&1 || { \
	    echo "uv not found. Installing..."; \
	    curl -LsSf https://astral.sh/uv/install.sh | sh; \
	}
	uv venv --python 3.12
	uv pip install -e ".[dev]"

docker-build: ## Build the Docker image (tag: query-compare:latest)
	docker build -t query-compare .

test: ## Run pytest
	uv run pytest -q

lint: ## Run ruff
	uv run ruff check .

clean: ## Remove .venv, caches, and out/
	rm -rf .venv .pytest_cache .ruff_cache .mypy_cache out
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name '*.egg-info' -prune -exec rm -rf {} +

helper-query: ## Print the DBeaver helper SQL (copy, paste into DBeaver, run, copy result cell)
	@uv run query-compare --print-helper-query

paste-compare: _check_compare ## Generate SQL from clipboard (macOS pbpaste). Vars: OLD NEW KEY [OUT]
	@mkdir -p $(dir $(OUT))
	pbpaste | uv run query-compare --old '$(OLD)' --new '$(NEW)' --key '$(KEY)' -o '$(OUT)'
	@echo "→ wrote $(OUT)"

compare: _check_compare _check_schema ## Generate SQL from a JSON file. Vars: OLD NEW KEY SCHEMA [OUT]
	@mkdir -p $(dir $(OUT))
	uv run query-compare --old '$(OLD)' --new '$(NEW)' --key '$(KEY)' --schema '$(SCHEMA)' -o '$(OUT)'
	@echo "→ wrote $(OUT)"

docker-compare: _check_compare _check_schema ## Same as compare, via Docker. Vars: OLD NEW KEY SCHEMA [OUT]
	@mkdir -p $(dir $(OUT))
	docker run --rm -i -v '$(CURDIR):/work' query-compare \
	    --old '$(OLD)' --new '$(NEW)' --key '$(KEY)' \
	    --schema '/work/$(SCHEMA)' -o '/work/$(OUT)'
	@echo "→ wrote $(OUT)"

# ---- internal helpers (not shown in help) ----

_check_compare:
	@if [ -z '$(OLD)' ]; then echo 'error: OLD is required (e.g. OLD=public.old_view)';            exit 1; fi
	@if [ -z '$(NEW)' ]; then echo 'error: NEW is required (e.g. NEW=public.new_view)';            exit 1; fi
	@if [ -z '$(KEY)' ]; then echo 'error: KEY is required (e.g. KEY=id  or  KEY=id,visit_date)';  exit 1; fi

_check_schema:
	@if [ -z '$(SCHEMA)' ];   then echo 'error: SCHEMA is required (e.g. SCHEMA=schemas/old.json)';  exit 1; fi
	@if [ ! -f '$(SCHEMA)' ]; then echo "error: SCHEMA file not found: $(SCHEMA)";                   exit 1; fi
