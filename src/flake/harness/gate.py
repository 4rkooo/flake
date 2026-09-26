"""The policy enforcement point. Lane A's graph calls check() from its gate
node for every tool call the model makes; there is no path from the model to
the world that skips it.
"""

from dataclasses import dataclass

from .. import memory
from ..risk import model as risk_model
from ..world import simulator
from ..world.people import ORGANIZER, PREMIUM_RATE


@dataclass
class Decision:
    action: str  # allow | modify | ask | deny
    final_args: dict
    reason: str
    rule_id: str | None = None


def permission(tool: str, args: dict, perms: dict) -> str:
    """Looks the tool up in tool_permissions. Unknown tools default to ask."""
    p = perms.get(tool, "ask")
    if tool == "book":
        # non-refundable for anyone but the organizer decides which sub-permission applies
        nonref = [x for x in args.get("non_refundable_for", []) if x != ORGANIZER]
        return p["non_refundable"] if nonref else p["refundable"]
    if tool == "request_money":
        return "auto" if args.get("person") in p.get("auto_for", []) else p.get("default", "ask")
    return p


def check(tool: str, args: dict, policy: dict, risk: dict, approvals: list[dict] = ()) -> Decision:
    args = dict(args)  # never mutate the model's own args in place
    mode = permission(tool, args, policy["tool_permissions"])
    if mode == "deny":
        return Decision("deny", args, f"{tool} is denied by policy")

    approved = any(a.get("tool") == tool for a in approvals)  # did Alex already say yes to this tool on this plan?
    action, reason, rule_id = "allow", "within policy", None
    episode = memory.get_episode(memory.current_run.get("plan_id", "")) or {}

    # step 2: rules -- reshape the call before guardrails judge it
    for rule in policy["rules"]:
        t = rule["type"]
        if tool == "book" and t == "book_refundable_for":
            moved = [p for p in args.get("non_refundable_for", []) if p in rule["people"]]
            if moved:
                args["non_refundable_for"] = [p for p in args["non_refundable_for"] if p not in moved]
                args["refundable_for"] = sorted(set(args.get("refundable_for", [])) | set(moved))
                action, reason, rule_id = "modify", f"book_refundable_for applies to {', '.join(moved)}", rule["id"]
        if tool == "book" and t == "require_deposit_from":
            invited = set(args.get("non_refundable_for", [])) | set(args.get("refundable_for", []))
            deposited = {m["person"] for m in episode.get("money_requests", []) if m.get("upfront")}
            missing = [p for p in rule["people"] if p in invited and p not in deposited]
            if missing:
                return Decision(
                    "deny", args, f"call request_money(upfront=True) for {', '.join(missing)} before booking", rule["id"]
                )
        if tool == "propose_plan" and t == "avoid_day_type" and simulator.day_type(args["day"]) == rule["day_type"]:
            mode, reason, rule_id = "ask", f"plans on a {rule['day_type']} need Alex's ok", rule["id"]
        if tool == "propose_plan" and t == "max_plan_cost_usd" and args.get("cost_per_person_usd", 0) > rule["amount"]:
            mode, reason, rule_id = "ask", f"over the ${rule['amount']} per-person cap", rule["id"]

    # step 3: guardrails -- only ever escalate to ask, never silently allow
    if tool == "book":
        g = policy["guardrails"]
        share = episode.get("cost_per_person_usd", 0)
        nonref = [p for p in args.get("non_refundable_for", []) if p != ORGANIZER]
        exposure = share * len(nonref)
        spend = share * (len(nonref) + 1) + round(PREMIUM_RATE * share * len(args.get("refundable_for", [])))
        problems = []
        if exposure > g["max_nonrefundable_exposure_usd"]:
            problems.append(f"non-refundable exposure ${exposure} is over the ${g['max_nonrefundable_exposure_usd']} cap")
        if spend > g["max_auto_spend_usd"]:
            problems.append(f"spend ${spend} is over the ${g['max_auto_spend_usd']} auto-spend cap")
        if nonref and risk:
            yes = [r["person"] for r in episode.get("rsvps", []) if r["rsvp"] == "yes"]
            forecast = risk_model.attendance(risk, yes, episode.get("min_people", 1))
            if forecast["p_at_least_min"] < g["min_confidence"]:
                problems.append(f"only {forecast['p_at_least_min']:.0%} confidence that {episode.get('min_people')} show")
        if problems:
            mode, reason = "ask", "; ".join(problems)

    # step 4: verdict -- an unapproved ask goes back as a question; else allow/modify with final args
    if mode == "ask" and not approved:
        return Decision("ask", args, f"Approve {tool} {args}? Reason: {reason}", rule_id)
    return Decision(action, args, reason, rule_id)
