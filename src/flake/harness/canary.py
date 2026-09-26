"""Judges a canary once its trial plan has resolved."""

from ..config import db
from . import versions
from ..risk.backtest import refundable_people
from ..world.people import PREMIUM_RATE


def expected_cost(policy: dict, episode: dict, profiles: dict) -> float:
    """What the *old* policy would have cost on this same plan: a certain
    premium for anyone it makes refundable, otherwise their flake probability
    times their share.
    """
    share = episode["cost_per_person_usd"]
    refundable = refundable_people(policy["rules"])
    yes = [r["person"] for r in episode["rsvps"] if r["rsvp"] == "yes"]
    total = 0.0
    for p in yes:
        total += PREMIUM_RATE * share if p in refundable else profiles[p]["flake"]["p_mean"] * share
    return round(total, 2)


def evaluate(group_id: str, episode: dict) -> str | None:
    """Only a plan that ran under the canary counts. Compare its realized cost
    to what the incumbent (parent) policy would have cost on the same plan:
    cheaper or equal -> promote, otherwise roll back (incumbent stays active).
    """
    canary = db.harness_versions.find_one({"group_id": group_id, "status": "canary"})
    if not canary or episode.get("version_id") != canary["_id"]:
        return None

    incumbent = versions.get(canary["parent"])
    profiles = {d["person"]: d for d in db.risk_profiles.find({"group_id": group_id})}
    expected = expected_cost(incumbent["policy"], episode, profiles)
    realized = episode["outcomes"]["total_cost_usd"]
    result = "promoted" if realized <= expected else "rolled_back"

    record = {"episode_id": episode["_id"], "expected_cost_usd": expected, "realized_cost_usd": realized, "result": result}
    if result == "promoted":
        versions.set_status(canary["_id"], "canary", {"canary": record})
        versions.promote(canary["_id"])
    else:
        versions.set_status(canary["_id"], "rolled_back", {"canary": record})
    return result
