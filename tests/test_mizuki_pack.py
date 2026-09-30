"""Мидзуки: балласт, который нельзя потерять.

Пак держится на трёх утверждениях канона (`direction/MIZUKI_CONCEPT.md`), и все три —
числа и код, а не проза:

1. Она начинает НИЖЕ нейтрального: доверие к человеку, наставившему на неё ствол, ноль.
2. Самое большое, что он может сделать, — защитить её, а не одарить.
3. Боевых рутин у неё нет до ступени партнёра; стойка при опасности — бегство (роутер).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.pack import load_pack
from engine.perception import TagClassifier, _available_tags

_MIZUKI = Path(__file__).resolve().parents[1] / "characters" / "mizuki"

FOLLOWING = 0.15   # кирка и блоки в руках
USEFUL = 0.30      # страх, что он уйдёт один; стройка
PARTNER = 0.50     # «ты для меня важна»


@pytest.fixture
def pack():
    return load_pack(str(_MIZUKI))


class _Insists:
    """Модель, которая называет один и тот же тег, что бы ей ни предложили."""

    def __init__(self, tag: str) -> None:
        self._tag = tag

    def chat(self, messages, *, model=None, fmt=None, options=None):
        return json.dumps({"tag": self._tag})


def test_she_starts_below_neutral_because_he_pointed_a_gun(pack):
    assert pack.axes.trust.start == 0
    assert pack.axes.affection.start < 10


def test_protecting_her_is_the_biggest_thing_he_can_do(pack):
    """Ей не нужен алмаз — ей нужно дожить до завтра."""
    protected = pack.deltas["protected"]
    for tag, delta in pack.deltas.items():
        if tag != "protected":
            assert protected.trust >= delta.trust, tag
    assert protected.affection > pack.deltas["gift"].affection
    assert pack.deltas["fed"].affection > pack.deltas["gift"].affection


def test_pointing_the_gun_again_costs_more_than_protecting_her_returns(pack):
    threatened, protected = pack.deltas["threatened"], pack.deltas["protected"]
    assert abs(threatened.trust) > protected.trust
    assert pack.remembered_for["threatened"] > pack.remembered_for["protected"]


def test_the_world_happening_to_her_moves_nothing(pack):
    """Выстрел, охота на неё, голод — положение дел, а не его поступок."""
    for tag in ("gunfire", "you_are_hunted", "you_were_hurt", "hungry", "he_is_in_danger"):
        d = pack.deltas[tag]
        assert (d.affection, d.trust, d.bond) == (0.0, 0.0, 0.0), tag


def test_fear_of_losing_him_opens_only_once_she_knows_him(pack):
    early = {t.id for t in _available_tags(pack, ratio=0.05)}
    assert "dont_leave_me" not in early and "closeness" not in early
    assert "dont_leave_me" in {t.id for t in _available_tags(pack, ratio=USEFUL)}
    assert "closeness" in {t.id for t in _available_tags(pack, ratio=PARTNER)}


def test_a_locked_tag_cannot_be_chosen_even_when_the_model_names_it(pack):
    assert TagClassifier(_Insists("closeness")).classify(
        pack, "you matter to me", ratio=0.05
    ) == pack.meta.fallback_tag
    assert TagClassifier(_Insists("closeness")).classify(
        pack, "you matter to me", ratio=0.8
    ) == "closeness"


def test_no_fighting_until_she_is_his_partner(pack):
    """Автор, 25.09: «отсутствие каких-либо боевых рутин в начале»."""
    for verb in ("fight", "strike", "beat"):
        bound = next(b for b in pack.bounds if b.verb == verb)
        assert bound.covers(verb, ("zombie",))
        assert not bound.allows(USEFUL), verb
        assert bound.allows(PARTNER), verb


def test_her_hands_open_with_the_stages(pack):
    build = next(b for b in pack.bounds if b.verb == "build")
    assert not build.allows(FOLLOWING) and build.allows(USEFUL)


def test_digging_is_the_worlds_rule_not_a_stage(pack):
    """Бревно рукой нереально на любой ступени — это держит роутер (`dig_with: iron`)."""
    assert not any(b.verb == "dig" for b in pack.bounds)


def test_she_will_not_kill_even_a_chicken_at_first(pack):
    fight = next(b for b in pack.bounds if b.verb == "fight")
    assert fight.covers("fight", ("chicken",)) and not fight.allows(USEFUL)


def test_she_never_takes_his_food(pack):
    food = next(b for b in pack.bounds if b.verb == "take_from")
    assert food.covers("take_from", ("bread",)) and not food.allows(1.0)
    assert not food.covers("take_from", ("iron_ingot",))


def test_every_stage_has_a_cold_face(pack):
    for stage in pack.stages:
        assert "unkind lately" in stage.block, f"ступень {stage.id} не умеет холодеть"


def test_gunfire_is_read_by_the_stage(pack):
    """Один повод, разные ступени: вздрагивает в начале, спокойна у партнёра."""
    assert "stage note" in pack.blocks["gunfire"]
    by_id = {s.id: s.block for s in pack.stages}
    assert "flinch" in by_id["shock"]
    assert "not afraid of the gunfire" in by_id["partner"]


def test_no_japanese_words_are_invited(pack):
    """Автор, 25.09: «Kowai с самого старта — так себе». Пак не должен звать японские слова."""
    text = " ".join([pack.identity, *pack.blocks.values(), *(s.block for s in pack.stages)]).lower()
    for word in ("kowai", "itadakimasu", "sugoi", "japanese word"):
        assert word not in text, word


def _flat(text):
    return " ".join(str(text).split())


def test_nothing_unseen_is_invited(pack):
    """Живьём 26.09: «шум как на заводе» на дереве в лесу, «торговый автомат» на кровать.

    Блок `progress` подсказывал сравнение с заводом, поездом, автоматом на ЛЮБОЕ достижение,
    включая её собственные; идентичность звала сравнивать с домом всё подряд. Пак не должен
    подсказывать ни одной вещи, которой она не видела.
    """
    text = " ".join([pack.identity, *pack.blocks.values(), *(s.block for s in pack.stages)]).lower()
    for word in ("factory", "vending machine"):
        assert word not in text, word
    assert "compare what you actually see here to home" in _flat(pack.identity)
    # «Ничего не выдумывать» — не её черта, а режим игры: GAMER=true (engine/character.py).
    assert not any("never describe a machine" in i.lower() for i in pack.invariants)


def test_she_does_not_see_advancements(pack):
    """Автор, 27.09: «закрыть ей глаза на достижения — это сюжетное РП».

    Достижение — счёт игры, а не то, что с ней происходит; живьём 26.09 кровать («Sweet
    Dreams») стала у неё «торговым автоматом». Заметка `advanced` до неё не доходит, и тегов,
    которые кормились только ею, в паке нет.
    """
    from tools.play import visible

    assert "advanced" in pack.unseen_notes
    unseen = frozenset(pack.unseen_notes)
    assert not visible({"kind": "advanced", "who": "Mizuki", "what": "Sweet Dreams"}, unseen)
    assert visible({"kind": "given", "who": "HontoUKI"}, unseen), "what he does still reaches her"
    assert not {"progress", "she_did"} & {t.id for t in pack.tags}


def test_home_is_not_one_memory_on_repeat(pack):
    """Живьём 26.09: «поезд в восемь утра» пять раз за утро — пример из блока стал ответом."""
    block = _flat(pack.blocks["asks_about_home"])
    assert "you have not told him yet" in block
    assert "train at eight" not in block


def test_small_talk_has_its_own_tags_and_neglect_is_narrow():
    """30.09: without small-talk tags the classifier filed chatter under story tags —
    short on-topic answers as `neglect` («ты всё равно меня не слушаешь» ×3), mock
    politeness as `attention` answered literally — and «teasing» told her to say «at
    home I would explain», five times in one evening."""
    pack = load_pack(str(_MIZUKI))
    ids = {t.id for t in pack.tags}
    assert {"small_talk", "joke", "sarcasm"} <= ids
    assert "mundane" not in ids
    assert pack.tag("small_talk").sentiment == "neutral", "chatter is not a deed in the dossier"
    assert pack.deltas["small_talk"].trust > 0, "small talk raises trust, slowly"
    assert "joke" in pack.diminishing
    assert "NOT neglect" in pack.tag("neglect").description
    assert "literally" in pack.blocks["sarcasm"]
    assert "home" not in pack.blocks["teasing"].split("Do not bring up home")[0]
