"""End-to-end scenario runner against a real Ollama model.

Drives a scripted conversation through a character pack and prints, per turn,
the chosen tag, the relationship stage, the axis movement, any recalled memory,
and the reply — then a summary. State can be seeded to test a character at a
specific point in the relationship.

Examples:
    python tools/run_scenario.py --character megumin --length 10
    python tools/run_scenario.py --character both --length all --memory
    python tools/run_scenario.py --character kaguya --length 20 \
        --affection 80 --trust 70 --bond 40
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# Model replies can contain characters outside the console's legacy code page
# (e.g. cp1251 on Windows); force UTF-8 so printing never crashes a run.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scenarios import SCENARIOS  # noqa: E402  (tools/ is on sys.path[0])

from engine.character import CharacterRuntime  # noqa: E402
from engine.llm import OllamaClient  # noqa: E402
from engine.memory import VectorStore  # noqa: E402
from engine.pack import load_pack  # noqa: E402
from engine.prompt_manager import DialogueTurn  # noqa: E402
from engine.state import (  # noqa: E402
    DEFAULT_AXIS_MAX,
    StateKernel,
    relationship_ratio,
)
from engine.web import DuckDuckGoSearcher  # noqa: E402

_AXES = ("affection", "trust", "bond")


def _seed_values(pack, overrides: dict[str, float | None]) -> dict[str, float]:
    return {
        axis: (overrides[axis] if overrides[axis] is not None else getattr(pack.axes, axis).start)
        for axis in _AXES
    }


def run_one(character: str, length, args) -> None:
    pack = load_pack(str(_ROOT / "characters" / character))
    llm = OllamaClient(
        args.ollama_url,
        args.model,
        args.embed_model,
        temperature=args.temperature,
    )
    values = _seed_values(pack, {a: getattr(args, a) for a in _AXES})
    kernel = StateKernel(pack.axes, axis_max=DEFAULT_AXIS_MAX, values=values)

    memory = VectorStore(tempfile.mkdtemp(prefix="scenario_mem_")) if args.memory else None
    searcher = DuckDuckGoSearcher() if args.web_search else None
    runtime = CharacterRuntime(
        pack,
        llm,
        state=kernel,
        memory=memory,
        embed_model=args.embed_model,
        non_rp=args.non_rp,
        non_romance=args.non_romance,
        web_search=searcher,
    )

    start = dict(values)
    print("=" * 78)
    print(
        f"{pack.meta.display_name}  |  length={length}  |  model={args.model}"
        f"  |  memory={'on' if memory else 'off'}  |  non_rp={args.non_rp}"
        f"  |  non_romance={args.non_romance}"
    )
    print("seed axes: " + "  ".join(f"{a}={values[a]:g}" for a in _AXES))
    print("=" * 78)

    # A per-character variant (e.g. "showcase-kaguya") wins over the generic key.
    scenario = SCENARIOS.get(f"{length}-{character}", SCENARIOS[length])

    history: list[tuple[str, str]] = []
    stages: list[str] = []
    for i, template in enumerate(scenario, 1):
        user = template.format(name=args.name)
        window = tuple(DialogueTurn(r, c) for r, c in history)
        result = runtime.respond(user, window)

        axes = result.axes
        ratio = relationship_ratio(axes, DEFAULT_AXIS_MAX)
        stage = result.stage or "-"
        if not stages or stages[-1] != stage:
            stages.append(stage)

        star = " *" if result.stage_changed else ""
        print(f"\n[{i:02d}] YOU   : {user}")
        print(
            f"     STATE : tag={result.tag}  stage={stage}{star}  "
            f"(aff {axes.affection:g}, tru {axes.trust:g}, bond {axes.bond:g}, "
            f"ratio {ratio:.2f})"
        )
        print(f"     REPLY : {result.reply.strip()}")
        history.append(("user", user))
        history.append(("assistant", result.reply))
        sys.stdout.flush()

    usage = llm.usage_snapshot()
    end = kernel.to_dict()
    print("\n" + "-" * 78)
    print(
        "SUMMARY  axes "
        + " ".join(f"{a}:{start[a]:g}->{end[a]:g}" for a in _AXES)
    )
    print("         stages: " + " -> ".join(stages))
    print(
        f"         tokens: prompt={usage['prompt_tokens']} "
        f"completion={usage['completion_tokens']} total={usage['total_tokens']} "
        f"(calls={usage['calls']})"
    )
    print("-" * 78 + "\n")
    sys.stdout.flush()


def main() -> None:
    p = argparse.ArgumentParser(description="Run an e2e character scenario.")
    p.add_argument("--character", default="both", help="megumin | kaguya | both")
    p.add_argument("--length", default="all", help="10 | 20 | 30 | coding | boundary | all")
    p.add_argument("--name", default="Alex", help="user name used in the script")
    p.add_argument("--model", default="gemma3:4b")
    p.add_argument("--embed-model", default="nomic-embed-text")
    p.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    p.add_argument("--temperature", type=float, default=0.8)
    p.add_argument("--memory", action="store_true", help="enable vector memory")
    p.add_argument("--non-rp", action="store_true", help="forbid roleplay action narration")
    p.add_argument(
        "--non-romance", action="store_true", help="keep the relationship strictly platonic"
    )
    p.add_argument("--web-search", action="store_true", help="enable opt-in web lookup")
    p.add_argument("--affection", type=float, default=None)
    p.add_argument("--trust", type=float, default=None)
    p.add_argument("--bond", type=float, default=None)
    args = p.parse_args()

    characters = ["megumin", "kaguya"] if args.character == "both" else [args.character]
    if args.length == "all":
        lengths: list = [10, 20, 30]
    elif args.length in ("coding", "boundary", "showcase"):
        lengths = [args.length]
    else:
        lengths = [int(args.length)]

    for character in characters:
        for length in lengths:
            run_one(character, length, args)


if __name__ == "__main__":
    main()
