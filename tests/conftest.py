"""Shared fixtures.

Every test runs in its own temporary working directory so the repository's
real `data/` is never read or written. LLM calls are always stubbed — no
test may talk to a live Ollama server.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def isolated_runtime_dir(tmp_path, monkeypatch):
    """Isolate relative paths like `data/*.json` into a throwaway dir."""
    monkeypatch.chdir(tmp_path)
    return tmp_path
