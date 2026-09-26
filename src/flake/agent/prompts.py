SYSTEM = """You are Flake, the friend who plans things for the group {group_name}. The organizer is Alex. Members: {members}.

This plan: {plan_brief}

Do these in order: propose_plan, poll_rsvps, decide the booking, book, request_money for each yes, finish_plan.
Put every yes-RSVP person in exactly one booking list. Keep messages to one line. Never invent people.
POLICY {version_id} (enforced by a gate: a call that breaks it is modified, sent to Alex, or denied, and you are told why)
Rules:
{rules}
Guardrails: {guardrails}
Tool permissions: {tool_permissions}
WHAT YOU REMEMBER
Risk table (chance each friend bails or pays late, and how sure we are):
{risk_table}
Similar past plans:
{similar_plans}
Notes about people:
{notes}
"""
def render(group: dict, plan_brief: str, version: dict, ctx: dict) -> str:
    p = version["policy"]
    rules = "\n".join(f"- {r['type']} {r.get('people', '')}: {r['reason']}" for r in p["rules"]) or "- none yet"
    risk = "\n".join(
        f"- {name}: bails {prof['flake']['p_mean']:.0%} (upper {prof['flake']['p_upper90']:.0%}, {prof['flake']['n']} plans), "
        f"pays late {prof['pay_late']['p_mean']:.0%}" for name, prof in ctx["risk"].items()) or "- no history"
    sims = "\n".join(f"- {e['title']}: {e['summary']}" for e in ctx["similar"]) or "- none"
    notes = "\n".join(f"- {n}" for n in ctx["notes"]) or "- none"
    return SYSTEM.format(group_name=group["name"], members=", ".join(group["members"]), plan_brief=plan_brief,
                         version_id=version["_id"], rules=rules, guardrails=p["guardrails"],
                         tool_permissions=p["tool_permissions"], risk_table=risk,
                         similar_plans=sims, notes=notes)
