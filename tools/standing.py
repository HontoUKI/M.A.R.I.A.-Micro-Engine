"""Where a character stands with a person — and, if needed, put her there.

The bond ladder grows over hours: Yukina's full cycle is about six hours of continuous play.
Checking the upper stages by playing up to them is impossible — that is not a check but a
second take. So there is seeding here: put the bond at the wanted stage and see what she is
like there.

    python tools/standing.py --character yukina                  # where she stands
    python tools/standing.py --character yukina --stage sabotage # put her on a stage
    python tools/standing.py --character yukina --bond 40        # or directly by number
    python tools/standing.py --character yukina --reset          # back to the start

The conversation key defaults to the game's (`minecraft:<name>`), because the ledger that
must be checked is the one that lives, not the one next to it: on 09.09 a turn went into a
conversation with herself, and the −8 trust for a killing went to nobody.

Seeding is a tool for checking, not for playing. It writes straight into the state, bypassing
the turn, so it leaves no trace in the transcript: the dossier counts lived turns and must not lie
about them.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.deps import get_service  # noqa: E402
from engine.io.json_store import save_json_atomic  # noqa: E402
from engine.state import StateKernel, resolve_stage, standing_ratio  # noqa: E402


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", required=True, help="the pack's name, e.g. yukina")
    parser.add_argument("--who", default="HontoUKI", help="with whom; HontoUKI by default")
    parser.add_argument(
        "--key", default="", help="the full conversation key, if it is not the game's"
    )
    parser.add_argument("--stage", default="", help="put her on this stage")
    parser.add_argument("--bond", type=float, default=None, help="set the bond by number")
    parser.add_argument("--reset", action="store_true", help="back to the pack's start")
    args = parser.parse_args()

    service = get_service()
    if not service.has_model(args.character):
        known = ", ".join(sorted(service.model_names()))
        print(f"no character {args.character!r}; there are {known}")
        return 1

    pack = service.registry.get(args.character)
    key = args.key or f"minecraft:{args.who}"
    axis_max = service.axis_max

    if args.reset:
        service.sessions.reset_state(key, pack)
        print(f"{key}: state reset to the pack's start")

    kernel = service.sessions.kernel_for(key, pack)

    want = args.bond
    if args.stage:
        named = [s for s in pack.stages if s.id == args.stage]
        if not named:
            print(f"no stage {args.stage!r}; there are {', '.join(s.id for s in pack.stages)}")
            return 1
        # The middle of a stage, not its edge: on the threshold itself the bounds are inclusive on
        # both sides, and checking there means checking the edge, not the stage.
        under = [s.up_to for s in pack.stages if s.up_to < named[0].up_to]
        low = max(under) if under else 0.0
        want = (low + named[0].up_to) / 2 * axis_max

    if want is not None:
        if pack.stage_axis != "bond":
            print(f"⚠ the pack reads stages by {pack.stage_axis!r}, but the bond is seeded —"
                  " seeding will change nothing")
        axes = kernel.axes.as_dict()
        axes["bond"] = max(0.0, min(axis_max, want))
        # The same way the state is restored when returning to a conversation: a method of
        # one's own for laying the numbers down will sooner or later diverge from the real one.
        kernel = StateKernel.restore(pack, axes, axis_max=axis_max)
        service.sessions._kernels[(key, pack.meta.name)] = kernel
        where = service.sessions._dir(key, pack)
        os.makedirs(where, exist_ok=True)
        save_json_atomic(os.path.join(where, "state.json"), kernel.to_dict())

    axes = kernel.axes
    ratio = standing_ratio(axes, axis_max, pack.stage_axis)
    stage = resolve_stage(ratio, pack.stages)
    other = "closeness" if pack.stage_axis == "bond" else "bond"

    print(f"{key} · {pack.meta.display_name}")
    print(f"  affection {axes.affection:6.1f} · trust {axes.trust:6.1f} · bond {axes.bond:6.1f}")
    where_now = stage.id if stage else "(no stages)"
    print(f"  stage axis: {pack.stage_axis} -> share {ratio:.3f} -> {where_now}")
    print(f"  for reference, by {other}: {standing_ratio(axes, axis_max, other):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
