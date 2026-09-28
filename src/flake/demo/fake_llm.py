"""A scripted stand-in for the chat model.

Used by `flake-demo --fake` (offline rehearsal) and by the tests that drive the whole
script through the real gate, risk, backtest and canary code. It plays a plausible but
naive agent: propose, poll, book everyone non-refundable, then do exactly what the gate's
replies say (request deposits, retry after Alex answers), request money, finish."""

import ast
import json
import re
from datetime import date, timedelta

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from flake import observe

KINDS = ("dinner", "karaoke", "trip", "brunch", "tickets")
WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
DEPOSIT_CALL = re.compile(r'request_money\(plan_id="([^"]+)", person="([^"]+)", amount_usd=(\d+), upfront=True\)')


def parse_brief(brief: str, today: date | None = None) -> dict:
    """'Taco Tuesday: dinner next Tuesday, about $25 each, at least 3 people' -> propose_plan args."""
    today = today or date.today()
    low = brief.lower()
    title = brief.split(":")[0].strip() if ":" in brief else brief.strip()[:40]
    kind = next((k for k in KINDS if k in low), "dinner")
    m = re.search(r"\$\s?(\d+)", brief)
    cost = int(m.group(1)) if m else 25
    m = re.search(r"(?:at least|min(?:imum)?)\s+(\d+)", low)
    min_people = int(m.group(1)) if m else 3
    weekday = next((WEEKDAYS[w] for w in WEEKDAYS if w in low), None)
    weeks = 2 if "two weeks" in low else 1
    if weekday is None:
        day = today + timedelta(days=7 * weeks)
    else:
        ahead = (weekday - today.weekday()) % 7 or 7          # strictly after today
        day = today + timedelta(days=ahead + 7 * (weeks - 1))
    return {"title": title, "kind": kind, "day": day.isoformat(), "cost_per_person_usd": cost, "min_people": min_people}


def parse_ask(question: str) -> tuple[str | None, dict]:
    m = re.match(r"^Approve (\w+) (\{.*\})\? Reason: ", question or "", re.S)
    if not m:
        return None, {}
    try:
        args = ast.literal_eval(m.group(2))
    except (ValueError, SyntaxError):
        args = {}
    return m.group(1), args if isinstance(args, dict) else {}


def _content(msg) -> str:
    c = msg.content
    return c if isinstance(c, str) else json.dumps(c)


class _Wordsmith:
    """with_structured_output(...) stand-in: returns the wording schema filled in. No reasons,
    so the underwriter keeps the pricing model's own numbers-quoting reasons."""

    def __init__(self, schema):
        self.schema = schema

    def invoke(self, prompt, **_):
        observe.note("llm_cache", "scripted")
        return self.schema(rationale="Scripted rationale (offline rehearsal): the rules and caps come from the pricing "
                                     "model's risk table, not from a language model.", reasons=[])


class ScriptedChatModel:
    def __init__(self) -> None:
        self.calls = 0
        self._ids = 0

    # -- the two entry points the code base uses --------------------------------------------
    def bind_tools(self, tools, **_):
        return self

    def with_structured_output(self, schema, **_):
        return _Wordsmith(schema)

    def invoke(self, messages, config=None, **_):
        observe.note("llm_cache", "scripted")
        self.calls += 1
        calls = self._decide(list(messages))
        if not calls:
            return AIMessage(content="Done.")
        return AIMessage(content="", tool_calls=calls)

    # -- the script -------------------------------------------------------------------------
    def _call(self, name: str, args: dict) -> dict:
        self._ids += 1
        return {"name": name, "args": args, "id": f"scripted_{self._ids}", "type": "tool_call"}

    def _decide(self, messages) -> list[dict]:
        brief = next((_content(m).removeprefix("Plan this: ") for m in messages if isinstance(m, HumanMessage)), "")
        planned = parse_brief(brief)
        ai = [m for m in messages if isinstance(m, AIMessage)]
        results = {m.tool_call_id: m for m in messages if isinstance(m, ToolMessage)}
        history = [(c["name"], c["args"], results.get(c["id"])) for m in ai for c in (m.tool_calls or [])]

        def ok(name):
            return [(a, r) for n, a, r in history if n == name and r is not None and getattr(r, "status", "success") != "error"]

        if ok("finish_plan"):
            return []                                   # said goodbye already: no more tool calls ends the run
        plan_ids = [_content(r) for _, r in ok("propose_plan")]
        if not plan_ids:
            return [self._call("propose_plan", planned)]
        plan_id = plan_ids[0]
        title = planned["title"]

        polls = ok("poll_rsvps")
        if not polls:
            return [self._call("poll_rsvps", {"plan_id": plan_id})]
        try:
            rsvps = json.loads(_content(polls[-1][1]))
        except ValueError:
            rsvps = []
        yes = [r["person"] for r in rsvps if isinstance(r, dict) and r.get("rsvp") == "yes"]
        cost = planned["cost_per_person_usd"]

        last_round = [(c["name"], c["args"], results.get(c["id"])) for c in (ai[-1].tool_calls or [])] if ai else []
        answers = [(a, r) for n, a, r in history if n == "ask_organizer" and r is not None]
        declined = set()
        for a, r in answers:
            tool, asked = parse_ask(a.get("question", ""))
            if (a.get("approve_tool") or tool) == "request_money" and not _content(r).lower().startswith("y"):
                declined.add(asked.get("person"))

        booked = [(a, r) for a, r in ok("book") if "deposit_usd" in _content(r)]
        intended_book = {"plan_id": plan_id, "non_refundable_for": yes, "refundable_for": []}

        if not booked:
            for name, args, r in last_round:
                if r is None:
                    continue
                if name == "policy_notice":
                    deposits = [{"plan_id": p, "person": who, "amount_usd": int(amt), "upfront": True}
                                for p, who, amt in DEPOSIT_CALL.findall(_content(r))]
                    if deposits:
                        return [self._call("request_money", d) for d in deposits]
                if name == "ask_organizer":
                    tool, asked = parse_ask(args.get("question", ""))
                    tool = args.get("approve_tool") or tool
                    if _content(r).lower().startswith("y"):
                        if tool == "request_money" and asked:
                            return [self._call("request_money", asked)]
                        return [self._call("book", intended_book)]
                    what = "the deposit request" if tool == "request_money" else "the booking"
                    return [self._call("finish_plan", {"plan_id": plan_id,
                                                       "summary": f"{title}: Alex declined {what}, so nothing was booked."})]
            return [self._call("book", intended_book)]

        requested = {a.get("person") for a, _ in ok("request_money")}
        remaining = [p for p in yes if p not in requested and p not in declined]
        if remaining:
            attempted = any((n == "request_money" and not a.get("upfront")) or
                            (n == "ask_organizer" and (a.get("approve_tool") or parse_ask(a.get("question", ""))[0]) == "request_money")
                            for n, a, _ in history)
            people = remaining if attempted else remaining[:1]    # one first; after Alex's answer, the rest at once
            return [self._call("request_money", {"plan_id": plan_id, "person": p, "amount_usd": cost, "upfront": False})
                    for p in people]

        receipt = json.loads(_content(booked[-1][1]))
        summary = (f"{title}: booked non-refundable for {', '.join(receipt.get('non_refundable_for', []))} and refundable for "
                   f"{', '.join(receipt.get('refundable_for', [])) or 'nobody'}, {len(yes)} yes RSVPs; money requested from everyone who said yes.")
        return [self._call("finish_plan", {"plan_id": plan_id, "summary": summary})]
