from tools.play import DeferredWake, Gifts, _with_gifts


def test_fast_completion_survives_speech_pause_and_is_delivered_once():
    queue = DeferredWake()
    queue.defer({'kind': 'closed', 'attempt': 'first'})
    assert queue.take(110, heard_at=100, woke_at=100, fled_at=0) is None
    queue.defer({'kind': 'closed', 'attempt': 'second'})
    assert queue.take(144, heard_at=100, woke_at=100, fled_at=0) is None
    assert queue.take(145, heard_at=100, woke_at=100, fled_at=0)['attempt'] == 'second'
    assert queue.take(146, heard_at=100, woke_at=100, fled_at=0) is None


def test_deferred_work_waits_for_frequency_and_danger_then_can_be_cleared():
    queue = DeferredWake()
    queue.defer({'kind': 'waiting'})
    assert queue.take(118, heard_at=0, woke_at=100, fled_at=100) is None
    assert queue.take(120, heard_at=0, woke_at=100, fled_at=100) == {'kind': 'waiting'}
    queue.defer({'kind': 'closed'})
    queue.clear()
    assert queue.take(200, heard_at=0, woke_at=0, fled_at=0) is None
    queue.defer({'kind': 'noticed'})
    assert queue.pending is None


def test_event_heartbeat_reaches_deferred_queue_without_changing_default_gift_stream():
    assert list(_with_gifts([None], Gifts(), clock=lambda: 100)) == []
    assert list(_with_gifts([None], Gifts(), clock=lambda: 100, keep_ticks=True)) == [None]
