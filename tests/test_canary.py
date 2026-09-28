import copy

from flake.harness import canary, versions

G = "taco-council"
PROFILES = [{"group_id": G, "person": p, "flake": {"p_mean": m}}
            for p, m in {"sam": 0.64, "priya": 0.07, "jordan": 0.07, "maya": 0.36}.items()]


def setup_canary(db):
    db.risk_profiles.insert_many(copy.deepcopy(PROFILES))
    v1 = versions.create(G, versions.V1_POLICY, "seed", None, created_by="seed", status="active")
    v2 = versions.create(G, versions.V1_POLICY, "retro", None, status="canary")
    return v1, v2


def episode(version_id, realized):
    return {"_id": "ep_t", "version_id": version_id, "cost_per_person_usd": 120,
            "rsvps": [{"person": p, "rsvp": "yes"} for p in ("sam", "priya", "jordan", "maya")],
            "outcomes": {"total_cost_usd": realized}}


def status(vid):
    return versions.get(vid)["status"]


def test_ignores_a_plan_that_did_not_run_under_the_canary(db):
    v1, v2 = setup_canary(db)
    assert canary.evaluate(G, episode(v1, 0)) is None
    assert status(v2) == "canary"


def test_promotes_when_cheaper_than_expected(db):
    v1, v2 = setup_canary(db)
    # v1 has no rules, so expected = (0.64 + 0.07 + 0.07 + 0.36) * 120 = 136.8
    assert canary.evaluate(G, episode(v2, 36)) == "promoted"
    assert (status(v1), status(v2)) == ("superseded", "active")
    assert versions.get(v2)["canary"]["expected_cost_usd"] == 136.8


def test_rolls_back_when_costlier_than_expected(db):
    v1, v2 = setup_canary(db)
    assert canary.evaluate(G, episode(v2, 500)) == "rolled_back"
    assert (status(v1), status(v2)) == ("active", "rolled_back")


def test_missing_risk_profile_is_treated_as_maximally_risky_not_a_crash(db):
    # maya RSVP'd yes but has no risk_profiles doc yet (e.g. added to the group since the
    # last Retro's build_profiles ran) -- must not KeyError and crash the tick beat
    db.risk_profiles.insert_many(copy.deepcopy([p for p in PROFILES if p["person"] != "maya"]))
    v1 = versions.create(G, versions.V1_POLICY, "seed", None, created_by="seed", status="active")
    v2 = versions.create(G, versions.V1_POLICY, "retro", None, status="canary")
    # expected = (0.64 + 0.07 + 0.07 + 1.0 [maya, missing profile]) * 120 = 213.6
    assert canary.evaluate(G, episode(v2, 100)) == "promoted"
    assert versions.get(v2)["canary"]["expected_cost_usd"] == 213.6

    profiles = {d["person"]: d for d in db.risk_profiles.find({"group_id": G})}
    breakdown = canary.expected_cost_breakdown(versions.get(v1)["policy"], episode(v2, 100), profiles)
    maya_line = next(line for line in breakdown if line["person"] == "maya")
    assert maya_line["rate"] == 1.0
    assert maya_line["profile_missing"] is True
