from typing import Literal
from pydantic import BaseModel, Field
from flake.config import llm
from flake.risk import pricing

RuleType = Literal["book_refundable_for", "require_deposit_from", "auto_collect_from", "avoid_day_type", "max_plan_cost_usd"]

class Rule(BaseModel):
    type: RuleType
    people: list[str] = []
    day_type: str | None = None
    amount: int | None = None
    reason: str = Field(description="one sentence citing the numbers that justify the rule")
class Guardrails(BaseModel):
    max_nonrefundable_exposure_usd: int
    max_auto_spend_usd: int
    min_expected_attendance_ratio: float
    min_confidence: float

class PolicyProposal(BaseModel):
    rules: list[Rule]
    guardrails: Guardrails
    auto_book_nonrefundable: bool = Field(description="may book non-refundable without asking when the attendance forecast passes")
    similar_plans_k: int = 3
    rationale: str = Field(description="three sentences a friend would understand")
class Wording(BaseModel):
    """All the LLM may write: the pricing model has already decided rules and caps."""
    rationale: str = Field(description="three sentences a friend would understand")
    reasons: list[str] = Field(description="one sentence per rule, same order, citing the numbers that justify it")

PROMPT = """You are the underwriter for a group-plans agent. The pricing model has already decided the next policy.
Your only job is to explain it: a three-sentence rationale a friend would understand, and one reason per rule,
in the same order, quoting the numbers that justify it. Do not add, drop or change any rule or number.

Rules decided:
{rules}
Guardrails decided: {guardrails}
Risk table (bail chance and late-payment chance, with 90% upper bounds and plan counts):
{risk}
Plans that lost money:
{losses}
"""

def _risk_lines(risk: dict) -> str:
    # numbers only -- no ids or timestamps, so the same history gives the same prompt and the cache replays it
    return "\n".join(
        f"{p}: bails {r['flake']['p_mean']:.0%} (upper {r['flake']['p_upper90']:.0%}, {r['flake']['n']} plans), "
        f"pays late {r['pay_late']['p_mean']:.0%} (upper {r['pay_late']['p_upper90']:.0%}, {r['pay_late']['n']} plans)"
        for p, r in sorted(risk.items()))

def _loss_lines(losses: list[dict]) -> str:
    return "\n".join(
        f"{e['title']} ({e.get('day_type', '?')}, ${e['cost_per_person_usd']} each): bailed {', '.join(e['outcomes']['bailed']) or 'nobody'}, "
        f"cost ${e['outcomes']['total_cost_usd']}" for e in losses) or "none"

def propose(policy: dict, risk: dict, losses: list[dict], floors: dict) -> PolicyProposal:
    # math decides, the LLM only words it: rules and caps always come from pricing,
    # so a model answer can't add rules or push the caps up to the constitution's floors
    decided = pricing.propose_rules(risk, losses, policy)
    try:
        # function_calling: the answer is cached as plain tool-call data. The default (json_schema)
        # attaches a parsed pydantic object the cache can't load back, so every run was a miss
        words = llm.with_structured_output(Wording, method="function_calling").invoke(PROMPT.format(
            rules="\n".join(f"{i + 1}. {r['type']} {', '.join(r['people'])}" for i, r in enumerate(decided["rules"])),
            guardrails=decided["guardrails"], risk=_risk_lines(risk), losses=_loss_lines(losses)))
        decided = {**decided, "rationale": words.rationale}
        if len(words.reasons) == len(decided["rules"]):   # a miscounted answer keeps pricing's own reasons
            decided["rules"] = [{**r, "reason": why} for r, why in zip(decided["rules"], words.reasons)]
    except Exception:
        pass                                              # network off: pricing's own wording
    return PolicyProposal(**decided)
