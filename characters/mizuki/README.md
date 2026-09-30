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

## ⚠ Warning

**If her attachment reaches 0.5 and you do not wipe the session data between tries,
there will be irreversible consequences.**

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
  what makes her shout. At first she cannot bring herself to kill anything, not even a
  chicken — the same window. Blocks at `following` (0.15), building at `useful` (0.30).
  She never takes food from him.
- **She cannot gather.** Farming is free — crops, breeding, cooking — but a log or a stone
  comes off only with an iron tool in her hand. That is the world's rule, not a stage:
  the router holds it (`hands-rule.js`, server rule `dig_with: iron`).

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

**Watcher** — Forge 1.20.1, Create 6 and **Create: Gunsmithing** (revolvers on NTGL),
about 120 mods on the server. Hardcore for both: a death is the end of that world.

- **Ammunition is the clock.** A revolver round cannot be made by hand: it is a sequenced
  assembly on brass, and brass needs a heated mixer. **Create: Netherless** makes the heat
  an engineering problem rather than a Nether trip — blaze rods come off a line from coal
  and lava, soul sand is made by hand, the blaze burner is crafted. Paper cartridges for
  the flintlock are hand-craftable; the flintlock itself needs an iron plate from a press.
- **The start.** He has **Last Gaze** — a named revolver — with 32 rounds, a wrench,
  engineer's goggles and an empty atlas: enough to reach a blaze burner, not enough to be
  careless. She has a school lunch: onigiri, sushi, a cheeseburger, mochi, peach tea.
- **The quest book (FTB Quests)** is two lines. His, «Инженер», six chapters from her
  appearance to a working shell line and a second gun; every early quest pays 4 rounds,
  chapter 0 ends with an iron backpack and crafting and smelting upgrades, chapter 1
  with a mechanical mixer. Hers, «Мидзуки», is food and comfort: a garden of onion,
  cabbage, tomato and wheat, a sandwich that is not insects, onigiri «as at home», hot food
  by her own hands, surviving alone, and receiving Last Gaze and ten kills of her own.
  Her quests count what she really did; KubeJS checks them.
- **The world is poor in food.** Dungeon chests hold materials; the mods' monster food is
  cut to at most one roll, so people here really do kill for bread.
- **No advancements.** The only progress the game announces is the quest book.

The server build lives outside this repository (`.local/pack-watcher/build.py`), because
the mods are not ours to redistribute.
