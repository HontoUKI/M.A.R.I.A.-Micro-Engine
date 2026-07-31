# Every recipe is a single portable command: no grep/awk/cp/printf/read, which
# do not exist in cmd.exe or PowerShell. Anything shell-shaped lives in
# tools/dev.py instead, so `make` behaves the same on Windows, macOS and Linux.
#
# Override the interpreter if `python` is not your launcher:
#   make test PYTHON=py
PYTHON ?= python

# Model names come from .env so every target uses the same one (falls back to
# these defaults when .env is absent or does not set them).
-include .env
CHAT_MODEL ?= gemma3:12b
EMBED_MODEL ?= nomic-embed-text

.PHONY: help start install model check lint test run serve scenario

help:  ## Show the available commands
	@$(PYTHON) tools/dev.py help

# ---------------------------------------------------------------- onboarding

start:  ## Guided setup: pick a model, install, test, then try it out
	@$(PYTHON) tools/dev.py start

# ---------------------------------------------------------------- quickstart

install:  ## Install runtime + dev dependencies
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

model:  ## Pull the .env chat + embed models into Ollama
	ollama pull $(CHAT_MODEL)
	ollama pull $(EMBED_MODEL)

run:  ## Run the dev server (autoreload) with the web shell on :8000
	$(PYTHON) -m uvicorn app.main:app --reload

serve:  ## Run the server without autoreload
	$(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# ---------------------------------------------------------------- scenarios

# Drive a scripted conversation through a character on a live Ollama model.
# The model comes from .env (CHAT_MODEL); pass extra options via ARGS, e.g.:
#   make scenario ARGS="--character kaguya --length showcase --memory --web-search"
#   make scenario ARGS="--scene 3_days_before --vision-model gemma3:4b"
# Lengths: 10 | 20 | 30 | coding | boundary | showcase.
scenario:  ## Run a scenario against Ollama (model from .env; options via ARGS=...)
	$(PYTHON) tools/run_scenario.py --model $(CHAT_MODEL) $(ARGS)

# ---------------------------------------------------------------- checks

check: lint test  ## Lint and test — the gate before every commit

lint:  ## Run ruff
	$(PYTHON) -m ruff check .

test:  ## Run the test suite
	$(PYTHON) -m pytest -q
