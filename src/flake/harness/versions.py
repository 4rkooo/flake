"""Owns the harness_versions collection and its state machine.

A version's `policy` is a plain dict (rules, guardrails, tool_permissions,
context_policy, model) -- not a typed model -- so Lane A's proposal shape and
Lane C's gate can each read it without a schema class in between.
"""

import os

from ..config import db
from .. import memory
from .constitution import clamp

V1_POLICY = {
    "rules": [],
    "guardrails": {
        "max_nonrefundable_exposure_usd": 0,
        "max_auto_spend_usd": 0,
        "min_expected_attendance_ratio": 0.8,
        "min_confidence": 0.85,
    },
    "tool_permissions": {
        "send_message": "auto",
        "propose_plan": "auto",
        "poll_rsvps": "auto",
        "book": {"refundable": "auto", "non_refundable": "ask"},
        "request_money": {"default": "ask", "auto_for": []},
        "cancel_booking": "ask",
        "ask_organizer": "auto",
        "finish_plan": "auto",
    },
    "context_policy": {"similar_plans_k": 3, "notes_per_person": 2, "include_recent_bails": True},
    "model": os.environ.get("LLM_MODEL", ""),
}
# ^ what a brand-new group starts on: no rules, zero exposure, zero unasked
# spend, every money action a question for Alex. The seed script stores this
# as active; everything the demo shows is measured against it.


def get_active(group_id: str) -> dict:
    return db.harness_versions.find_one({"group_id": group_id, "status": "active"})


def get_effective(group_id: str) -> dict:
    # the policy that should gate the *next* plan -- a canary on trial wins over active
    canary = db.harness_versions.find_one({"group_id": group_id, "status": "canary"})
    return canary or get_active(group_id)


def get(version_id: str) -> dict:
    return db.harness_versions.find_one({"_id": version_id})


def history(group_id: str) -> list[dict]:
    return list(db.harness_versions.find({"group_id": group_id}).sort("version", 1))


def create(
    group_id: str,
    policy: dict,
    rationale: str,
    backtest: dict | None,
    created_by: str = "retro",
    status: str = "candidate",
) -> str:
    """Clamp, number one past the latest, point `parent` at the current active
    version (rollback needs it), and store the backtest + constitution notes
    alongside the policy.
    """
    policy, notes = clamp(policy)
    latest = db.harness_versions.find_one({"group_id": group_id}, sort=[("version", -1)])
    n = (latest["version"] + 1) if latest else 1
    active = get_active(group_id)
    doc = {
        "_id": f"{group_id}:v{n}",
        "group_id": group_id,
        "version": n,
        "parent": active["_id"] if active else None,
        "status": status,
        "created_by": created_by,
        "created_at": memory.now(),
        "rationale": rationale,
        "policy": policy,
        "backtest": backtest,
        "constitution_notes": notes,
        "canary": None,
    }
    db.harness_versions.insert_one(doc)
    return doc["_id"]


def set_status(version_id: str, status: str, extra: dict | None = None) -> None:
    db.harness_versions.update_one({"_id": version_id}, {"$set": {"status": status, **(extra or {})}})


def promote(version_id: str) -> None:
    v = get(version_id)
    active = get_active(v["group_id"])
    if active and active["_id"] != version_id:
        set_status(active["_id"], "superseded")
    set_status(version_id, "active")


def rollback(group_id: str) -> str:
    # rolls back whatever is currently active, back to its parent
    active = get_active(group_id)
    if not active["parent"]:
        # checked first, or we'd retire the only active version and leave none
        raise ValueError(f"nothing to roll back to: {active['_id']} has no parent")
    set_status(active["_id"], "rolled_back")
    set_status(active["parent"], "active")
    return active["parent"]


def apply_proposal(incumbent: dict, proposal: dict, accepted_rules: list[dict]) -> dict:
    """Translates a PolicyProposal (Lane A/B's shape) into a full policy dict
    (what the gate reads). Keeping this here means the proposal shape can
    change without touching gate.py.
    """
    policy = {**incumbent, "rules": [{"id": f"r{i + 1}", **r} for i, r in enumerate(accepted_rules)]}
    policy["guardrails"] = dict(proposal["guardrails"])
    perms = {**incumbent["tool_permissions"]}
    perms["book"] = {
        "refundable": "auto",
        "non_refundable": "auto" if proposal["auto_book_nonrefundable"] else "ask",
    }
    auto_for = [p for r in accepted_rules if r["type"] == "auto_collect_from" for p in r["people"]]
    perms["request_money"] = {"default": "ask", "auto_for": sorted(set(auto_for))}
    policy["tool_permissions"] = perms
    policy["context_policy"] = {**incumbent["context_policy"], "similar_plans_k": proposal.get("similar_plans_k", 3)}
    return policy


def _flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def diff(a_id: str, b_id: str) -> list[str]:
    """Flattens both policies to dotted keys (guardrails.max_auto_spend_usd)
    and prints the ones that changed -- the demo's clearest picture of evolution.
    """
    a, b = _flatten(get(a_id)["policy"]), _flatten(get(b_id)["policy"])
    lines = []
    for key in sorted(set(a) | set(b)):
        if a.get(key) != b.get(key):
            lines.append(f"{key}: {a.get(key, '-')} -> {b.get(key, '-')}")
    return lines
