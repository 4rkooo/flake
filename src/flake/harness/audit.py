"""Append-only receipts: one document per gate decision, never updated."""

from ..config import db
from .. import memory


def log(plan_id: str, version_id: str, call: dict, decision) -> str:
    doc = {
        "_id": f"ad_{db.audit_log.count_documents({}) + 1:03d}",
        "episode_id": plan_id,
        "version_id": version_id,
        "tool": call["name"],
        "requested_args": call["args"],
        "decision": decision.action,
        "final_args": decision.final_args,
        "rule_id": decision.rule_id,
        "reason": decision.reason,
        "ts": memory.now(),
    }
    db.audit_log.insert_one(doc)
    return doc["_id"]
