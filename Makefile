.DEFAULT_GOAL := help
.PHONY: help install check-venv check-env up test typecheck eval eval-fresh eval-answers

PYTHON ?= python3
label ?= dev
k ?= 5
threshold ?= 0.6
workers ?= 4
args ?=

help:
	@echo "make install                   create .venv (Python >= 3.12) and install requirements-dev.txt"
	@echo "make up                        build and run api + qdrant in the foreground (Ctrl-C stops)"
	@echo "make test                      run the pytest suite"
	@echo "make typecheck                 run pyright (standard mode)"
	@echo "make eval label=<name> [k=5] [threshold=0.6] [args='--no-compare']"
	@echo "make eval-fresh label=<name>   drop the eval collection, re-ingest and run"
	@echo "make eval-answers label=<name> [k=5] [threshold=0.6] [workers=4] [args='--no-compare']  retrieval + answer layer (LLM calls)"

install:
	@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
		|| { echo "Python >= 3.12 required, found: $$($(PYTHON) --version 2>&1). Try: make install PYTHON=python3.12"; exit 1; }
	@test -d .venv || $(PYTHON) -m venv .venv
	@.venv/bin/pip install -r requirements-dev.txt

check-venv:
	@test -x .venv/bin/python || { echo "No .venv found. Run: make install"; exit 1; }

check-env:
	@test -f .env || { echo "No .env found. Run: cp .env.example .env   then set OPENAI_API_KEY and GEMINI_API_KEY in it"; exit 1; }

up: check-env
	@docker compose up --build

test: check-venv
	@.venv/bin/pytest

typecheck: check-venv
	@.venv/bin/pyright

eval: check-venv check-env
	@set -a; . ./.env; set +a; PYTHONPATH=src .venv/bin/python -m evaluation.run --label $(label) --k $(k) --threshold $(threshold) $(args)

eval-fresh: check-venv check-env
	@set -a; . ./.env; set +a; curl -sf -X DELETE "$${QDRANT_URL:-http://localhost:6333}/collections/$${EVAL_QDRANT_COLLECTION:-eval_chunks}" > /dev/null || true
	@$(MAKE) --no-print-directory eval label=$(label) k=$(k) threshold=$(threshold) args="$(args)"

eval-answers: check-venv check-env
	@$(MAKE) --no-print-directory eval label=$(label) k=$(k) threshold=$(threshold) args="--answers --workers $(workers) $(args)"
