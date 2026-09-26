"""The five scripted, resolved plans Alex organized before Flake existed -- owned by Lane B.

Each is a full episode dict (group_id "taco-council", status "resolved", outcomes, summary).
scripts/seed.py (Lane C) adds the embeddings and inserts them.
"""
from datetime import date

from flake.world.people import PEOPLE, ORGANIZER

GROUP_ID = "taco-council"

EPISODE_SPECS = [
    {
        "_id": "ep_001",
        "kind": "dinner",
        "min_people": 3,
        "title": "Pizza night",
        "day": "2026-08-25",
        "day_type": "weekday",
        "cost_per_person_usd": 20,
        "bailed": ["sam", "maya"],
        "paid_late_days": {"jordan": 12, "priya": 0},
    },
    {
        "_id": "ep_002",
        "kind": "karaoke",
        "min_people": 3,
        "title": "Karaoke Friday",
        "day": "2026-08-28",
        "day_type": "weekday",
        "cost_per_person_usd": 40,
        "bailed": ["sam"],
        "paid_late_days": {"jordan": 8, "priya": 0, "maya": 0},
    },
    {
        "_id": "ep_003",
        "kind": "trip",
        "min_people": 3,
        "title": "Ski trip",
        "day": "2026-09-05",
        "day_type": "saturday",
        "cost_per_person_usd": 150,
        "bailed": ["sam"],
        "paid_late_days": {"jordan": 20, "priya": 0, "maya": 0},
    },
    {
        "_id": "ep_004",
        "kind": "brunch",
        "min_people": 3,
        "title": "Sunday brunch",
        "day": "2026-09-13",
        "day_type": "sunday",
        "cost_per_person_usd": 30,
        "bailed": [],
        "paid_late_days": {"jordan": 6, "sam": 7, "priya": 0, "maya": 0},
    },
    {
        "_id": "ep_005",
        "kind": "tickets",
        "min_people": 3,
        "title": "Comedy show",
        "day": "2026-09-17",
        "day_type": "weekday",
        "cost_per_person_usd": 35,
        "bailed": ["sam", "maya"],
        "paid_late_days": {"jordan": 5, "priya": 0},
    },
]

WEEKDAY_DAY_TYPES = {5: "saturday", 6: "sunday"}


def day_type_of(day):
    return WEEKDAY_DAY_TYPES.get(date.fromisoformat(day).weekday(), "weekday")


def check_day_type(spec):
    actual = day_type_of(spec["day"])
    if actual != spec["day_type"]:
        raise ValueError(
            f"{spec['_id']}: {spec['day']} is a {actual}, but day_type says {spec['day_type']}"
        )


def join_names(names):
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def summarize(spec, lost):
    day_type = spec["day_type"]
    when = "a weekday" if day_type == "weekday" else f"a {day_type.capitalize()}"
    if spec["bailed"]:
        who = f"{join_names([p.capitalize() for p in spec['bailed']])} bailed"
    else:
        who = "Nobody bailed"
    return (
        f"{spec['title']} on {when}, ${spec['cost_per_person_usd']} each. "
        f"{who}; ${lost} lost."
    )


def build_episode(spec):
    people = list(PEOPLE)
    share = spec["cost_per_person_usd"]
    bailed = spec["bailed"]
    showed = [p for p in people if p not in bailed]
    covered = sorted(people) + [ORGANIZER]
    lost = share * len(bailed)
    return {
        "_id": spec["_id"],
        "group_id": GROUP_ID,
        "title": spec["title"],
        "kind": spec["kind"],
        "min_people": spec["min_people"],
        "day": spec["day"],
        "day_type": spec["day_type"],
        "cost_per_person_usd": share,
        "rsvps": [{"person": p, "rsvp": "yes"} for p in people],
        "status": "resolved",
        "booking": {
            "non_refundable_for": covered,
            "refundable_for": [],
            "deposit_usd": share * len(covered),
            "premium_usd": 0,
        },
        "outcomes": {
            "showed": showed,
            "bailed": bailed,
            "paid_late_days": spec["paid_late_days"],
            "lost_nonrefundable_usd": lost,
            "premium_paid_usd": 0,
            "total_cost_usd": lost,
        },
        "summary": summarize(spec, lost),
    }


for _spec in EPISODE_SPECS:  # fail at import if a hand-typed day_type disagrees with its date
    check_day_type(_spec)

HISTORY: list[dict] = [build_episode(spec) for spec in EPISODE_SPECS]
