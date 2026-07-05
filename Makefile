.PHONY: help install model check lint test run serve scenario

help:  ## Show the available commands
	@grep -E '^[a-z.]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- quickstart

install:  ## Install runtime + dev dependencies
	pip install -r requirements.txt -r requirements-dev.txt

model:  ## Pull the default chat model into Ollama
	ollama pull gemma3:12b

run:  ## Run the dev server (autoreload) with the web shell on :8000
	uvicorn app.main:app --reload

serve:  ## Run the server without autoreload
	uvicorn app.main:app --host 0.0.0.0 --port 8000

# ---------------------------------------------------------------- scenarios

# Drive a scripted conversation through a character on a live Ollama model.
# Pass options via ARGS, e.g.:
#   make scenario ARGS="--character kaguya --length showcase --memory --web-search"
#   make scenario ARGS="--character megumin --length boundary --affection 8 --trust 6"
# Lengths: 10 | 20 | 30 | coding | boundary | showcase.
scenario:  ## Run a scenario against Ollama (options via ARGS=...)
	python tools/run_scenario.py $(ARGS)

# ---------------------------------------------------------------- checks

check: lint test  ## Lint and test — the gate before every commit

lint:  ## Run ruff
	ruff check .

test:  ## Run the test suite
	python -m pytest -q
