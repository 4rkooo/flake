from flake.config import db
from flake import memory

def build(group_id: str, brief: str, cp: dict) -> dict:
    risk = {d["person"]: d for d in db.risk_profiles.find({"group_id": group_id})}
    similar = memory.similar_episodes(group_id, brief, cp.get("similar_plans_k", 3))
    notes = memory.search_notes(group_id, brief, cp.get("notes_per_person", 2))
    recent_bails = []
    if cp.get("include_recent_bails", True):
        for e in memory.resolved_episodes(group_id)[-3:]:
            for person in e.get("outcomes", {}).get("bailed", []):
                recent_bails.append(f"{person} bailed on {e['title']}")
    return {"risk": risk, "similar": similar, "notes": notes + recent_bails}