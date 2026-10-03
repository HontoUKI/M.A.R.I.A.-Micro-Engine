"""Reference lifetime and the one-hop engine boundary."""
import json

import pytest

from engine.character import CharacterRuntime
from engine.glossary import GlossaryNotes
from tests._packs import make_pack


def test_cells_expire_refresh_evict_and_never_store_index():
    notes = GlossaryNotes()
    for name in ('Teach', 'Keys', 'Things'):
        notes.begin_turn()
        notes.remember({'name': name, 'text': name})
    notes.begin_turn()
    notes.remember({'name': 'teach', 'text': 'refreshed'})
    notes.begin_turn()
    notes.remember({'name': 'Places', 'text': 'place'})
    assert set(notes.cells) == {'teach', 'things', 'places'}
    notes.remember({'name': 'Glossary', 'index': True, 'text': 'index'})
    assert len(notes.cells) == 3
    for _ in range(9):
        notes.begin_turn()
    assert set(notes.cells) == {'places'}
    assert 'gone in 1' in notes.render()
    notes.begin_turn()
    assert notes.render() == ''
    assert GlossaryNotes().cells == {}


@pytest.mark.parametrize('threat', [False, True])
def test_lookup_only_once_discards_first_action_and_hides_tags(threat):
    class Hands:
        calls = []

        def history(self):
            return []

        def sight(self):
            return {'defending': 'zombie'} if threat else {}

        def offer(self):
            return {'game': 'Minecraft', 'glossary': True, 'affordances': [{'verb': 'gather'}]}

        def glossary(self, name):
            self.calls.append(name)
            return {'name': 'Teach', 'text': 'Reference body'}

    class Model:
        voices = []

        def chat(self, messages, *, fmt=None, **kwargs):
            if fmt:
                return json.dumps({'tag': 'neutral'})
            self.voices.append(messages)
            if len(self.voices) == 1:
                if threat:
                    return 'Hold position.<LOOKUP>Teach</LOOKUP>'
                return '<LOOKUP>Teach</LOOKUP><play>gather(stone)</play>'
            return 'Done.<lookup>Keys</lookup>'

    hands, model, notes = Hands(), Model(), GlossaryNotes()
    runtime = CharacterRuntime(make_pack(), model, hands=hands, glossary_notes=notes)
    executed = []
    runtime._reach_for_the_game = lambda text: (executed.append(text) or text, ())
    result = runtime.respond('Read the reference')
    expected = 'Hold position.' if threat else 'Done.'
    assert result.reply == expected
    assert executed == [expected]
    assert len(model.voices) == (1 if threat else 2)
    assert len(hands.calls) == (0 if threat else 1)
    assert bool(notes.cells) is not threat
    if not threat:
        assert 'Read the reference' in model.voices[1][-1]['content']
        assert 'Reference body' in model.voices[1][-1]['content']


def test_routine_index_and_action_history_reach_the_compact_world():
    from engine.hands import describe

    routines = [{'name': f'routine_{i}', 'details': f'Purpose {i}'} for i in range(26)]
    text = describe({'game': 'Minecraft', 'glossary': True, 'affordances': [{'verb': 'activate'}]},
                    {'routines': routines}, 'Recent actions: #a activate — reached')
    for routine in routines:
        assert routine['name'] in text
    assert 'Recent actions: #a activate — reached' in text
    assert 'History of completed calls' not in text
