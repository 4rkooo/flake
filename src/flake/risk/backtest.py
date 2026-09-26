"""Replay candidate vs incumbent rules over past plans -- owned by Lane B."""


def run(proposed_rules: list[dict], incumbent_rules: list[dict], episodes: list[dict]) -> dict:
    raise NotImplementedError("Lane B: {accepted, rejected, baseline_usd, proposed_usd, delta_usd}")


def refundable_people(rules: list[dict]) -> list[str]:
    raise NotImplementedError("Lane B: people covered by a book_refundable_for rule")
