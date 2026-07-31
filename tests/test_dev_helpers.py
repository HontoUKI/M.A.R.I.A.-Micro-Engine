"""The Makefile's cross-platform helpers (tools/dev.py).

These exist because grep/awk/cp/printf/read are absent on Windows, so the logic
must live in Python and stay correct on every platform.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _load_dev():
    spec = importlib.util.spec_from_file_location("dev_helpers", _ROOT / "tools" / "dev.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dev = _load_dev()


# ---------------------------------------------------------------- help


def test_target_pattern_matches_documented_targets():
    assert dev._TARGET.match("test:  ## Run the test suite").groups() == (
        "test", "Run the test suite",
    )
    assert dev._TARGET.match("check: lint test  ## Lint and test").group(1) == "check"


def test_target_pattern_ignores_undocumented_and_comments():
    assert dev._TARGET.match("PYTHON ?= python") is None
    assert dev._TARGET.match("# just a comment") is None
    assert dev._TARGET.match("silent:") is None  # no ## description


def test_show_help_lists_the_real_makefile_targets(capsys):
    assert dev.show_help() == 0
    out = capsys.readouterr().out
    for target in ("help", "start", "install", "run", "test", "scenario"):
        assert target in out


# ---------------------------------------------------------------- .env


def test_read_env_parses_and_skips_comments(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\n\nCHAT_MODEL=gemma3:12b\nBAD LINE\nX = 1\n", encoding="utf-8")
    monkeypatch.setattr(dev, "_ENV", env)
    values = dev._read_env()
    assert values["CHAT_MODEL"] == "gemma3:12b"
    assert values["X"] == "1"
    assert "BAD LINE" not in values


def test_set_env_value_replaces_in_place_and_keeps_the_rest(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# keep me\nCHAT_MODEL=old\nWEB_SEARCH=false\n", encoding="utf-8")
    monkeypatch.setattr(dev, "_ENV", env)
    dev._set_env_value("CHAT_MODEL", "new-model")
    text = env.read_text(encoding="utf-8")
    assert "CHAT_MODEL=new-model" in text
    assert "CHAT_MODEL=old" not in text
    assert "# keep me" in text and "WEB_SEARCH=false" in text


def test_set_env_value_appends_when_missing(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("WEB_SEARCH=false\n", encoding="utf-8")
    monkeypatch.setattr(dev, "_ENV", env)
    dev._set_env_value("CHAT_MODEL", "fresh")
    assert "CHAT_MODEL=fresh" in env.read_text(encoding="utf-8")


# ---------------------------------------------------------------- prompts


def test_ask_falls_back_to_the_default_without_a_terminal(monkeypatch):
    def no_input(_prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", no_input)
    assert dev._ask("model? ", "gemma3:12b") == "gemma3:12b"


def test_ask_returns_the_answer_when_given(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _p: "  qwen3:8b  ")
    assert dev._ask("model? ", "default") == "qwen3:8b"


# ---------------------------------------------------------------- commands


def test_missing_optional_tool_is_skipped_not_fatal(monkeypatch, capsys):
    monkeypatch.setattr(dev.shutil, "which", lambda _name: None)
    dev._run(["ollama", "pull", "x"], optional=True)  # must not raise
    assert "skipped" in capsys.readouterr().out


def test_missing_required_tool_raises(monkeypatch):
    import pytest

    monkeypatch.setattr(dev.shutil, "which", lambda _name: None)
    with pytest.raises(SystemExit):
        dev._run(["definitely-not-installed"])


def test_main_rejects_an_unknown_command(capsys):
    argv = sys.argv
    try:
        sys.argv = ["dev.py", "nonsense"]
        assert dev.main() == 2
    finally:
        sys.argv = argv
    assert "unknown command" in capsys.readouterr().err
