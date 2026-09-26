from flake.config import db, embed
from flake import memory
from flake.harness import versions
from flake.risk import model as risk_model
from flake.world.people import HISTORY, MEMBERS, ORGANIZER

GROUP = "taco-council"

db.groups.insert_one({"_id": GROUP, "name": "Taco Council", "organizer": ORGANIZER, "members": MEMBERS})

for ep in HISTORY:  # the five scripted plans from Lane B, as dicts
    ep["embedding"] = embed(ep["summary"])
    db.episodes.insert_one(ep)

versions.create(GROUP, versions.V1_POLICY, "initial probation policy", None, created_by="seed", status="active")
risk_model.build_profiles(GROUP, memory.resolved_episodes(GROUP))
