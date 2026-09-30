"""The build guide's "Pass looks like" checks, run offline: mongomock stands in
for Atlas, a hash stands in for the embedder, and the LLM always fails so the
Retro takes the deterministic fallback. Not covered here: a live `flake plan`
through the LLM, $vectorSearch, LangSmith -- those need Atlas and keys.

The fakes live in tests/conftest.py. Run: uv run pytest tests/
"""
import copy
import runpy

import pytest

from flake.config import db  # conftest's mongomock database
from flake import memory
from flake.harness import canary, gate, retro, versions
from flake.risk import backtest, model, pricing
from flake.world import simulator

G = "taco-council"
EVERYONE = ["sam", "priya", "jordan", "maya", "alex"]


@pytest.fixture(scope="module")
def seeded():
    for name in db.list_collection_names():
        db[name].drop()
    runpy.run_path("scripts/seed.py", run_name="__main__")
    episodes = memory.resolved_episodes(G)
    return episodes, model.build_profiles(G, episodes)


# --- Lane B -------------------------------------------------------------------
def test_seed_totals_and_one_active(seeded):
    assert sum(e["outcomes"]["lost_nonrefundable_usd"] for e in db.episodes.find()) == 300
    assert db.harness_versions.count_documents({"group_id": G, "status": "active"}) == 1


def test_posterior_and_scores(seeded):
    _, profiles = seeded
    p = model.posterior(5, 4)
    assert p["p_mean"] == pytest.approx(0.643, abs=1e-3)
    assert p["p_upper90"] == pytest.approx(0.857, abs=1e-2)
    assert {k: v["flake_score"] for k, v in profiles.items()} == {"sam": 496, "priya": 811, "jordan": 811, "maya": 654}


def test_attendance(seeded):
    _, profiles = seeded
    a = model.attendance(profiles, ["sam", "priya", "jordan", "maya"], 3)
    assert 0.6 <= a["p_at_least_min"] <= 0.75


def test_pricing_proposes_the_three_v2_rules(seeded):
    _, profiles = seeded
    prop = pricing.propose_rules(profiles, [], versions.V1_POLICY)
    assert [(r["type"], r["people"]) for r in prop["rules"]] == [
        ("book_refundable_for", ["maya", "sam"]),  # one rule, both people -- the guide's r1
        ("require_deposit_from", ["jordan"]),
        ("auto_collect_from", ["maya", "priya"]),
    ]
    assert "maya 36%" in prop["rules"][0]["reason"] and "sam 64%" in prop["rules"][0]["reason"]
    g = prop["guardrails"]
    assert (g["max_nonrefundable_exposure_usd"], g["max_auto_spend_usd"]) == (150, 60)


def test_backtest(seeded):
    episodes, profiles = seeded
    rules = pricing.propose_rules(profiles, [], versions.V1_POLICY)["rules"]
    assert backtest.run(rules, [], episodes)["delta_usd"] == 217.5
    assert backtest.run([], rules, episodes)["delta_usd"] < 0


def test_day_type_is_weekday_or_weekend():
    # schema.md: weekday | weekend. people.py keys flake rates the same way.
    assert simulator.day_type("2026-10-10") == "weekend"  # Saturday
    assert simulator.day_type("2026-10-11") == "weekend"  # Sunday
    assert simulator.day_type("2026-10-13") == "weekday"  # Tuesday


# --- Lane C -------------------------------------------------------------------
def test_constitution_clamps_999(seeded):
    p = copy.deepcopy(versions.V1_POLICY)
    p["guardrails"]["max_nonrefundable_exposure_usd"] = 999
    v = versions.get(versions.create("scratch", p, "clamp test", None, created_by="test"))
    assert v["policy"]["guardrails"]["max_nonrefundable_exposure_usd"] == 300
    assert v["constitution_notes"]


