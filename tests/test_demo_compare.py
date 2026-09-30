from flake.demo.compare import compare_policies
from flake.harness import versions
from flake.risk import pricing

RISK = {
    "sam":    {"flake": {"n": 5, "k": 4, "p_mean": 0.643, "p_upper90": 0.857}, "pay_late": {"n": 1, "k": 1, "p_mean": 0.5, "p_upper90": 0.844}},
    "priya":  {"flake": {"n": 5, "k": 0, "p_mean": 0.071, "p_upper90": 0.19}, "pay_late": {"n": 5, "k": 0, "p_mean": 0.071, "p_upper90": 0.19}},
    "jordan": {"flake": {"n": 5, "k": 0, "p_mean": 0.071, "p_upper90": 0.19}, "pay_late": {"n": 5, "k": 5, "p_mean": 0.786, "p_upper90": 0.957}},
    "maya":   {"flake": {"n": 5, "k": 2, "p_mean": 0.357, "p_upper90": 0.6}, "pay_late": {"n": 3, "k": 0, "p_mean": 0.1, "p_upper90": 0.27}},
}


def make_versions():
    proposal = pricing.propose_rules(RISK, [], versions.V1_POLICY)
    v1 = {"_id": "taco-council:v1", "version": 1, "status": "superseded", "parent": None, "policy": versions.V1_POLICY,
          "rationale": "initial probation policy", "backtest": None, "constitution_notes": [], "canary": None}
    policy = versions.apply_proposal(versions.V1_POLICY, proposal, proposal["rules"])
    v2 = {"_id": "taco-council:v2", "version": 2, "status": "active", "parent": v1["_id"], "policy": policy,
          "rationale": proposal["rationale"], "backtest": {"delta_usd": 217.5}, "constitution_notes": [], "canary": None}
    return v1, v2


def test_rules_permissions_guardrails_and_context_are_grouped():
    v1, v2 = make_versions()
    c = compare_policies(v1, v2)
    assert (c["from"]["id"], c["to"]["id"]) == ("taco-council:v1", "taco-council:v2")
    assert [(r["type"], r["people"]) for r in c["rules"]["added"]] == [
        ("book_refundable_for", ["maya", "sam"]), ("require_deposit_from", ["jordan"]), ("auto_collect_from", ["maya", "priya"])]
    assert c["rules"]["removed"] == [] and c["rules"]["kept"] == []
    perms = {r["key"]: r for r in c["permissions"]}
    assert perms["book.non_refundable"]["from"] == "ask" and perms["book.non_refundable"]["to"] == "auto"
    assert perms["request_money.auto_for"]["to"] == ["maya", "priya"] and perms["request_money.auto_for"]["changed"]
    assert perms["send_message"]["changed"] is False
    guard = {r["key"]: r for r in c["guardrails"]}
    assert (guard["max_nonrefundable_exposure_usd"]["from"], guard["max_nonrefundable_exposure_usd"]["to"]) == (0, 150)
    assert (guard["max_auto_spend_usd"]["from"], guard["max_auto_spend_usd"]["to"]) == (0, 60)
    assert all(not r["changed"] for r in c["context"])          # similar_plans_k stays 3
    assert c["rationale"] == v2["rationale"] and c["backtest"]["delta_usd"] == 217.5


def test_diff_lines_match_the_cli_format():
    v1, v2 = make_versions()
    lines = compare_policies(v1, v2)["diff"]
    assert "guardrails.max_auto_spend_usd: 0 -> 60" in lines
    assert "tool_permissions.book.non_refundable: ask -> auto" in lines
    assert not any(line.startswith("rules") and "->" not in line for line in lines)
