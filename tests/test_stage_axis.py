"""На какой оси читаются ступени и ворота тегов.

Ступень — климат, и климат не должен меняться от одного плохого вечера. Живьём 09.09
четыре грубости уронили близость 0.935 → 0.797: на лестнице, висящей на близости, это
угрожает развернуть НАЗАД сам характер, а не испортить настроение. Злиться на человека и
не мочь его отпустить — разные числа, и вторым может быть только `bond`.

Поле необязательное и по умолчанию сохраняет прежнее поведение: пак, написанный до него,
не должен заметить, что оно появилось.
"""
from __future__ import annotations

from engine.state import Axes, standing_ratio
from tests._packs import make_pack

LADDER = [
    {"id": "wary", "up_to": 0.05, "block": "Поодаль."},
    {"id": "helping", "up_to": 0.15, "block": "Помогает."},
    {"id": "attached", "up_to": 0.30, "block": "Зависит."},
    {"id": "keeping", "up_to": 0.50, "block": "Держит."},
    {"id": "sabotage", "up_to": 0.75, "block": "Мешает тихо."},
    {"id": "obsessed", "up_to": 1.00, "block": "Не отпускает."},
]


def test_the_default_is_what_every_pack_before_this_field_assumed():
    pack = make_pack()
    assert pack.stage_axis == "closeness"


def test_closeness_answers_how_she_is_right_now():
    axes = Axes(affection=90.0, trust=70.0, bond=5.0)
    assert standing_ratio(axes, 100.0) == 0.8
    assert standing_ratio(axes, 100.0, "closeness") == 0.8


def test_bond_answers_what_they_are_to_her_at_all():
    axes = Axes(affection=90.0, trust=70.0, bond=5.0)
    assert standing_ratio(axes, 100.0, "bond") == 0.05


def test_a_bad_evening_does_not_unwind_a_bond_ladder():
    """Утверждение, ради которого поле и заведено.

    Одни и те же четыре грубости: на близости они сбрасывают её ступенью вниз, на связи —
    не двигают лестницу вовсе. Проверяется обеими осями сразу, потому что «не
    развернулось» ничего не значит без «а на другой оси развернулось бы».
    """
    pack = make_pack(stages=LADDER)
    before = Axes(affection=93.5, trust=93.5, bond=60.0)   # близость 0.935, связь 0.60
    after = Axes(affection=61.5, trust=65.5, bond=58.4)    # четыре оскорбления −8/−7/−0.4

    from engine.state import resolve_stage
    close_before = resolve_stage(standing_ratio(before, 100.0, "closeness"), pack.stages)
    close_after = resolve_stage(standing_ratio(after, 100.0, "closeness"), pack.stages)
    bond_before = resolve_stage(standing_ratio(before, 100.0, "bond"), pack.stages)
    bond_after = resolve_stage(standing_ratio(after, 100.0, "bond"), pack.stages)

    assert close_before.id == "obsessed"
    assert close_after.id == "sabotage", "на близости характер откатывается ступенью вниз"
    assert bond_before.id == bond_after.id == "sabotage", "на связи лестница не двигается"


def test_the_ladder_still_falls_when_the_bond_itself_is_spent():
    """Односторонняя — не значит неподвижная.

    Убийство её собственной рукой того, кто был другим, стоит связи. Иначе лестница была
    бы не медленной, а необратимой, и цена перестала бы существовать.
    """
    pack = make_pack(stages=LADDER)
    from engine.state import resolve_stage
    high = Axes(affection=50.0, trust=50.0, bond=51.0)
    spent = Axes(affection=50.0, trust=50.0, bond=49.0)
    assert resolve_stage(standing_ratio(high, 100.0, "bond"), pack.stages).id == "sabotage"
    assert resolve_stage(standing_ratio(spent, 100.0, "bond"), pack.stages).id == "keeping"


def test_tag_windows_read_the_same_axis_as_the_stages():
    """Иначе «она стала другой» и «ей стало доступно другое» происходят в разные моменты.

    Проверяется через рантайм, а не через арифметику: разъехаться они могут только там.
    """
    import json

    from engine.character import CharacterRuntime

    class _Says:
        def __init__(self, tag):
            self._tag = tag

        def chat(self, messages, *, model=None, fmt=None, options=None):
            return json.dumps({"tag": self._tag}) if fmt is not None else "..."

    pack = make_pack(
        stage_axis="bond",
        stages=LADDER,
        tags=[
            {"id": "warmth", "description": "Тепло.", "sentiment": "positive"},
            {"id": "hostility", "description": "Грубость.", "sentiment": "negative"},
            {"id": "neutral", "description": "Обычное.", "sentiment": "neutral"},
            # Доступна только на верхней половине лестницы.
            {"id": "possessive", "description": "Ревность.", "sentiment": "negative",
             "unlock_at": 0.5},
        ],
        deltas={
            "warmth": {"affection": 5.0, "trust": 3.0, "bond": 0.5},
            "hostility": {"affection": -6.0, "trust": -4.0, "bond": -0.2},
            "neutral": {"affection": 0.0, "trust": 0.0, "bond": 0.0},
            "possessive": {"affection": -1.0, "trust": -1.0, "bond": 0.0},
        },
        blocks={"warmth": "a", "hostility": "b", "neutral": "", "possessive": "c"},
    )

    from engine.state import StateKernel

    # Близость высокая, связь низкая: ворота обязаны быть ЗАКРЫТЫ, хотя настроение отличное.
    warm_stranger = StateKernel(pack.axes, values={"affection": 95.0, "trust": 95.0, "bond": 5.0})
    got = CharacterRuntime(pack, _Says("possessive"), state=warm_stranger).respond("кто это был")
    assert got.tag == pack.meta.fallback_tag

    # И наоборот: связь высокая, настроение испорчено — ворота открыты.
    bonded = StateKernel(pack.axes, values={"affection": 20.0, "trust": 10.0, "bond": 80.0})
    got = CharacterRuntime(pack, _Says("possessive"), state=bonded).respond("кто это был")
    assert got.tag == "possessive"
