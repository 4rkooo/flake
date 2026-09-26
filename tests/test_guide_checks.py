"""The build guide's "Pass looks like" checks, run offline: mongomock stands in
for Atlas, a hash stands in for the embedder, and the LLM always fails so the
Retro takes the deterministic fallback. Not covered here: a live `flake plan`
through the LLM, $vectorSearch, LangSmith -- those need Atlas and keys.

Run: uv run pytest tests/test_guide_checks.py
"""
import copy
import hashlib
import runpy
import sys
import types

import mongomock
import pytest

# --- fakes, installed before anything imports flake.config -------------------
cfg = types.ModuleType("flake.config")
cfg.db = mongomock.MongoClient()["flake"]
cfg.embed = lambda text: [b / 255 for b in hashlib.sha256(text.encode()).digest()] * 48  # 1536 dims


class _NoLLM:  # "network off": underwriter_llm.propose must fall back to pricing
    def with_structured_output(self, *_a, **_k):
        raise RuntimeError("network off")

    def bind_tools(self, *_a, **_k):
        return self


cfg.llm, cfg.embedder, cfg.DEMO_SEED, cfg.LLM_CACHE_PATH = _NoLLM(), None, 42, None
sys.modules["flake.config"] = cfg


class _Store:  # memory.py opens a LangGraph Mongo store at import
    def __init__(self):
        self.items = []

    def __enter__(self):
        return self

    def put(self, ns, key, value, **_):
        self.items.append((ns, key, value))

    def search(self, ns, query=None, limit=10, **_):
        return [types.SimpleNamespace(key=k, value=v) for n, k, v in self.items if n == ns][:limit]


store_mod = types.ModuleType("langgraph.store.mongodb")
store_mod.MongoDBStore = types.SimpleNamespace(from_conn_string=lambda *a, **k: _Store())
store_mod.create_vector_index_config = lambda **k: None
sys.modules["langgraph.store.mongodb"] = store_mod

import os  # noqa: E402

os.environ.setdefault("MONGODB_URI", "mongodb://fake")

from flake import memory  # noqa: E402
from flake.harness import canary, gate, retro, versions  # noqa: E402
from flake.risk import backtest, model, pricing  # noqa: E402
from flake.world import simulator  # noqa: E402

db = cfg.db
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
