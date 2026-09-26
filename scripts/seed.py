from flake.config import db, embed
from flake import memory
from flake.harness import versions
from flake.risk import model as risk_model
from flake.world.history import GROUP_ID, HISTORY
from flake.world.people import ORGANIZER, PEOPLE

COLLECTIONS = ("episodes", "risk_profiles", "notes")  # wiped per group so re-seeding is repeatable


def main():
    for name in COLLECTIONS:
        deleted = db[name].delete_many({"group_id": GROUP_ID}).deleted_count
        print(f"deleted {deleted} from {name}")
    db.harness_versions.delete_many({"group_id": GROUP_ID})

    # upsert: reset_demo doesn't drop `groups`, so a plain insert would collide on re-seed
    db.groups.replace_one(
        {"_id": GROUP_ID},
        {"_id": GROUP_ID, "name": "Taco Council", "organizer": ORGANIZER, "members": list(PEOPLE)},
        upsert=True,
    )

    episodes = [{**ep, "embedding": embed(ep["summary"])} for ep in HISTORY]
    db.episodes.insert_many(episodes)

    versions.create(GROUP_ID, versions.V1_POLICY, "initial probation policy", None, created_by="seed", status="active")
    risk_model.build_profiles(GROUP_ID, memory.resolved_episodes(GROUP_ID))

    lost = {p: 0 for p in PEOPLE}
    for ep in HISTORY:
        for person in ep["outcomes"]["bailed"]:
            lost[person] += ep["cost_per_person_usd"]
    print(f"inserted {len(episodes)} episodes; total lost: ${sum(lost.values())}")
    for person, usd in lost.items():
        print(f"  {person}: ${usd}")


if __name__ == "__main__":
    main()
