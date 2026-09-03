# Every recipe is a single portable command: no grep/awk/cp/printf/read, which
# do not exist in cmd.exe or PowerShell. Anything shell-shaped lives in
# tools/dev.py instead, so `make` behaves the same on Windows, macOS and Linux.
#
# The interpreter is the repo's own .venv when there is one, because that is
# where `make install` put the dependencies and where every other tool here
# looks. Without this, `make run` reaches for the system python, finds no
# `requests`, and reports a missing module about a repository that is fully
# installed — a true error about the wrong thing.
#
# Override it if you keep your environment elsewhere:
#   make test PYTHON=py
VENV_PYTHON := $(wildcard .venv/Scripts/python.exe) $(wildcard .venv/bin/python)
PYTHON ?= $(if $(VENV_PYTHON),$(firstword $(VENV_PYTHON)),python)

# Model names come from .env so every target uses the same one (falls back to
# these defaults when .env is absent or does not set them).
-include .env
CHAT_MODEL ?= gemma3:12b
EMBED_MODEL ?= nomic-embed-text
# Which character sits in the world for `make play`.
CHARACTER ?= yukina

.PHONY: help start install model check lint test run serve game play scenario

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

# Attach to a game router that is ALREADY running (docs/GAME_PORT.md). It is not
# started here and cannot be: attaching to what somebody else runs is the
# boundary that keeps this engine out of launching programs on your machine.
game:  ## Run the server attached to a game router (GAME_PORT), checking it first
	@$(PYTHON) tools/dev.py game

# Sit in the world and talk in ITS chat, which is where a game companion lives.
# Runs beside the HTTP app rather than inside it: that surface is
# request/response, and a companion in a chat is a loop that outlives a request.
play:  ## Talk to a character in the game chat (CHARACTER=yukina)
	@$(PYTHON) tools/play.py --character $(CHARACTER)

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
