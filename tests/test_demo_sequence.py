"""The whole presentation script, driven through the coordinator with a scripted model and
the real gate, risk, backtest and canary code on the in-memory database."""
import time

import pytest

from flake import memory
from flake.config import db
from flake.demo import fake_llm
from flake.demo.coordinator import Blocked, Coordinator

V1, V2, V3 = "taco-council:v1", "taco-council:v2", "taco-council:v3"


def wait_for(pred, timeout=60, step=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(step)
    return False


@pytest.fixture
def coord(monkeypatch):
    from flake.agent import graph, tools, underwriter_llm

    model = fake_llm.ScriptedChatModel()
    monkeypatch.setattr(graph, "model", model.bind_tools(tools.TOOLS))
    monkeypatch.setattr(underwriter_llm, "llm", model)
    for name in db.list_collection_names():
        db[name].drop()
    memory.store.clear()
    c = Coordinator(reset_index_timeout=0)
    yield c
    c.close()


def run_beat(c, approve=True, timeout=60):
    """Advance one beat, answering every approval as it appears. Returns the approvals answered."""
    c.next_beat()
    answered = []

    def step():
        for ap in c.pending_approvals():
            c.answer_approval(ap["id"], "approve" if approve else "decline")
            answered.append(ap)
        return not c.busy()

    assert wait_for(step, timeout), "beat did not finish"
    assert c.beat_status == "done", (c.beat_status, c.beat_error)
    return answered


def events(c, kind):
    return [e for e in c.journal.all() if e.kind == kind]


def test_the_full_script(coord):
    c = coord
    # 0. reset / baseline
    run_beat(c)
    assert db.episodes.count_documents({"status": "resolved"}) == 5
    assert [v["status"] for v in db.harness_versions.find()] == ["active"]
    assert events(c, "reset.done") and c.state()["beat"] == {"index": 0, "id": "reset", "title": "Reset / baseline",
                                                              "operation": "reset", "status": "done", "error": None, "warning": None}

    # 1. Taco Tuesday under v1: the booking and the first money request need Alex
    approvals = run_beat(c)
    assert [a["tool"] for a in approvals] == ["book", "request_money"]
    ep6 = memory.get_episode("ep_006")
    assert ep6["status"] == "booked" and ep6["version_id"] == V1 and ep6["booking"] and ep6["day_type"] == "weekday"
    decisions = [(e.details["tool"], e.details["decision"]) for e in events(c, "gate.decision")]
    assert ("book", "ask") in decisions and ("book", "allow") in decisions and ("request_money", "ask") in decisions
    assert all(e.version_id == V1 for e in events(c, "gate.decision"))          # every decision cites its policy
    assert all(e.details["cache"] == "scripted" for e in events(c, "llm.turn"))
    similar = events(c, "memory.similar")
    assert similar and similar[0].details["method"] == "recency_fallback" and similar[0].status == "warn"
    assert events(c, "policy.loaded")[0].version_id == V1 and events(c, "approval.resolved")
    assert [e.kind for e in c.journal.all() if e.kind.startswith("beat.")] == ["beat.start", "beat.done", "beat.start", "beat.done"]

    # 2. advance: Sam's scripted bail lands, the lost share is real
    run_beat(c)
    ep6 = memory.get_episode("ep_006")
    assert ep6["status"] == "resolved" and "sam" in ep6["outcomes"]["bailed"] and ep6["outcomes"]["lost_nonrefundable_usd"] == 25
    assert events(c, "sim.resolved")[-1].details["scripted"] == ["sam"] and events(c, "canary.skipped")

    # 3. Retro: v2 goes on trial as a canary
    run_beat(c)
    v2 = db.harness_versions.find_one({"_id": V2})
    types = [r["type"] for r in v2["policy"]["rules"]]
    assert v2["status"] == "canary" and "book_refundable_for" in types and "require_deposit_from" in types
    bt = events(c, "backtest.run")[-1].details
    assert bt["decision"] == "ship" and bt["delta_usd"] > 0 and bt["episodes"] == 6 and len(bt["per_episode"]) == 6
    assert events(c, "proposal.worded") and events(c, "version.created")[-1].details["constitution_notes"] == []
    assert events(c, "risk.profiles")[-1].details["profiles"]["sam"]["flake"]["k"] == 5   # four seeded bails plus Taco Tuesday
    assert [e.details["status"] for e in events(c, "version.status")][-1] == "canary"

    # 4. compare v1 -> v2
    run_beat(c)
    cmp = events(c, "policy.compared")[-1].details["compare"]
    assert (cmp["from"]["id"], cmp["to"]["id"]) == (V1, V2) and len(cmp["rules"]["added"]) >= 2 and cmp["diff"]

    # 5. Beach Weekend under v2: deposit first (deny), the learned rule rewrites the booking (modify), exposure asks
    approvals = run_beat(c)
    assert [a["tool"] for a in approvals] == ["request_money", "book"]
    assert approvals[0]["args"]["person"] == "jordan" and approvals[0]["args"]["upfront"] is True
    ep7 = memory.get_episode("ep_007")
    assert ep7["version_id"] == V2 and ep7["booking"]["refundable_for"] == ["maya", "sam"] and ep7["day_type"] == "weekend"
    d7 = [(e.details["tool"], e.details["decision"], e.details["rule_id"]) for e in events(c, "gate.decision") if e.plan_id == "ep_007"]
    assert ("book", "deny", "r2") in d7 or any(t == "book" and d == "deny" for t, d, _ in d7)
    assert any(t == "book" and d == "modify" and r == "r1" for t, d, r in d7)
    assert any(t == "book" and d == "ask" for t, d, _ in d7)
    assert events(c, "policy.loaded")[-1].version_id == V2 and all(e.version_id == V2 for e in events(c, "gate.decision") if e.plan_id == "ep_007")

    # 6. advance: Sam bails again but was refundable; the canary is promoted
    run_beat(c)
    ev = events(c, "canary.evaluated")[-1].details
    assert ev["result"] == "promoted" and ev["realized_cost_usd"] <= ev["expected_cost_usd"] and len(ev["breakdown"]) == 4
    assert db.harness_versions.find_one({"_id": V2})["status"] == "active"
    assert db.harness_versions.find_one({"_id": V1})["status"] == "superseded"
    assert memory.get_episode("ep_007")["outcomes"]["lost_nonrefundable_usd"] == 0

    # 7. reckless Retro: rejected by the backtest
    run_beat(c)
    assert db.harness_versions.find_one({"_id": V3})["status"] == "rejected"
    assert events(c, "backtest.run")[-1].details["delta_usd"] < 0 and events(c, "retro.done")[-1].details["status"] == "rejected"
    with pytest.raises(Blocked):
        c.next_beat()

    rows = c.journal.all()
    seqs = [e.seq for e in rows]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs) and len({e.session for e in rows}) == 1
    st = c.state()
    assert st["beat"]["index"] == 7 and st["beat"]["status"] == "done" and st["next_available"] is False
    assert [v["status"] for v in st["policy"]["versions"]] == ["superseded", "active", "rejected"]
    assert st["policy"]["active"]["_id"] == V2 and len(st["compares"]) == 2 and len(st["events"]) == len(rows)
    # inspector values come from the persisted documents
    audit_ids = {a["_id"] for a in st["audit"]}
    assert all(e.details["audit_id"] in audit_ids for e in events(c, "gate.decision"))
    assert events(c, "backtest.run")[-1].details["delta_usd"] == st["policy"]["versions"][2]["backtest"]["delta_usd"]


