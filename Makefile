# Model names come from .env so every target uses the same one (falls back to
# these defaults when .env is absent or does not set them).
-include .env
CHAT_MODEL ?= gemma3:12b
EMBED_MODEL ?= nomic-embed-text

.ONESHELL:
.PHONY: help start install model check lint test run serve scenario

help:  ## Show the available commands
	@grep -hE '^[a-z.]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- onboarding

start:  ## Guided setup: pick a model, install, test, then try it out
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from .env.example."; fi
	printf "Which chat model? [%s]: " "$(CHAT_MODEL)"
	read model; model=$${model:-$(CHAT_MODEL)}
	grep -v '^CHAT_MODEL=' .env > .env.tmp && echo "CHAT_MODEL=$$model" >> .env.tmp && mv .env.tmp .env
	echo ">> Using $$model (saved to .env)"
	echo ">> Installing dependencies..."
	pip install -q -r requirements.txt -r requirements-dev.txt
	echo ">> Pulling models into Ollama (Ctrl-C to skip if you use the OpenAI backend)..."
	ollama pull "$$model" || true
	ollama pull $(EMBED_MODEL) || true
	echo ">> Running tests..."
	python -m pytest -q
	echo
	echo ">> See a real 100-message run:  docs/EXAMPLE_RUN.md"
	echo ">> Start the server + web UI:    make run   (then open http://127.0.0.1:8000/)"
	printf "Try a quick 10-message scenario now? [y/N]: "
	read yn
	if [ "$$yn" = "y" ] || [ "$$yn" = "Y" ]; then \
		python tools/run_scenario.py --character megumin --length 10 --memory --model "$$model"; \
	fi

# ---------------------------------------------------------------- quickstart

install:  ## Install runtime + dev dependencies
	pip install -r requirements.txt -r requirements-dev.txt

model:  ## Pull the .env chat + embed models into Ollama
	ollama pull $(CHAT_MODEL)
	ollama pull $(EMBED_MODEL)

run:  ## Run the dev server (autoreload) with the web shell on :8000
	uvicorn app.main:app --reload

serve:  ## Run the server without autoreload
	uvicorn app.main:app --host 0.0.0.0 --port 8000

# ---------------------------------------------------------------- scenarios

# Drive a scripted conversation through a character on a live Ollama model.
# The model comes from .env (CHAT_MODEL); pass extra options via ARGS, e.g.:
#   make scenario ARGS="--character kaguya --length showcase --memory --web-search"
#   make scenario ARGS="--character megumin --length boundary --affection 8 --trust 6"
# Lengths: 10 | 20 | 30 | coding | boundary | showcase.
scenario:  ## Run a scenario against Ollama (model from .env; options via ARGS=...)
	python tools/run_scenario.py --model $(CHAT_MODEL) $(ARGS)

# ---------------------------------------------------------------- checks

check: lint test  ## Lint and test — the gate before every commit

lint:  ## Run ruff
	ruff check .

test:  ## Run the test suite
	python -m pytest -q
