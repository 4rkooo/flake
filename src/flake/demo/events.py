"""Turn observe calls into journal rows: which diagram node lights up, a one-line summary
a presenter can read aloud, and bounded inspector details. Embeddings, query vectors,
credentials and full model prompts never reach the browser."""

import json

# planning loop: memory -> agent -> gate -> tools -> agent; learning loop: outcomes -> risk -> proposal -> backtest -> policy -> gate
NODE_FOR_GRAPH = {"load_context": "memory", "agent": "agent", "gate": "gate", "tools": "tools", "record_episode": "memory"}
DROP_KEYS = {"embedding", "queryVector"}
MAX_STR = 800
MAX_LIST = 40
MAX_DEPTH = 7

CACHE_LABEL = {"hit": "cached replay", "miss": "fresh API call", "off": "fresh API call, cache off",
               "scripted": "scripted model"}


def bounded(value, depth: int = 0):
    """JSON-safe and small: long strings cut, long lists capped, embeddings dropped."""
    if depth > MAX_DEPTH:
        return "..."
    if isinstance(value, dict):
        return {str(k): bounded(v, depth + 1) for k, v in value.items() if k not in DROP_KEYS}
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        out = [bounded(v, depth + 1) for v in items[:MAX_LIST]]
        if len(items) > MAX_LIST:
            out.append(f"... {len(items) - MAX_LIST} more")
        return out
    if isinstance(value, str):
        return value if len(value) <= MAX_STR else value[:MAX_STR] + f"... [{len(value) - MAX_STR} more chars]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def money(x) -> str:
    try:
        return f"${float(x):,.2f}"
    except (TypeError, ValueError):
        return str(x)


def pct(x) -> str:
    try:
        return f"{float(x):.0%}"
    except (TypeError, ValueError):
        return str(x)


def _parse(content):
    # ToolNode serialises dict/list results as JSON strings; give the inspector the structure back
    if isinstance(content, str):
        s = content.strip()
        if s[:1] in "[{":
            try:
                return json.loads(s)
            except ValueError:
                return content
    return content


def _people(xs) -> str:
    return ", ".join(xs) if xs else "nobody"


