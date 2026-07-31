"""Cross-platform helpers behind the Makefile.

The `help` and `start` targets used to be POSIX shell (grep, awk, cp, printf,
read, mv), which simply do not exist in cmd.exe / PowerShell — so on Windows
those targets failed. Python is already a hard dependency of this project, so
the logic lives here instead and behaves identically on every platform.

    python tools/dev.py help
    python tools/dev.py start
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

# Target descriptions contain characters outside the legacy Windows code pages
# (cp866/cp1251), which would otherwise raise on print. Same guard the scenario
# runner uses.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]
_MAKEFILE = _ROOT / "Makefile"
_ENV = _ROOT / ".env"
_ENV_EXAMPLE = _ROOT / ".env.example"

DEFAULT_CHAT_MODEL = "gemma3:12b"
DEFAULT_EMBED_MODEL = "nomic-embed-text"

# `target:  ## description`
_TARGET = re.compile(r"^([a-z.][a-z.-]*):.*?##\s*(.+)$")


def _color(text: str, code: str) -> str:
    """ANSI colour, but only when writing to a real terminal."""
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


def show_help() -> int:
    """List the documented Makefile targets (replaces grep|awk)."""
    if not _MAKEFILE.is_file():
        print("Makefile not found", file=sys.stderr)
        return 1
    rows = []
    for line in _MAKEFILE.read_text(encoding="utf-8").splitlines():
        match = _TARGET.match(line)
        if match:
            rows.append((match.group(1), match.group(2).strip()))
    for name, description in sorted(set(rows)):
        print(f"  {_color(f'{name:<12}', '36')} {description}")
    return 0


def _read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if _ENV.is_file():
        for line in _ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def _set_env_value(key: str, value: str) -> None:
    """Rewrite one KEY=value line in .env, preserving everything else."""
    lines = _ENV.read_text(encoding="utf-8").splitlines() if _ENV.is_file() else []
    out, replaced = [], False
    for line in lines:
        if line.strip().startswith(f"{key}="):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    _ENV.write_text("\n".join(out) + "\n", encoding="utf-8")


def _run(args: list[str], *, optional: bool = False) -> None:
    """Run a command, reporting rather than exploding when it is missing."""
    if shutil.which(args[0]) is None and args[0] != sys.executable:
        message = f"(skipped: {args[0]} is not installed)"
        if optional:
            print(message)
            return
        raise SystemExit(message)
    result = subprocess.run(args, cwd=_ROOT, check=False)
    if result.returncode != 0 and not optional:
        raise SystemExit(result.returncode)


def _ask(prompt: str, default: str = "") -> str:
    try:
        answer = input(prompt).strip()
    except EOFError:  # non-interactive shell: take the default
        answer = ""
    return answer or default


def start() -> int:
    """Guided setup: pick a model, install, pull, test, then offer a scenario."""
    if not _ENV.is_file() and _ENV_EXAMPLE.is_file():
        shutil.copyfile(_ENV_EXAMPLE, _ENV)
        print("Created .env from .env.example.")

    env = _read_env()
    current = env.get("CHAT_MODEL") or DEFAULT_CHAT_MODEL
    embed = env.get("EMBED_MODEL") or DEFAULT_EMBED_MODEL

    model = _ask(f"Which chat model? [{current}]: ", current)
    _set_env_value("CHAT_MODEL", model)
    print(f">> Using {model} (saved to .env)")

    print(">> Installing dependencies...")
    _run([sys.executable, "-m", "pip", "install", "-q",
          "-r", "requirements.txt", "-r", "requirements-dev.txt"])

    print(">> Pulling models into Ollama (skip if you use the OpenAI backend)...")
    _run(["ollama", "pull", model], optional=True)
    _run(["ollama", "pull", embed], optional=True)

    print(">> Running tests...")
    _run([sys.executable, "-m", "pytest", "-q"])

    print()
    print(">> See a real 100-message run:  docs/EXAMPLE_RUN.md")
    print(">> Start the server + web UI:    make run   (then open http://127.0.0.1:8000/)")

    if _ask("Try a quick 10-message scenario now? [y/N]: ").lower().startswith("y"):
        _run([sys.executable, "tools/run_scenario.py", "--character", "megumin",
              "--length", "10", "--memory", "--model", model])
    return 0


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "help"
    if command == "help":
        return show_help()
    if command == "start":
        return start()
    print(f"unknown command {command!r}; expected 'help' or 'start'", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
