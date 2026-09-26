"""Structured PolicyProposal output, with a deterministic fallback -- owned by Lane A."""


def propose(incumbent_policy: dict, profiles: dict, losses: list[dict], floors: dict):
    raise NotImplementedError("Lane A: LLM structured output -> PolicyProposal, falls back to risk.pricing.propose_rules")
