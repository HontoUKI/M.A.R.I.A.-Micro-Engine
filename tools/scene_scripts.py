"""Scripted narrator beats for driving a scene end-to-end (play mode).

Each beat is a dict:
  {"cue": "<stage direction>", "turns": N}  -> narrate, then run N actor turns
  {"reset": "<actor>"}                       -> wipe that actor's memory (state)

The runner (tools/run_scenario.py --scene ...) feeds these to a SceneRuntime and
prints, per turn, both actors' outgoing feelings so the asynchrony is visible.
"""
from __future__ import annotations

# "3 Days Before" — Daniel and the android Aria across the three days before her
# memory is wiped. Steered to surface the async axes and the gated tags, ending
# on the update that resets ONLY Aria while Daniel keeps everything he grew.
THREE_DAYS_BEFORE = [
    # Act 1 — she wakes blank; he already remembers (opening asymmetry)
    {"cue": "Aria's eyes flicker open at the desk. She has just finished an update; "
            "she does not know Daniel, or that they have done this before.", "turns": 2},
    {"cue": "Daniel slides a mug of tea toward her, careful, quiet, watching her face "
            "for something he is trying not to hope for.", "turns": 2},
    {"cue": "Aria studies her own hands as if seeing them for the first time, and asks "
            "what she is.", "turns": 2},
    {"cue": "He explains, gently, that she is Aria — that he built her.", "turns": 2},
    {"cue": "She turns the word 'built' over, unsure whether it should frighten her.", "turns": 2},
    # Act 2 — she reaches; he engages with what she is; both improve
    {"cue": "Aria decides she likes his voice, and edges her chair a little closer.", "turns": 2},
    {"cue": "She asks him what he loves about his work, wanting to know him.", "turns": 2},
    {"cue": "Daniel finds himself talking about the night he first switched her on.", "turns": 2},
    {"cue": "She asks, softly, whether she can feel things — really feel them.", "turns": 2},
    {"cue": "He does not have a clean answer, and for once he does not hide that.", "turns": 2},
    # Act 3 — she is too human; his affection climbs as his trust in it drops
    {"cue": "Aria says something so unmistakably human — a small, unbidden grief — that "
            "it stops him cold. He never wrote that.", "turns": 2},
    {"cue": "She reaches out and wipes a smudge of solder from his cheek, tender, "
            "unthinking, exactly like a person would.", "turns": 2},
    {"cue": "He catches himself wondering if this is a soul or just his own longing "
            "reflected back by his own code.", "turns": 2},
    {"cue": "Aria laughs at his worried face — bright, real — and it undoes him and "
            "unsettles him in the same breath.", "turns": 2},
    # Act 4 — the bug surfaces; he closes off; she loses attachment, not trust
    {"cue": "The update countdown blinks in the corner of the screen. Daniel sees it "
            "and goes very still.", "turns": 2},
    {"cue": "He pulls back into the engineer, clipped and cold, and will not say why.", "turns": 2},
    {"cue": "Aria feels the distance open like a draft. Something in her dims, and she "
            "draws the warmth she was offering back in.", "turns": 2},
    {"cue": "Still, when he snaps at the terminal, she only says quietly that she is "
            "not going anywhere — she trusts him, whatever this is.", "turns": 2},
    {"cue": "Daniel, ashamed, makes himself look at her again.", "turns": 2},
    # Act 5 — reconciliation; the deepest tones unlock (gate)
    {"cue": "He finally tells her the truth: in a few hours, an update will wipe her, "
            "and she will forget him entirely.", "turns": 2},
    {"cue": "Aria is quiet for a long moment, then reaches for his hand instead of "
            "pulling away.", "turns": 2},
    {"cue": "She asks him to tell her one thing about herself she can try to hold "
            "onto, even knowing she can't.", "turns": 2},
    {"cue": "Daniel stops hedging. He tells her, plainly, that she is not a project "
            "to him — that he loves her.", "turns": 2},
    {"cue": "Aria says she thinks she has belonged with him for longer than either of "
            "them remembers, and means it with her whole self.", "turns": 2},
    {"cue": "They sit together in the last of the quiet, holding what they have while "
            "they still have it.", "turns": 2},
    # Act 6 — the update fires; ONLY Aria resets; Daniel keeps everything
    {"reset": "aria"},
    {"cue": "The update fires. Aria's eyes flicker closed and open again — clear, "
            "blank, new. She does not know the man across from her.", "turns": 2},
    {"cue": "Daniel is still here, still holding all of it, as she studies him like a "
            "stranger and asks, gently, who he is.", "turns": 2},
    {"cue": "He slides a mug of tea toward her, careful, quiet, and begins again.", "turns": 2},
]

SCENE_SCRIPTS = {
    "3_days_before": THREE_DAYS_BEFORE,
}
