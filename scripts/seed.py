from datetime import date

from flake.config import db
from flake.world.people import PEOPLE, ORGANIZER

GROUP_ID = "friends"
COLLECTIONS = ("episodes", "risk_profiles", "notes")

EPISODE_SPECS = [
    {
        "_id": "ep_001",
        "title": "Pizza night",
        "day": "2026-08-25",
        "day_type": "weekday",
        "cost_per_person_usd": 20,
        "bailed": ["sam", "maya"],
        "paid_late_days": {"jordan": 12, "priya": 0},
    },
    {
        "_id": "ep_002",
        "title": "Karaoke Friday",
        "day": "2026-08-28",
        "day_type": "weekday",
        "cost_per_person_usd": 40,
        "bailed": ["sam"],
        "paid_late_days": {"jordan": 8, "priya": 0, "maya": 0},
    },
    {
        "_id": "ep_003",
        "title": "Ski trip",
        "day": "2026-09-05",
        "day_type": "saturday",
        "cost_per_person_usd": 150,
        "bailed": ["sam"],
        "paid_late_days": {"jordan": 20, "priya": 0, "maya": 0},
    },
    {
        "_id": "ep_004",
        "title": "Sunday brunch",
        "day": "2026-09-13",
        "day_type": "sunday",
        "cost_per_person_usd": 30,
        "bailed": [],
        "paid_late_days": {"jordan": 6, "sam": 7, "priya": 0, "maya": 0},
    },
    {
        "_id": "ep_005",
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


def main():
    for spec in EPISODE_SPECS:
        check_day_type(spec)

    episodes = [build_episode(spec) for spec in EPISODE_SPECS]

    for name in COLLECTIONS:
        deleted = db[name].delete_many({"group_id": GROUP_ID}).deleted_count
        print(f"deleted {deleted} from {name}")

    db.episodes.insert_many(episodes)

    lost_per_person = {p: 0 for p in PEOPLE}
    for spec in EPISODE_SPECS:
        for person in spec["bailed"]:
            lost_per_person[person] += spec["cost_per_person_usd"]
    total_lost = sum(lost_per_person.values())

    print(f"inserted {len(episodes)} episodes")
    print(f"total lost: ${total_lost}")
    print("lost per person:")
    for person, lost in lost_per_person.items():
        print(f"  {person}: ${lost}")


if __name__ == "__main__":
    main()
