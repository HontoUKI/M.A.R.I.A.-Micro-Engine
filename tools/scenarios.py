"""Scripted user-message scenarios for end-to-end character runs.

Each scenario is a list of user turns. `{name}` is substituted with the run's
user name. The turns deliberately probe:

- name recall (introduced at the start, asked again later),
- fact memory (a black cat named Pixel; a breakfast idea),
- simple help/hints (a virtual pet should be able to offer small suggestions),
- warmth and one teasing turn (to exercise positive and negative tags),
- staying in character.
"""
from __future__ import annotations

_S10 = [
    "Hi! I'm {name}, nice to meet you.",
    "Honestly, you're pretty amazing.",
    "I have a little black cat named Pixel who keeps stealing my pens.",
    "Quick question - what's an easy breakfast I could make tomorrow?",
    "You're a bit of a show-off, you know that?",
    "Still, I'm really glad I get to talk with you.",
    "Do you remember what my cat is called?",
    "And do you remember my name?",
    "Give me one simple tip to wake up less groggy?",
    "This was lovely. Talk soon!",
]

_S20 = [
    "Hey there, I'm {name}.",
    "I've heard a lot about you, and you really live up to it.",
    "I work late a lot; my black cat Pixel keeps me company.",
    "What's a good five-minute snack when I'm coding at night?",
    "You can be a little dramatic, huh?",
    "Sorry, didn't mean to poke fun - you're great, really.",
    "What do you actually enjoy doing?",
    "That's so you. I love it.",
    "Remind me, what's my cat's name?",
    "Do you remember my name too?",
    "I'm trying to read more this year; any simple tip to keep the habit?",
    "You always know what to say.",
    "If you had a free afternoon, what would you do?",
    "Ha, of course you'd say that.",
    "Honestly, talking to you is the best part of my day.",
    "Tell me one small thing to do when I feel stressed.",
    "Thank you, I'll try that.",
    "What was that snack you suggested earlier?",
    "You've been really kind to me today.",
    "Goodnight, see you tomorrow.",
]

_S30 = [
    "Hi! I'm {name}, nice to finally talk to you.",
    "You've got quite the reputation, and you live up to it.",
    "I've got a black cat named Pixel; he's asleep on my keyboard right now.",
    "What's a quick breakfast idea for tomorrow?",
    "You're a bit of a show-off, aren't you?",
    "Kidding! I actually really like that about you.",
    "So what do you love doing most?",
    "That is so on brand for you.",
    "I've been tired lately; any simple tip to sleep better?",
    "Thanks, I'll give that a try tonight.",
    "You're easy to talk to, you know?",
    "What's my cat's name again, do you remember?",
    "And do you remember my name?",
    "You remembered! That makes me happy.",
    "If you could go anywhere, where would you go?",
    "I'd love to come along, honestly.",
    "Can you suggest one small habit to be more productive?",
    "You always give good advice.",
    "I trust you more than most people, weirdly.",
    "What's something that always cheers you up?",
    "I'll remember that for when you're down.",
    "Earlier you mentioned breakfast - what was it again?",
    "You've really grown on me.",
    "Tell me a simple way to stay focused while working?",
    "Perfect, thank you.",
    "Pixel just knocked over my coffee, classic him.",
    "Do you still remember his name?",
    "Talking with you is the highlight of my day.",
    "One last thing, any encouragement before I go?",
    "Thank you, truly. Goodnight!",
]

SCENARIOS: dict[int, list[str]] = {10: _S10, 20: _S20, 30: _S30}
