import pytest

from flake import memory
from flake.harness import gate

# flake probabilities from the seeded risk table (Sam 0.64, Priya/Jordan 0.07, Maya 0.36)
RISK = {p: {"flake": {"p_mean": m}} for p, m in
        {"sam": 0.64, "priya": 0.07, "jordan": 0.07, "maya": 0.36}.items()}


def policy(**guardrails):
    return {
        "rules": [],
        "guardrails": {"max_nonrefundable_exposure_usd": 300, "max_auto_spend_usd": 300,
                       "min_expected_attendance_ratio": 0.0, "min_confidence": 0.0, **guardrails},
        "tool_permissions": {
            "send_message": "auto",
            "book": {"refundable": "auto", "non_refundable": "auto"},
            "request_money": {"default": "ask", "auto_for": ["priya"]},
        },
    }


@pytest.fixture
def episode(monkeypatch):
    # the gate reads the plan from Mongo; hand it an in-memory one instead
    ep = {"_id": "ep_t", "cost_per_person_usd": 25, "min_people": 3, "money_requests": [],
          "rsvps": [{"person": p, "rsvp": "yes"} for p in ("sam", "priya", "jordan", "maya")]}
    monkeypatch.setitem(memory.current_run, "plan_id", "ep_t")
    monkeypatch.setattr(memory, "get_episode", lambda _id: ep)
    return ep


BOOK = {"non_refundable_for": ["priya", "jordan"], "refundable_for": ["sam", "maya"]}


def test_send_message_is_allowed(episode):
    assert gate.check("send_message", {"text": "hi"}, policy(), RISK).action == "allow"


def test_request_money_auto_for_listed_person_ask_otherwise(episode):
    assert gate.check("request_money", {"person": "priya"}, policy(), RISK).action == "allow"
    assert gate.check("request_money", {"person": "sam"}, policy(), RISK).action == "ask"


def test_refundable_rule_moves_people_and_modifies(episode):
    p = policy()
    p["rules"] = [{"id": "r1", "type": "book_refundable_for", "people": ["sam", "maya"]}]
    args = {"non_refundable_for": ["sam", "priya", "maya"], "refundable_for": []}
    d = gate.check("book", args, p, RISK)
    assert d.action == "modify" and d.rule_id == "r1"
    assert d.final_args["non_refundable_for"] == ["priya"]
    assert d.final_args["refundable_for"] == ["maya", "sam"]
    assert args["non_refundable_for"] == ["sam", "priya", "maya"]  # model's own args untouched


def test_missing_deposit_denies_booking(episode):
    p = policy()
    p["rules"] = [{"id": "r2", "type": "require_deposit_from", "people": ["jordan"]}]
    d = gate.check("book", BOOK, p, RISK)
    assert d.action == "deny" and "jordan" in d.reason


def test_exposure_over_cap_asks_then_approval_allows(episode):
    p = policy(max_nonrefundable_exposure_usd=40)
    assert gate.check("book", BOOK, p, RISK).action == "ask"
    assert gate.check("book", BOOK, p, RISK, [{"tool": "book"}]).action == "allow"


def test_low_expected_attendance_ratio_asks(episode):
    # expected show-ups 2.86 of 4 yes = 71%
    d = gate.check("book", BOOK, policy(min_expected_attendance_ratio=0.8), RISK)
    assert d.action == "ask" and "expected attendance" in d.reason


def test_attendance_ratio_at_or_above_floor_allows(episode):
    assert gate.check("book", BOOK, policy(min_expected_attendance_ratio=0.6), RISK).action == "allow"


def test_ratio_ignored_when_nobody_is_non_refundable(episode):
    args = {"non_refundable_for": [], "refundable_for": ["sam", "priya", "jordan", "maya"]}
    assert gate.check("book", args, policy(min_expected_attendance_ratio=0.95), RISK).action == "allow"
