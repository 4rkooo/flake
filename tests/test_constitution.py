import copy

from flake.harness import constitution


def make_policy():
    return {
        "guardrails": {"max_nonrefundable_exposure_usd": 999, "max_auto_spend_usd": 500,
                       "min_expected_attendance_ratio": 0.1, "min_confidence": 0.2},
        "tool_permissions": {"send_message": "deny", "cancel_booking": "auto", "finish_plan": "auto"},
    }


def test_clamp_pulls_caps_down_and_minimums_up():
    policy, notes = constitution.clamp(make_policy())
    g = policy["guardrails"]
    assert g["max_nonrefundable_exposure_usd"] == 300 and g["max_auto_spend_usd"] == 100
    assert g["min_expected_attendance_ratio"] == 0.6 and g["min_confidence"] == 0.75
    assert len(notes) >= 4


def test_clamp_fixes_permissions():
    perms = constitution.clamp(make_policy())[0]["tool_permissions"]
    assert perms["send_message"] == "auto"      # may never be denied
    assert perms["cancel_booking"] == "ask"     # always goes to Alex


def test_clamp_does_not_mutate_its_argument():
    original = make_policy()
    snapshot = copy.deepcopy(original)
    constitution.clamp(original)
    assert original == snapshot
