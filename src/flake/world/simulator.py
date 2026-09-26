"""Outcomes arrive late, repeatably; rsvp, book, organizer_answer, resolve, tick -- owned by Lane B."""

import random
from datetime import date, timedelta

from flake import memory, observe
from flake.config import db, DEMO_SEED
from flake.world.people import LATE_DAYS, ORGANIZER, PEOPLE, PREMIUM_RATE

# TODO: the db.episodes writes below should move to memory.update_episode /
# finish_episode (they exist now). Notes already go through memory.add_note.

rng = random.Random(DEMO_SEED)

SCRIPT = {"sam": {"ep_006": "bail", "ep_007": "bail"}}

WEEKDAY_DAY_TYPES = {5: "weekend", 6: "weekend"}  # schema.md: weekday | weekend


def day_type(iso_day):
    return WEEKDAY_DAY_TYPES.get(date.fromisoformat(iso_day).weekday(), "weekday")


def rsvp(episode):
    return [{"person": p, "rsvp": "yes"} for p in PEOPLE]


def book(episode, non_refundable_for, refundable_for):
    share = episode["cost_per_person_usd"]
    nonref = sorted(set(non_refundable_for) | {ORGANIZER})
    return {
        "non_refundable_for": nonref,
        "refundable_for": sorted(refundable_for),
        "deposit_usd": share * len(nonref),
        "premium_usd": PREMIUM_RATE * share * len(refundable_for),
    }


def scripted_organizer(question):
    return "yes"  # Alex approves everything in the CLI demo


_organizer = scripted_organizer


def set_organizer(fn):
    """The visual demo swaps in a live presenter here; None restores the scripted yes.
    The CLI never calls this, so `flake plan` keeps its simulated answer."""
    global _organizer
    _organizer = fn or scripted_organizer


def organizer_answer(question):
    return _organizer(question)


def _add_note(episode, person, dt, share):
    # through Lane A's store, not db.notes directly: the store keys its documents,
    # and raw inserts make its startup backfill hit a duplicate-key error
    memory.add_note(episode["group_id"], f"{person}-{episode['_id']}",
                    f"{person} bailed on {episode['title']} ({dt}, ${share} share)")


def resolve(episode):
    share = episode["cost_per_person_usd"]
    dt = day_type(episode["day"])
    yes = [r["person"] for r in episode.get("rsvps", []) if r["rsvp"] == "yes"]

    showed = []
    bailed = []
    paid_late_days = {}
    for person in yes:
        scripted = SCRIPT.get(person, {}).get(episode["_id"])
        if scripted is not None:
            bails = scripted == "bail"
        else:
            bails = rng.random() < PEOPLE[person]["flake"][dt]

        if bails:
            bailed.append(person)
            _add_note(episode, person, dt, share)
        else:
            showed.append(person)
            late = rng.random() < PEOPLE[person]["late"]
            paid_late_days[person] = rng.randint(*LATE_DAYS) if late else 0

    booking = episode.get("booking", {})
    nonref = set(booking.get("non_refundable_for", []))
    lost = share * len([p for p in bailed if p in nonref])
    premium = booking.get("premium_usd", 0)

    return {
        "showed": showed,
        "bailed": bailed,
        "paid_late_days": paid_late_days,
        "lost_nonrefundable_usd": lost,
        "premium_paid_usd": premium,
        "total_cost_usd": lost + premium,
    }


def tick(days):
    # Each `flake tick` is its own process, so the world always rolls from a fresh DEMO_SEED.
    # The demo server ticks twice in one process and reseeds here to get the same draws.
    rng.seed(DEMO_SEED)
    resolved_at = (date.today() + timedelta(days=days)).isoformat()
    resolved_ids = []

    for episode in list(db.episodes.find({"status": "booked"})):
        outcomes = resolve(episode)
        summary = episode.get("summary", "") + (
            f" Outcome: bailed {len(outcomes['bailed'])}, "
            f"cost ${outcomes['total_cost_usd']:.2f}."
        )
        db.episodes.update_one(
            {"_id": episode["_id"]},
            {
                "$set": {
                    "outcomes": outcomes,
                    "resolved_at": resolved_at,
                    "summary": summary,
                }
            },
        )
        db.episodes.update_one(
            {"_id": episode["_id"]}, {"$set": {"status": "resolved"}}
        )
        observe.emit("sim.resolved", plan_id=episode["_id"], title=episode.get("title"),
                     version_id=episode.get("version_id"), day_type=day_type(episode["day"]),
                     share=episode["cost_per_person_usd"], booking=episode.get("booking"),
                     outcomes=outcomes, resolved_at=resolved_at, scripted=[p for p in outcomes["bailed"]
                                                                            if SCRIPT.get(p, {}).get(episode["_id"])])
        resolved_ids.append(episode["_id"])

    observe.emit("sim.tick", days=days, resolved=resolved_ids)
    return resolved_ids


if __name__ == "__main__":
    import json

    episode = {
        "_id": "ep_006",
        "group_id": "friends",
        "title": "Beach weekend",
        "day": "2026-10-03",
        "day_type": "weekend",
        "cost_per_person_usd": 80,
        "status": "booked",
        "summary": "Beach weekend, $80 each.",
    }
    episode["rsvps"] = rsvp(episode)
    episode["booking"] = book(episode, ["priya", "jordan"], ["sam", "maya"])
    db.episodes.replace_one({"_id": episode["_id"]}, episode, upsert=True)

    resolved_ids = tick(7)
    print(f"resolved: {resolved_ids}")
    for _id in resolved_ids:
        doc = db.episodes.find_one({"_id": _id})
        print(f"\n{_id} summary: {doc['summary']}")
        print(json.dumps(doc["outcomes"], indent=2))
