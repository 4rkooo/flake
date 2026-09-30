"""The outer loop, orchestrated by Lane C: B's risk model, A's proposal (or a
scripted fallback), B's backtest, then C's versions.
"""

from .. import memory, observe
from ..config import db
from ..agent import underwriter_llm
from . import constitution, versions
from ..risk import backtest, model as risk_model

# a deliberately bad proposal, for the `flake retro --reckless` rejection beat.
# No rules and the caps sitting right at the floors -- the backtest's negative
# delta is real, not staged.
RECKLESS = {
    "rules": [],
    "guardrails": {
        "max_nonrefundable_exposure_usd": 300,
        "max_auto_spend_usd": 100,
        "min_expected_attendance_ratio": 0.6,
        "min_confidence": 0.75,
    },
    "auto_book_nonrefundable": True,
    "similar_plans_k": 1,
    "rationale": "Drop the refundable rules and save the premiums.",
}


def run(group_id: str, scripted: dict | None = None) -> dict:
    # a canary judges exactly one plan; a second Retro now would muddy which version is on trial
    on_trial = db.harness_versions.find_one({"group_id": group_id, "status": "canary"})
    if on_trial:
        raise RuntimeError(f"canary {on_trial['_id']} is still on trial; run `flake tick` first")

    episodes = memory.resolved_episodes(group_id)
    incumbent = versions.get_active(group_id)
    observe.emit("retro.start", group_id=group_id, scripted=scripted is not None, episodes=[e["_id"] for e in episodes],
                 incumbent=incumbent["_id"])
    profiles = risk_model.build_profiles(group_id, episodes)
    losses = [e for e in episodes if e["outcomes"]["total_cost_usd"] > 0]

    proposal = scripted or underwriter_llm.propose(incumbent["policy"], profiles, losses, constitution.FLOORS).model_dump()
    observe.emit("retro.proposal", group_id=group_id, source="scripted" if scripted else "underwriter", proposal=proposal,
                 losses=[{"_id": e["_id"], "title": e.get("title"), "total_cost_usd": e["outcomes"]["total_cost_usd"]} for e in losses])
    bt = backtest.run(proposal["rules"], incumbent["policy"]["rules"], episodes)
    policy = versions.apply_proposal(incumbent["policy"], proposal, bt["accepted"])
    vid = versions.create(group_id, policy, proposal["rationale"], bt)

    status = "canary" if bt["accepted"] and bt["delta_usd"] >= 0 else "rejected"
    versions.set_status(vid, status)
    observe.emit("retro.done", group_id=group_id, version_id=vid, status=status, incumbent=incumbent["_id"],
                 delta_usd=bt["delta_usd"], accepted=len(bt["accepted"]), rejected=len(bt["rejected"]))
    return {"version_id": vid, "status": status, "profiles": profiles, "backtest": bt}
