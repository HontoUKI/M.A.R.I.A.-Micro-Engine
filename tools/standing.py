"""Где персонаж стоит с человеком — и, если надо, поставить его туда.

Лестница на связи растёт часами: полный цикл Юкины это около шести часов непрерывной
игры. Проверять верхние ступени, наиграв до них, нельзя — это не проверка, а вторая
съёмка. Поэтому здесь есть посев: поставить связь на нужную ступень и посмотреть, какая
она там.

    python tools/standing.py --character yukina                  # где стоит
    python tools/standing.py --character yukina --stage sabotage # поставить на ступень
    python tools/standing.py --character yukina --bond 40        # или прямо числом
    python tools/standing.py --character yukina --reset          # обратно в начало

Ключ разговора по умолчанию тот же, что у игры (`minecraft:<имя>`), потому что проверять
надо ту ведомость, которая живёт, а не соседнюю: 09.09 ход уехал в разговор с самой собой,
и −8 доверия за убийство не достались никому.

Посев — инструмент проверки, а не игры. Он пишет прямо в состояние, минуя ход, поэтому в
расшифровке следа не оставляет: досье считается по прожитым ходам и врать о них не должно.
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
    parser.add_argument("--character", required=True, help="имя пака, например yukina")
    parser.add_argument("--who", default="HontoUKI", help="с кем; по умолчанию HontoUKI")
    parser.add_argument("--key", default="", help="ключ разговора целиком, если он не игровой")
    parser.add_argument("--stage", default="", help="поставить на эту ступень")
    parser.add_argument("--bond", type=float, default=None, help="поставить связь числом")
    parser.add_argument("--reset", action="store_true", help="вернуть к началу пака")
    args = parser.parse_args()

    service = get_service()
    if not service.has_model(args.character):
        known = ", ".join(sorted(service.model_names()))
        print(f"нет персонажа {args.character!r}; есть {known}")
        return 1

    pack = service.registry.get(args.character)
    key = args.key or f"minecraft:{args.who}"
    axis_max = service.axis_max

    if args.reset:
        service.sessions.reset_state(key, pack)
        print(f"{key}: состояние сброшено к началу пака")

    kernel = service.sessions.kernel_for(key, pack)

    want = args.bond
    if args.stage:
        named = [s for s in pack.stages if s.id == args.stage]
        if not named:
            print(f"нет ступени {args.stage!r}; есть {', '.join(s.id for s in pack.stages)}")
            return 1
        # Середина ступени, а не её край: на самом пороге границы включительны с обеих
        # сторон, и проверять там значит проверять край, а не ступень.
        under = [s.up_to for s in pack.stages if s.up_to < named[0].up_to]
        low = max(under) if under else 0.0
        want = (low + named[0].up_to) / 2 * axis_max

    if want is not None:
        if pack.stage_axis != "bond":
            print(f"⚠ пак читает ступени по {pack.stage_axis!r}, а сеется связь —"
                  " посев ничего не изменит")
        axes = kernel.axes.as_dict()
        axes["bond"] = max(0.0, min(axis_max, want))
        # Тем же способом, каким состояние восстанавливают при возврате к разговору:
        # свой способ положить числа рано или поздно разойдётся с настоящим.
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
    where_now = stage.id if stage else "(ступеней нет)"
    print(f"  ось ступеней: {pack.stage_axis} -> доля {ratio:.3f} -> {where_now}")
    print(f"  для справки, по {other}: {standing_ratio(axes, axis_max, other):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
