import copy

import pytest

from flake.harness import versions

G = "taco-council"


def test_create_clamps_exposure_and_records_a_note(db):
    policy = copy.deepcopy(versions.V1_POLICY)
    policy["guardrails"]["max_nonrefundable_exposure_usd"] = 999
    vid = versions.create(G, policy, "greedy", None)
    doc = versions.get(vid)
    assert doc["policy"]["guardrails"]["max_nonrefundable_exposure_usd"] == 300
    assert any("max_nonrefundable_exposure_usd" in n for n in doc["constitution_notes"])


def test_create_leaves_the_v1_constant_untouched(db):
    before = copy.deepcopy(versions.V1_POLICY)
    versions.create(G, versions.V1_POLICY, "seed", None, created_by="seed", status="active")
    assert versions.V1_POLICY == before


def seeded_v1_and_v2(status="canary"):
    v1 = versions.create(G, versions.V1_POLICY, "seed", None, created_by="seed", status="active")
    v2 = versions.create(G, versions.V1_POLICY, "retro", None, status=status)
    return v1, v2


def statuses():
    return {v["_id"]: v["status"] for v in versions.history(G)}


def test_create_numbers_versions_and_points_parent_at_active(db):
    v1, v2 = seeded_v1_and_v2()
    assert (v1, v2) == (f"{G}:v1", f"{G}:v2")
    assert versions.get(v2)["parent"] == v1


def test_promote_leaves_exactly_one_active(db):
    v1, v2 = seeded_v1_and_v2()
    versions.promote(v2)
    assert statuses() == {v1: "superseded", v2: "active"}


def test_rollback_restores_the_parent(db):
    v1, v2 = seeded_v1_and_v2()
    versions.promote(v2)
    assert versions.rollback(G) == v1
    assert statuses() == {v1: "active", v2: "rolled_back"}


def test_rollback_on_v1_errors_and_changes_nothing(db):
    v1 = versions.create(G, versions.V1_POLICY, "seed", None, created_by="seed", status="active")
    with pytest.raises(ValueError, match="nothing to roll back"):
        versions.rollback(G)
    assert statuses() == {v1: "active"}


def test_get_effective_prefers_the_canary(db):
    v1, v2 = seeded_v1_and_v2()
    assert versions.get_effective(G)["_id"] == v2


def test_diff_lists_only_changed_keys(db):
    v1 = versions.create(G, versions.V1_POLICY, "seed", None, created_by="seed", status="active")
    changed = copy.deepcopy(versions.V1_POLICY)
    changed["guardrails"]["max_auto_spend_usd"] = 50
    v2 = versions.create(G, changed, "retro", None)
    assert versions.diff(v1, v2) == ["guardrails.max_auto_spend_usd: 0 -> 50"]