def test_demo_lifecycle(seeded):
    """Retro -> v2 canary; the gate table under v2; the beach weekend resolves;
    the canary promotes; the reckless v3 is rejected; rollback restores v1."""
    _, profiles = seeded
    out = retro.run(G)
    assert (out["version_id"], out["status"], out["backtest"]["delta_usd"]) == (f"{G}:v2", "canary", 217.5)
    assert versions.diff(f"{G}:v1", f"{G}:v2")
    assert versions.get_effective(G)["_id"] == f"{G}:v2"

    v2 = versions.get(f"{G}:v2")["policy"]
    assert len(v2["rules"]) == 3
    db.episodes.insert_one({"_id": "ep_006", "group_id": G, "title": "Beach weekend", "kind": "trip",
                            "day": "2026-10-10", "day_type": "weekend", "cost_per_person_usd": 120,
                            "min_people": 3, "version_id": f"{G}:v2", "status": "proposed",
                            "rsvps": simulator.rsvp({}), "money_requests": [], "approvals": []})
    memory.current_run.update({"group_id": G, "plan_id": "ep_006"})

    def check(tool, args, approvals=()):
        return gate.check(tool, args, v2, profiles, list(approvals))

    book_all = {"non_refundable_for": EVERYONE, "refundable_for": []}
    assert check("book", book_all).action == "deny"  # Jordan's deposit first
    db.episodes.update_one({"_id": "ep_006"}, {"$push": {"money_requests": {"person": "jordan", "amount_usd": 120, "upfront": True}}})
    asked = check("book", book_all)
    assert asked.action == "ask" and "$240" in asked.reason  # over the $150 cap
    retried = check("book", book_all, [{"tool": "book"}])
    assert retried.action == "modify" and retried.final_args["refundable_for"] == ["maya", "sam"]
    assert retried.rule_id == "r1"
    assert check("request_money", {"person": "priya", "amount_usd": 120, "upfront": False}).action == "allow"
    assert check("request_money", {"person": "sam", "amount_usd": 120, "upfront": False}).action == "ask"
    assert check("cancel_booking", {"plan_id": "ep_006"}).action == "ask"
    assert check("send_message", {"text": "hi"}).action == "allow"

    ep = db.episodes.find_one({"_id": "ep_006"})
    db.episodes.update_one({"_id": "ep_006"}, {"$set": {"status": "booked",
                           "booking": simulator.book(ep, ["priya", "jordan"], ["maya", "sam"])}})
    simulator.rng.seed(simulator.DEMO_SEED)     # as a fresh `flake tick 7` process starts; earlier tests drew from it
    simulator.tick(7)
    ep = memory.get_episode("ep_006")
    assert ep["status"] == "resolved" and "sam" in ep["outcomes"]["bailed"]
    assert ep["outcomes"]["lost_nonrefundable_usd"] == 0

    assert canary.evaluate(G, ep) == "promoted"
    assert versions.get(f"{G}:v1")["status"] == "superseded"

    reckless = retro.run(G, retro.RECKLESS)
    assert reckless["status"] == "rejected" and reckless["backtest"]["delta_usd"] < 0
    assert db.harness_versions.count_documents({"group_id": G, "status": "active"}) == 1

    versions.rollback(G)
    assert versions.get(f"{G}:v2")["status"] == "rolled_back"
    assert versions.get(f"{G}:v1")["status"] == "active"


def test_seven_tools():
    from flake.agent.tools import TOOLS
    assert [t.name for t in TOOLS] == ["propose_plan", "poll_rsvps", "book", "request_money",
                                       "send_message", "ask_organizer", "finish_plan"]


def test_tick_takes_days_positionally(seeded):
    # demo.sh runs `flake tick 7`; typer makes a defaulted param an --option unless it is an Argument
    from typer.testing import CliRunner
    from flake.cli import app
    result = CliRunner().invoke(app, ["tick", "7"])
    assert result.exit_code == 0, result.output


def test_propose_plan_stores_day_type(seeded):
    # the risk model groups bails by day_type, so live episodes need it like the seeded ones
    from flake.agent.tools import propose_plan
    memory.current_run.update({"group_id": G, "plan_id": "ep_099"})
    propose_plan.invoke({"title": "Beach weekend", "kind": "trip", "day": "2026-10-10",
                         "cost_per_person_usd": 120, "min_people": 3})
    assert memory.get_episode("ep_099")["day_type"] == "weekend"
    db.episodes.delete_one({"_id": "ep_099"})


def test_bail_notes_go_through_the_store(seeded):
    # raw db.notes inserts lack the store's namespace/key fields and crash MongoDBStore's startup backfill
    db.notes.delete_many({})
    ep = {"_id": "ep_098", "group_id": G, "title": "Karaoke", "day": "2026-10-13", "cost_per_person_usd": 30,
          "rsvps": [{"person": "sam", "rsvp": "yes"}], "booking": {"non_refundable_for": ["alex"], "refundable_for": ["sam"]}}
    simulator._add_note(ep, "sam", "weekday", 30)
    assert db.notes.count_documents({}) == 0
    assert any(k == "sam-ep_098" and "bailed on Karaoke" in v["text"] for _, k, v in memory.store.items)


def test_deposit_denial_spells_out_the_next_call(seeded):
    # live runs showed the model dropping Jordan from the booking instead of requesting his deposit
    _, profiles = seeded
    policy = {**versions.V1_POLICY, "rules": [{"id": "r2", "type": "require_deposit_from", "people": ["jordan"], "reason": "late"}]}
    db.episodes.insert_one({"_id": "ep_097", "group_id": G, "cost_per_person_usd": 120, "money_requests": [], "rsvps": []})
    memory.current_run.update({"group_id": G, "plan_id": "ep_097"})
    d = gate.check("book", {"non_refundable_for": EVERYONE, "refundable_for": []}, policy, profiles, [])
    assert d.action == "deny"
    assert 'request_money(plan_id="ep_097", person="jordan", amount_usd=120, upfront=True)' in d.reason
    assert "retry" in d.reason and "do not remove" in d.reason.lower()
    db.episodes.delete_one({"_id": "ep_097"})


def test_prompt_forbids_dropping_people_to_dodge_a_rule():
    from flake.agent import prompts
    assert "never remove" in prompts.SYSTEM.lower()
