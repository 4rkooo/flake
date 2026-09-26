"""Shared memory layer -- owned by Lane A: episodes, chat, notes, vector search.

now/get_episode/resolved_episodes/current_run are simple DB pass-throughs, shipped
early so Lane C's code has something real to run against. save/similar_episodes
are Lane A's real work (writes + $vectorSearch).
"""

from datetime import datetime, timezone

from .config import db

current_run: dict = {}  # set by agent/graph.py per request, e.g. current_run["plan_id"] = ep["_id"]


def now() -> datetime:
    return datetime.now(timezone.utc)


def get_episode(plan_id: str) -> dict | None:
    return db.episodes.find_one({"_id": plan_id})


def resolved_episodes(group_id: str) -> list[dict]:
    return list(db.episodes.find({"group_id": group_id, "status": "resolved"}).sort("resolved_at", 1))


def save(episode: dict) -> None:
    raise NotImplementedError("Lane A: upsert an episode doc, embed its summary")


def similar_episodes(group_id: str, brief: str, k: int) -> list[dict]:
    raise NotImplementedError("Lane A: $vectorSearch over episodes.embedding")
