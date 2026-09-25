# Mizuki — sample character pack

A schoolgirl who fell out of our world into a dead Minecraft one, and the last engineer
left in it — who pointed his revolver at her the moment he saw her. She is useless in a
fight. She is also the only other person left who talks.

An original character written for this engine, shipped under CC-BY-4.0.

## Сюжет

> Ты — один из последних инженерных гениев этого мира, полного опасностей. Привык работать
> один, никому не доверять и никогда не стоять на месте.
>
> Внезапно перед тобой появилась девушка в странной одежде. Вооружённый револьвером и
> последней горсткой патронов, ты направил на неё ствол. Девушка в шоке забилась в угол.
>
> Ты впервые видишь такого, как ты, — «человека», а не местных жителей. Цивилизация давно
> пала от вируса.
>
> Что в бою, что по силе новая спутница совершенно бесполезна и становится балластом. Но
> если она умрёт, ты, возможно, потеряешь последний шанс поговорить с кем-то, кто говорит,
> а не издаёт пресловутое короткое гнусавое «хмм».
>
> Успех зависит от одного: как быстро ты наладишь массовое производство патронов — и не
> умрёшь от голода.

## What it demonstrates

Yukina is the mirror: she cannot die and you can. **Mizuki can die, once, and the story
ends with her.** The pack is built so that everything about her stays true in numbers
rather than in prose:

- **She starts below neutral.** Trust 0, affection 5 — the only sample pack that opens
  under zero-ish, because the first thing he did was aim a gun at her.
- **Protecting her is the biggest thing he can do**, feeding her the second. A gift of
  things comes after both: she does not need a diamond, she needs to see tomorrow.
- **Pointing the gun again costs more than protecting her returns**, and is remembered
  for 300 turns.
- **What the world does to her moves nothing.** Gunfire, being hunted, hunger: the stage
  decides how she takes it. The same shot makes her cover her ears at `shock` and look for
  the target at `following`.
- **No combat routines at the start.** `fight` and `strike` open only at `partner` (0.50).
  Her stance in danger is to run, hide and call for help from the first hit: the router's
  `flee` posture (server rule `posture: flee`) runs her to him, and the note it sends is
  what makes her shout. Her hands open with the stages: a pickaxe and blocks at
  `following` (0.15), building at `useful` (0.30). She never takes food from him.

| stage | up to | she is |
|---|---|---|
| `shock` | 0.05 | still in the corner; one-word answers |
| `ballast` | 0.15 | follows because alone she would die |
| `following` | 0.30 | knows what is dangerous; asks about him |
| `useful` | 0.50 | food is hers; tells him about home |
| `partner` | 0.75 | not afraid of the gunfire; argues when he goes alone |
| `home` | 1.00 | would not go home without him |

`tests/test_mizuki_pack.py` pins each of these.

## The world she is written for

Forge 1.20.1 with Create 6 and **Create: Gunsmithing**. The design depends on one fact read
from the mod's own recipes: a revolver round cannot be made by hand at all. It is a
sequenced assembly on brass, and brass needs a heated mixer — a blaze burner, so a trip to
the Nether. Paper cartridges for the flintlock are hand-craftable, but the flintlock
itself needs an iron plate, which only a press makes. Starting with a revolver and twelve
rounds therefore means starting with a clock.
