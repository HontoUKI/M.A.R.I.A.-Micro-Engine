.PHONY: help install model check lint test run serve

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

# ---------------------------------------------------------------- checks

check: lint test  ## Lint and test — the gate before every commit

lint:  ## Run ruff
	ruff check .

test:  ## Run the test suite
	python -m pytest -q
