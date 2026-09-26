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
PROMPT = """You are the underwriter for a group-plans agent. Propose the next policy version.
    You may only use these rule types: book_refundable_for, require_deposit_from, auto_collect_from, avoid_day_type, max_plan_cost_usd.
    Loosen only where the 90% upper bound of the risk is below the threshold and there are at least 3 observations. Tighten wherever a loss happened.
    Floors you cannot exceed: {floors}

    Current policy: {policy}
    Risk table: {risk}
    Plans that lost money: {losses}
    Deterministic suggestion from the pricing model: {suggestion}
"""
def propose(policy: dict, risk: dict, losses: list[dict], floors: dict) -> PolicyProposal:
    suggestion = pricing.propose_rules(risk, losses, policy)
    try:
        structured = llm.with_structured_output(PolicyProposal)
        return structured.invoke(PROMPT.format(floors=floors, policy=policy, risk=risk, losses=losses, suggestion=suggestion))
    except Exception:
        return PolicyProposal(**suggestion)      # the deterministic proposal already has this shape