def translate(kind: str, f: dict) -> dict:
    """-> {node, status, summary, details, plan_id, version_id}. node None = beat-level (or
    'attach to the current node' for db.* rows, which the coordinator fills in)."""
    node, status, summary = None, "info", kind
    details = dict(f)
    plan_id, version_id = f.get("plan_id"), f.get("version_id")

    if kind == "node.start":
        node, status = NODE_FOR_GRAPH.get(f.get("node"), f.get("node")), "start"
        n = f.get("node")
        if n == "load_context":
            summary = "Loading context: policy in force, risk table, similar plans, notes"
        elif n == "agent":
            summary = f"Agent turn {f.get('turn')}: model deciding"
        elif n == "gate":
            summary = "Gate checking the requested tool calls"
        elif n == "tools":
            names = [c["name"] for c in f.get("calls", [])]
            summary = "Running " + (", ".join(names) if names else "no tools")
        else:
            summary = "Recording the episode"
    elif kind == "node.end":
        node, status, summary = NODE_FOR_GRAPH.get(f.get("node"), f.get("node")), "ok", f"{f.get('node')} done"
    elif kind == "policy.loaded":
        node, status = "policy", "ok"
        p = f.get("policy") or {}
        g = p.get("guardrails", {})
        summary = (f"Policy {f.get('version_id')} ({f.get('status')}) in force: {len(p.get('rules', []))} rule(s), "
                   f"exposure cap {money(g.get('max_nonrefundable_exposure_usd', 0))}, "
                   f"auto-spend {money(g.get('max_auto_spend_usd', 0))}")
    elif kind == "context.built":
        node, status = "memory", "ok"
        summary = (f"Context loaded: {len(f.get('risk', {}))} risk profiles, {len(f.get('similar', []))} similar plans, "
                   f"{len(f.get('notes', []))} notes")
        details["risk"] = {p: {"flake": d.get("flake"), "pay_late": d.get("pay_late"), "flake_score": d.get("flake_score")}
                           for p, d in (f.get("risk") or {}).items()}
    elif kind == "memory.similar":
        node = "memory"
        hits = f.get("hits", [])
        if f.get("method") == "vector_search":
            status = "ok"
            top = ", ".join(f"{h.get('title')} ({h.get('score'):.2f})" if isinstance(h.get("score"), (int, float))
                            else str(h.get("title")) for h in hits[:3])
            summary = f"Vector search ($vectorSearch, k={f.get('k')}): {len(hits)} similar plan(s): {top}"
        else:
            status = "warn"
            why = f.get("error") or "the search returned no hits"
            summary = f"Vector search fallback: {why}; using the {len(hits)} most recent plan(s) instead"
    elif kind == "memory.notes":
        node = "memory"
        if f.get("method") == "store_search":
            status, summary = "ok", f"Notes search: {len(f.get('hits', []))} note(s) about the friends"
        else:
            status, summary = "warn", f"Notes store fallback: {f.get('error')}; no notes loaded"
    elif kind == "memory.embedded":
        node, status, summary = "memory", "ok", f"Summary embedded ({f.get('dims')} dims) and stored on {plan_id}"
    elif kind == "episode.created":
        node, status = "tools", "ok"
        e = f.get("fields", {})
        summary = (f"Episode {plan_id} created: {e.get('title')} on {e.get('day')} ({e.get('day_type', '?')}), "
                   f"{money(e.get('cost_per_person_usd', 0))} each, min {e.get('min_people')}")
    elif kind == "approval.recorded":
        node, status, summary = "tools", "ok", f"Approval recorded on {plan_id}: {f.get('tool')} may now run"
    elif kind == "chat.message":
        node, status, summary = "tools", "ok", f"{f.get('sender')} in chat: {f.get('text')}"
    elif kind == "llm.cache":
        node = "agent"
        status = "ok" if f.get("hit") else "info"
        summary = "Model cache hit: replaying the recorded response" if f.get("hit") else "Model cache miss: fresh API call"
    elif kind == "llm.cache.stored":
        node, status, summary = "agent", "ok", "Fresh model response stored in the cache"
    elif kind == "llm.turn":
        node, status = "agent", "ok"
        label = CACHE_LABEL.get(f.get("cache"), str(f.get("cache")))
        calls = f.get("tool_calls", [])
        if calls:
            summary = f"Model turn {f.get('turn')} ({label}): requests " + ", ".join(c["name"] for c in calls)
        else:
            summary = f"Model turn {f.get('turn')} ({label}): no tool calls, finishing"
    elif kind == "gate.decision":
        node = "gate"
        d = f.get("decision")
        status = {"allow": "ok", "modify": "ok", "ask": "warn", "deny": "error"}.get(d, "info")
        summary = f"Gate {str(d).upper()}: {f.get('tool')}"
        reason = f.get("reason")
        if d in ("allow", "modify") and reason and reason != "within policy" and not str(reason).startswith("book_refundable_for"):
            # the only way an allow carries guardrail text is the retry after Alex said yes
            summary = f"Gate {str(d).upper()} (approved by Alex): {f.get('tool')} — {reason}"
        elif reason and reason != "within policy":
            summary += f" — {reason}"
        elif d == "allow":
            summary += " — within policy"
        if f.get("rule_id"):
            summary += f" [{f.get('rule_id')}]"
        details["args_changed"] = f.get("requested_args") != f.get("final_args")
    elif kind == "risk.attendance":
        node, status = "gate", "ok"
        summary = (f"Attendance forecast: expected {f.get('expected'):.2f} of {len(f.get('yes_people', []))} show; "
                   f"{pct(f.get('p_at_least_min'))} chance that at least {f.get('min_people')} show ({f.get('sims')} draws)")
    elif kind == "tool.result":
        node = "tools"
        name, args, result = f.get("name"), f.get("args") or {}, _parse(f.get("result"))
        status = "error" if f.get("status") == "error" else "ok"
        details["result"] = result
        if name == "propose_plan":
            summary = f"propose_plan → {result}"
        elif name == "poll_rsvps" and isinstance(result, list):
            yes = [r["person"] for r in result if isinstance(r, dict) and r.get("rsvp") == "yes"]
            summary = f"poll_rsvps → {len(yes)} yes ({_people(yes)}), {len(result) - len(yes)} no"
        elif name == "book" and isinstance(result, dict):
            summary = (f"book → receipt: deposit {money(result.get('deposit_usd', 0))}, premium {money(result.get('premium_usd', 0))}; "
                       f"non-refundable {_people(result.get('non_refundable_for'))}, refundable {_people(result.get('refundable_for'))}")
        elif name == "request_money":
            summary = (f"request_money({args.get('person')}, {money(args.get('amount_usd', 0))}"
                       f"{', upfront deposit' if args.get('upfront') else ''}) → {result}")
        elif name == "ask_organizer":
            summary = f"ask_organizer → Alex answered “{result}”"
        elif name == "send_message":
            summary = f"send_message → posted: {args.get('text')}"
        elif name == "finish_plan":
            summary = "finish_plan → summary saved, episode marked booked"
        elif name == "policy_notice":
            status, summary = "error", f"policy_notice → {result}"
        else:
            summary = f"{name} → {result}"
    elif kind == "plan.start":
        status, summary = "start", f"Alex asked: “{f.get('brief')}”"
    elif kind == "plan.recorded":
        node = "memory"
        status = "ok" if f.get("status") == "booked" else "warn"
        summary = f"Episode {plan_id} recorded as {f.get('status')} under {version_id} after {f.get('turns')} turn(s)"
        if f.get("incomplete_reason"):
            summary += f": {f.get('incomplete_reason')}"
    elif kind == "plan.end":
        status = "ok" if f.get("booking") else "warn"
        summary = (f"Plan {plan_id} finished: booked under {version_id}" if f.get("booking")
                   else f"Plan {plan_id} finished without a booking: {f.get('incomplete_reason')}")
    elif kind == "sim.resolved":
        node, status = "outcomes", "ok"
        o = f.get("outcomes", {})
        late = [f"{p} {d}d late" for p, d in (o.get("paid_late_days") or {}).items() if d]
        summary = (f"{f.get('title')} resolved: {_people(o.get('bailed'))} bailed; cost {money(o.get('total_cost_usd', 0))} "
                   f"(lost {money(o.get('lost_nonrefundable_usd', 0))} non-refundable, {money(o.get('premium_paid_usd', 0))} premiums)")
        if late:
            summary += "; " + ", ".join(late)
    elif kind == "sim.tick":
        node, status = "outcomes", "ok"
        n = len(f.get("resolved", []))
        summary = f"Advanced {f.get('days')} days: {n} plan(s) resolved" if n else f"Advanced {f.get('days')} days: nothing was booked, nothing to resolve"
        if not n:
            status = "warn"
    elif kind == "risk.profiles":
        node, status = "risk", "ok"
        profs = f.get("profiles", {})
        summary = f"Risk table rebuilt from {f.get('episodes')} plans: " + ", ".join(
            f"{p} bails {pct(d['flake']['p_mean'])} (upper {pct(d['flake']['p_upper90'])}, score {d.get('flake_score')})"
            for p, d in profs.items())
    elif kind == "proposal.pricing":
        node, status = "proposal", "ok"
        g = f.get("guardrails", {})
        summary = (f"Pricing model decided {len(f.get('rules', []))} rule(s); exposure cap {money(g.get('max_nonrefundable_exposure_usd', 0))}, "
                   f"auto-spend {money(g.get('max_auto_spend_usd', 0))}; auto non-refundable booking "
                   f"{'on' if f.get('auto_book_nonrefundable') else 'off'}")
    elif kind == "proposal.worded":
        node, status = "proposal", "ok"
        summary = f"Underwriter LLM worded the proposal ({CACHE_LABEL.get(f.get('cache'), f.get('cache'))})"
        if not f.get("reasons_applied"):
            summary += "; rule reasons kept from the pricing model"
    elif kind == "proposal.fallback":
        node, status = "proposal", "warn"
        summary = f"LLM unavailable ({f.get('error')}): deterministic proposal fallback"
    elif kind == "retro.start":
        node, status = "risk", "start"
        summary = f"Retro over {len(f.get('episodes', []))} resolved plans against {f.get('incumbent')}"
        if f.get("scripted"):
            summary += " (scripted reckless proposal)"
    elif kind == "retro.proposal":
        node, status = "proposal", "ok"
        p = f.get("proposal", {})
        summary = f"Proposal ({f.get('source')}): {len(p.get('rules', []))} rule(s). {p.get('rationale', '')}"
    elif kind == "backtest.run":
        node = "backtest"
        status = "ok" if f.get("decision") == "ship" else "warn"
        delta = f.get("delta_usd", 0)
        summary = (f"Backtest over {f.get('episodes')} plans: incumbent {money(f.get('baseline_usd'))} → proposed {money(f.get('proposed_usd'))}, "
                   f"delta {'+' if delta >= 0 else ''}{money(delta)} → {f.get('decision')}; "
                   f"{len(f.get('accepted', []))} rule(s) accepted, {len(f.get('rejected', []))} rejected")
    elif kind == "version.created":
        node, status = "policy", "ok"
        notes = f.get("constitution_notes") or []
        summary = f"Version {version_id} created ({f.get('status')}) with {len((f.get('policy') or {}).get('rules', []))} rule(s); "
        summary += ("constitution clamped: " + "; ".join(notes)) if notes else "constitution check: nothing to clamp"
    elif kind == "version.status":
        node, status = "policy", "ok"
        summary = f"{version_id} → {f.get('status')}"
        c = (f.get("extra") or {}).get("canary")
        if c:
            summary += f" (canary on {c.get('episode_id')}: realized {money(c.get('realized_cost_usd'))} vs expected {money(c.get('expected_cost_usd'))})"
    elif kind == "canary.evaluated":
        node = "policy"
        status = "ok" if f.get("result") == "promoted" else "warn"
        summary = (f"Canary {version_id} on {plan_id}: realized {money(f.get('realized_cost_usd'))} vs "
                   f"{f.get('incumbent')} expected {money(f.get('expected_cost_usd'))} → {f.get('result')}")
    elif kind == "canary.skipped":
        node, status, summary = "policy", "info", f"Canary check skipped: {f.get('reason')}"
    elif kind == "retro.done":
        node = "policy"
        status = "ok" if f.get("status") == "canary" else "warn"
        delta = f.get("delta_usd", 0)
        summary = f"Retro result: {version_id} is {f.get('status')} (backtest delta {'+' if delta >= 0 else ''}{money(delta)})"
    elif kind == "policy.compared":
        node, status = "policy", "ok"
        c = f.get("compare", {})
        summary = (f"Compared {c.get('from', {}).get('id')} → {c.get('to', {}).get('id')}: {len(c.get('diff', []))} setting(s) changed, "
                   f"{len(c.get('rules', {}).get('added', []))} rule(s) added")
    elif kind == "db.op":
        status = "ok"
        op, coll = f.get("op"), f.get("collection")
        ids = f.get("ids") or []
        if op == "insert":
            summary = f"insert {coll}: {', '.join(ids) or f.get('count', 0)}"
        elif op == "update":
            what = ", ".join(ids) if ids else "matched " + str(f.get("n"))
            summary = f"update {coll} {what}: set {', '.join(f.get('fields') or []) or '(replace)'}"
            if f.get("upserted"):
                summary += f" (upserted {', '.join(f['upserted'])})"
        elif op == "delete":
            summary = f"delete {coll}: {f.get('n')} removed"
        elif op == "vectorSearch":
            vs = f.get("vector_search") or {}
            summary = f"$vectorSearch {coll}.{vs.get('index')} (k={vs.get('k')}, candidates {vs.get('numCandidates')}): {f.get('count', 0)} hit(s)"
        elif op == "find":
            summary = f"find {coll}: {f.get('count', 0)} result(s)"
        elif op == "aggregate":
            summary = f"aggregate {coll} ({', '.join(f.get('stages') or [])}): {f.get('count', 0)} result(s)"
        elif op == "count":
            summary = f"count {coll}: {f.get('n')}"
        else:
            summary = f"{op} {coll}"
    elif kind == "db.failed":
        status, summary = "error", f"{f.get('op')} {f.get('collection')} failed: {f.get('error')}"
    elif kind == "checkpoint.saved":
        node, status = "memory", "ok"
        summary = f"Checkpoint saved after {f.get('after_node') or 'start'}: {f.get('total')} write(s) to working memory"
    elif kind == "reset.step":
        step = f.get("step")
        status = "ok"
        if step == "clear":
            summary = f"Cleared {f.get('collection')}: {f.get('deleted')} document(s) deleted, collection and indexes kept"
        elif step == "seed":
            summary = ("Reseeding: group, five past plans with embeddings, v1, first risk table" if f.get("state") == "start"
                       else f"Seeded {f.get('episodes')} episode(s), {f.get('versions')} version(s), {f.get('profiles')} risk profile(s)")
            status = "start" if f.get("state") == "start" else "ok"
        else:
            summary = f"Index: {f.get('message')}"
            if "waiting" in str(f.get("message")) or "still" in str(f.get("message")) or "unavailable" in str(f.get("message")):
                status = "warn"
    elif kind == "reset.done":
        status, summary = "ok", (f"Baseline restored: {f.get('episodes')} past plans, {f.get('versions')} policy version; "
                                 f"vector index {'ready' if f.get('episodes_index_ready') else 'not ready (recency fallback)'}")
    elif kind == "approval.requested":
        node, status = "tools", "warn"
        summary = f"Waiting for Alex: approve {f.get('tool') or 'this'}? {f.get('reason') or f.get('question')}"
    elif kind == "approval.resolved":
        node = "tools"
        status = "ok" if f.get("decision") == "approve" else "warn"
        summary = f"Alex {'approved' if f.get('decision') == 'approve' else 'declined'} {f.get('tool') or 'the request'}"
    elif kind == "beat.start":
        status, summary = "start", f"Beat {f.get('index', 0) + 1}: {(f.get('beat') or {}).get('title')}"
    elif kind == "beat.done":
        status = "warn" if f.get("warning") else "ok"
        summary = f"Beat finished: {(f.get('beat') or {}).get('title')}" + (f" — {f['warning']}" if f.get("warning") else "")
    elif kind == "beat.error":
        status, summary = "error", f"Beat failed at {f.get('stage') or 'unknown stage'}: {f.get('error')}. Reset to continue."
    elif kind == "beat.cancelled":
        status, summary = "warn", f"Beat cancelled by reset: {(f.get('beat') or {}).get('title')}"

    return {"node": node, "status": status, "summary": summary, "details": bounded(details),
            "plan_id": plan_id, "version_id": version_id}
