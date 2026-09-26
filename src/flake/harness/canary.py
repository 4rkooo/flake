"""Judges a canary once its trial plan has resolved."""

from ..config import db
from .. import observe
from . import versions
from ..risk.backtest import refundable_people
from ..world.people import PREMIUM_RATE


def expected_cost_breakdown(policy: dict, episode: dict, profiles: dict) -> list[dict]:
    """One line per yes-RSVP: a certain premium for anyone the policy makes refundable,
    otherwise their flake probability times their share. Shown by the demo as the working."""
    share = episode["cost_per_person_usd"]
    refundable = refundable_people(policy["rules"])
    yes = [r["person"] for r in episode["rsvps"] if r["rsvp"] == "yes"]
    lines = []
    for p in yes:
        if p in refundable:
            lines.append({"person": p, "refundable": True, "rate": PREMIUM_RATE, "share": share,
                          "expected_usd": round(PREMIUM_RATE * share, 2)})
        else:
            p_mean = profiles[p]["flake"]["p_mean"]
            lines.append({"person": p, "refundable": False, "rate": p_mean, "share": share,
                          "expected_usd": round(p_mean * share, 2)})
    return lines


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
        observe.emit("canary.skipped", plan_id=episode.get("_id"), version_id=episode.get("version_id"),
                     reason="no canary on trial" if not canary
                     else f"plan ran under {episode.get('version_id')}, the canary is {canary['_id']}")
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
    observe.emit("canary.evaluated", plan_id=episode["_id"], version_id=canary["_id"], incumbent=incumbent["_id"],
                 result=result, expected_cost_usd=expected, realized_cost_usd=realized,
                 breakdown=expected_cost_breakdown(incumbent["policy"], episode, profiles),
                 outcomes=episode.get("outcomes"))
    return result
