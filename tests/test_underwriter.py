from flake.agent import underwriter_llm
from flake.risk import pricing

# the seeded risk numbers that matter to pricing (see risk_profiles in schema.md)
RISK = {
    "sam":    {"flake": {"n": 5, "k": 4, "p_mean": 0.643, "p_upper90": 0.857}, "pay_late": {"n": 1, "k": 1, "p_mean": 0.5, "p_upper90": 0.844}},
    "priya":  {"flake": {"n": 5, "k": 0, "p_mean": 0.071, "p_upper90": 0.19}, "pay_late": {"n": 5, "k": 0, "p_mean": 0.071, "p_upper90": 0.19}},
    "jordan": {"flake": {"n": 5, "k": 0, "p_mean": 0.071, "p_upper90": 0.19}, "pay_late": {"n": 5, "k": 5, "p_mean": 0.786, "p_upper90": 0.957}},
    "maya":   {"flake": {"n": 5, "k": 2, "p_mean": 0.357, "p_upper90": 0.6}, "pay_late": {"n": 3, "k": 0, "p_mean": 0.1, "p_upper90": 0.27}},
}
LOSSES = [{"title": "Ski trip", "day_type": "weekend", "cost_per_person_usd": 150,
           "outcomes": {"bailed": ["sam"], "total_cost_usd": 150}, "updated_at": "2026-09-26T13:39:00Z"}]


class _Wordsmith:
    """A stand-in LLM: records the prompt and fills whatever wording schema it is given."""
    def __init__(self, n_rules=0):
        self.prompts, self.n_rules = [], n_rules

    def with_structured_output(self, schema, **_):
        self.schema = schema
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.schema(rationale="Sam bails a lot, so we insure his share.",
                           reasons=[f"reason {i}" for i in range(self.n_rules)])


def test_llm_only_words_the_pricing_decision(monkeypatch):
    decided = pricing.propose_rules(RISK, LOSSES, {})
    fake = _Wordsmith(n_rules=len(decided["rules"]))
    monkeypatch.setattr(underwriter_llm, "llm", fake)

    out = underwriter_llm.propose({}, RISK, LOSSES, {}).model_dump()

    assert [(r["type"], r["people"]) for r in out["rules"]] == [(r["type"], r["people"]) for r in decided["rules"]]
    assert out["guardrails"] == decided["guardrails"]
    assert out["auto_book_nonrefundable"] == decided["auto_book_nonrefundable"]
    assert out["rationale"] == "Sam bails a lot, so we insure his share."
    assert [r["reason"] for r in out["rules"]] == [f"reason {i}" for i in range(len(decided["rules"]))]


def test_prompt_has_no_timestamps_so_the_cache_can_replay(monkeypatch):
    fake = _Wordsmith()
    monkeypatch.setattr(underwriter_llm, "llm", fake)
    underwriter_llm.propose({}, RISK, LOSSES, {})
    assert "2026-09-26" not in fake.prompts[0] and "updated_at" not in fake.prompts[0]


def test_network_off_returns_the_pricing_proposal():
    # conftest's LLM always raises
    decided = pricing.propose_rules(RISK, LOSSES, {})
    out = underwriter_llm.propose({}, RISK, LOSSES, {}).model_dump()
    assert [(r["type"], r["people"], r["reason"]) for r in out["rules"]] == \
           [(r["type"], r["people"], r["reason"]) for r in decided["rules"]]
    assert out["rationale"] == decided["rationale"]
