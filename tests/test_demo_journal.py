from flake.demo.journal import Journal


def test_seq_is_monotonic_and_since_replays_only_newer_events():
    j = Journal()
    a = j.append("a", "ok", summary="first")
    b = j.append("b", "ok", summary="second")
    assert (a.seq, b.seq) == (1, 2) and j.cursor() == 2
    assert [e.kind for e in j.since(0)] == ["a", "b"]
    assert [e.kind for e in j.since(1)] == ["b"]
    assert j.since(2) == []


def test_a_cursor_from_another_session_replays_everything():
    j = Journal()
    j.append("a")
    assert [e.kind for e in j.since(99)] == ["a"]   # stale cursor from before a reset


def test_reset_starts_a_new_session_and_sequence():
    j = Journal()
    j.append("old")
    before = j.session
    after = j.reset()
    assert after != before and j.all() == [] and j.cursor() == 0
    assert j.append("new").seq == 1 and j.all()[0].session == after


def test_events_carry_the_row_fields():
    j = Journal()
    e = j.append("gate.decision", "warn", beat=1, beat_id="taco", operation="plan", node="gate",
                 summary="Gate ASK", details={"tool": "book"}, plan_id="ep_006", version_id="taco-council:v1")
    d = e.to_dict()
    assert d["node"] == "gate" and d["details"] == {"tool": "book"} and d["plan_id"] == "ep_006"
    assert d["session"] == j.session and d["ts"].endswith("+00:00")