def test_an_approval_holds_the_protected_action_and_duplicates_are_harmless(coord):
    c = coord
    run_beat(c)
    c.next_beat()
    assert wait_for(lambda: c.pending_approvals() or not c.busy(), 30) and c.pending_approvals(), (c.beat_status, c.beat_error)
    ap = c.pending_approvals()[0]
    assert ap["tool"] == "book" and memory.get_episode("ep_006").get("booking") is None      # held at ask_organizer
    # gate.py's decision.reason doubles as ask_organizer's whole question ("Approve <tool>
    # <args>? Reason: <why>"); the approval card must show just the "why", not the full question
    assert ap["reason"] and "Approve" not in ap["reason"] and "? Reason:" not in ap["reason"]
    assert c.state()["next_available"] is False
    with pytest.raises(Exception):
        c.next_beat()                                                                      # other beats stay locked
    first = c.answer_approval(ap["id"], "approve")
    second = c.answer_approval(ap["id"], "decline")                                        # a second click changes nothing
    assert first["status"] == "accepted" and second["status"] == "already_answered" and second["decision"] == "approve"
    with pytest.raises(KeyError):
        c.answer_approval("ap_999", "approve")
    approvals = []
    assert wait_for(lambda: [approvals.extend(c.answer_approval(a["id"], "approve") for a in c.pending_approvals()), not c.busy()][1], 60)
    assert c.beat_status == "done" and memory.get_episode("ep_006")["booking"]


def test_declining_the_booking_ends_the_plan_honestly(coord):
    c = coord
    run_beat(c)
    run_beat(c, approve=False)
    ep6 = memory.get_episode("ep_006")
    assert ep6.get("booking") is None and ep6["status"] == "proposed" and "without booking" in ep6["incomplete_reason"]
    assert c.beat_warning and "without a booking" in c.beat_warning
    assert events(c, "plan.end")[-1].status == "warn"
    run_beat(c)                                   # nothing to resolve, but no crash and no fake outcomes
    assert memory.get_episode("ep_006")["status"] == "proposed" and "nothing" in (c.beat_warning or "")


def test_reset_during_an_approval_stops_the_worker_and_leaves_no_stale_writes(coord):
    c = coord
    run_beat(c)
    c.next_beat()
    assert wait_for(lambda: c.pending_approvals(), 30)
    ap = c.pending_approvals()[0]
    old_session = c.journal.session
    out = c.reset()
    assert out["session"] != old_session
    assert wait_for(lambda: not c.busy(), 60) and c.beat_status == "done" and c.beat_index == 0
    assert db.episodes.count_documents({}) == 5 and memory.get_episode("ep_006") is None
    assert c.pending_approvals() == [] and all(e.session == out["session"] for e in c.journal.all())
    with pytest.raises(KeyError):
        c.answer_approval(ap["id"], "approve")   # the old request was consumed by the reset
    assert [a["tool"] for a in run_beat(c)] == ["book", "request_money"]   # and the script runs cleanly again
    assert memory.get_episode("ep_006")["booking"]


def test_pacing_holds_each_moment_and_yields_to_a_reset(coord, monkeypatch):
    from flake import observe
    from flake.demo import coordinator as mod

    monkeypatch.setitem(mod.PACE, "x.paced", 0.3)
    c = coord
    t = time.time()
    c._record("x.paced")                       # pace 0: no wait
    assert time.time() - t < 0.1
    c.set_pace(1.0)
    t = time.time()
    c._record("x.paced")
    assert time.time() - t >= 0.28             # held on screen
    observe.request_cancel()
    try:
        t = time.time()
        c._record("x.paced")
        assert time.time() - t < 0.15          # a reset does not wait for the pause
    finally:
        observe.clear_cancel()
    with pytest.raises(ValueError):
        c.set_pace(99)
