.PHONY: help build helper-query compare compare-file clean _check_compare_file

.DEFAULT_GOAL := help

IMAGE := query-compare
OUT   ?= out/compare.sql

help: ## Show this help and the standard workflow
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	    awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Standard workflow:"
	@echo "  1. make build                 # one-time (and after code changes)"
	@echo "  2. make helper-query          # paste output into DBeaver, run, copy result cell"
	@echo "  3. make compare               # interactive: paste JSON, then new name, old name, key"
	@echo "  4. open $(OUT) in DBeaver and run each section"
	@echo ""
	@echo "Non-interactive (scripted) alternative:"
	@echo "  3a. save the DBeaver result to schemas/old_view.json"
	@echo "  3b. make compare-file OLD=public.v_opt_tracker_old NEW=public.v_opt_tracker \\"
	@echo "                        KEY=record_id SCHEMA=schemas/old_view.json"
	@echo ""
	@echo "Variables (compare-file only):"
	@echo "  OLD     fully-qualified old view/table  (e.g. public.v_opt_tracker_old)"
	@echo "  NEW     fully-qualified new view/table  (e.g. public.v_opt_tracker)"
	@echo "  KEY     join key, comma-separated for composite (e.g. record_id  or  patient_id,visit_date)"
	@echo "  SCHEMA  path to JSON file"
	@echo "  OUT     output SQL path                 (default: $(OUT))"
	@echo ""

build: ## Build the Docker image (run once, and again after code changes)
	docker build -t $(IMAGE) .

helper-query: ## Print the DBeaver helper SQL (paste into DBeaver, run, copy result cell)
	@docker run --rm $(IMAGE) --print-helper-query

compare: ## Interactive: prompts for JSON, new name, old name, key. Writes $(OUT).
	@mkdir -p $(dir $(OUT))
	@docker run --rm -it -v '$(CURDIR):/work' $(IMAGE) -o '/work/$(OUT)'
	@echo "→ wrote $(OUT)"

compare-file: _check_compare_file ## Non-interactive. Vars: OLD NEW KEY SCHEMA [OUT]
	@mkdir -p $(dir $(OUT))
	@docker run --rm -v '$(CURDIR):/work' $(IMAGE) \
	    --old '$(OLD)' --new '$(NEW)' --key '$(KEY)' \
	    --schema '/work/$(SCHEMA)' -o '/work/$(OUT)'
	@echo "→ wrote $(OUT)"

clean: ## Remove out/
	rm -rf out

# ---- internal helpers (not shown in help) ----

_check_compare_file:
	@if [ -z '$(OLD)' ];      then echo 'error: OLD is required (e.g. OLD=public.v_opt_tracker_old)';   exit 1; fi
	@if [ -z '$(NEW)' ];      then echo 'error: NEW is required (e.g. NEW=public.v_opt_tracker)';       exit 1; fi
	@if [ -z '$(KEY)' ];      then echo 'error: KEY is required (e.g. KEY=record_id)';                  exit 1; fi
	@if [ -z '$(SCHEMA)' ];   then echo 'error: SCHEMA is required (e.g. SCHEMA=schemas/old.json)';     exit 1; fi
	@if [ ! -f '$(SCHEMA)' ]; then echo "error: SCHEMA file not found: $(SCHEMA)";                      exit 1; fi
