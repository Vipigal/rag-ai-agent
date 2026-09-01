.DEFAULT_GOAL := help
.PHONY: help eval eval-fresh test typecheck up

label ?= dev
k ?= 5
threshold ?= 0.6
args ?=

help:
	@echo "make eval label=<name> [k=5] [threshold=0.6] [args='--no-compare']"
	@echo "make eval-fresh label=<name>   drop the eval collection, re-ingest and run"
	@echo "make test                      run the pytest suite"
	@echo "make typecheck                 run pyright (standard mode)"
	@echo "make up                        start api + qdrant via docker compose"

eval:
	@set -a; . ./.env; set +a; PYTHONPATH=src .venv/bin/python -m evaluation.run --label $(label) --k $(k) --threshold $(threshold) $(args)

eval-fresh:
	@set -a; . ./.env; set +a; curl -sf -X DELETE "$${QDRANT_URL:-http://localhost:6333}/collections/$${EVAL_QDRANT_COLLECTION:-eval_chunks}" > /dev/null || true
	@$(MAKE) --no-print-directory eval label=$(label) k=$(k) threshold=$(threshold) args="$(args)"

test:
	@.venv/bin/pytest

typecheck:
	@.venv/bin/pyright

up:
	@docker compose up -d
