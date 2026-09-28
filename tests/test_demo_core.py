"""The blockers found inspecting the demo: an unbooked run must not be marked booked, the
demo must reseed the world per tick inside one process, and a presenter can stand in for Alex."""
import random

import pytest

from flake import memory, observe
from flake.config import db  # conftest's mongomock database
from flake.world import simulator

G = "taco-council"


@pytest.fixture(autouse=True)
def clean_episodes():
    db.episodes.delete_many({"_id": {"$in": ["ep_t1", "ep_t2", "ep_t3"]}})
    yield
    db.episodes.delete_many({"_id": {"$in": ["ep_t1", "ep_t2", "ep_t3"]}})


def _state(plan_id, turns, version="taco-council:v1"):
    return {"plan_id": plan_id, "group_id": G, "turns": turns, "version": {"_id": version},
            "messages": [], "plan_brief": "x", "context": {}}


def test_record_episode_marks_a_booked_plan_booked():
    from flake.agent import graph
    db.episodes.insert_one({"_id": "ep_t1", "group_id": G, "status": "proposed",
                            "booking": {"non_refundable_for": ["alex"], "refundable_for": []}})
    graph.record_episode(_state("ep_t1", 5))
    ep = memory.get_episode("ep_t1")
    assert ep["status"] == "booked" and ep["version_id"] == "taco-council:v1"
    assert ep.get("incomplete_reason") is None


def test_record_episode_reports_a_turn_limited_run_without_booking():
    from flake.agent import graph
    db.episodes.insert_one({"_id": "ep_t2", "group_id": G, "status": "proposed"})
    graph.record_episode(_state("ep_t2", graph.MAX_TURNS))
    ep = memory.get_episode("ep_t2")
    assert ep["status"] == "proposed"           # tick only resolves booked plans; this one stays out
    assert "turn limit" in ep["incomplete_reason"]
    assert ep["version_id"] == "taco-council:v1"


def test_record_episode_undoes_a_finish_without_a_booking():
    from flake.agent import graph
    # finish_plan sets status booked before record_episode runs; without a receipt that is a lie
    db.episodes.insert_one({"_id": "ep_t3", "group_id": G, "status": "booked", "summary": "gave up"})
    graph.record_episode(_state("ep_t3", 4))
    ep = memory.get_episode("ep_t3")
    assert ep["status"] == "proposed" and "without booking" in ep["incomplete_reason"]


def test_tick_keeps_drawing_from_one_stream(monkeypatch):
    # the guide's world: one seeded generator that advances, so repeated ticks in one
    # process (a batch loop, a test) get fresh draws rather than a replay
    import mongomock
    monkeypatch.setattr(simulator, "db", mongomock.MongoClient().flake)   # nothing booked: no draws
    simulator.rng.random()
    before = simulator.rng.getstate()
    simulator.tick(7)
    assert simulator.rng.getstate() == before


def test_the_demo_ticks_from_a_fresh_seed_like_a_cli_run(monkeypatch):
    # a `flake tick` is one process, so it always rolls from DEMO_SEED; the demo server ticks
    # twice in one process and must see the same draws
    from flake.demo.beats import BEATS
    from flake.demo.coordinator import Coordinator
    first_draw = []
    monkeypatch.setattr(simulator, "tick", lambda days: first_draw.append(simulator.rng.random()) or [])
    c = Coordinator()
    try:
        simulator.rng.random()           # disturb the generator, as an earlier tick would
        c._run(next(i for i, b in enumerate(BEATS) if b["operation"] == "tick"))
    finally:
        c.close()
    assert first_draw == [random.Random(simulator.DEMO_SEED).random()]


def test_organizer_is_scripted_yes_unless_the_demo_injects_one():
    assert simulator.organizer_answer("Approve book?") == "yes"
    simulator.set_organizer(lambda q: "no")
    try:
        assert simulator.organizer_answer("Approve book?") == "no"
    finally:
        simulator.set_organizer(None)
    assert simulator.organizer_answer("Approve book?") == "yes"


def test_run_plan_returns_an_incomplete_summary_when_no_episode_was_created(monkeypatch):
    from flake.agent import graph
    monkeypatch.setattr(memory, "next_plan_id", lambda: "ep_t9")
    final = {"version": {"_id": "taco-council:v1"}, "turns": graph.MAX_TURNS, "messages": []}
    monkeypatch.setattr(graph.graph, "invoke", lambda *_a, **_k: final)
    ep = graph.run_plan(G, "nothing happens")
    assert ep["_id"] == "ep_t9" and ep.get("booking") is None
    assert ep["version_id"] == "taco-council:v1" and ep["incomplete_reason"]
