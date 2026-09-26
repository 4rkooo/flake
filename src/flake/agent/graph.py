"""
flake/agent/graph.py  (Lane A)

The inner loop: one plan, from Alex's sentence to a booked episode.

The gate sits between what the model *asks* for and what the tools *run*.
There is no path from the model to the world that skips it.
"""

import os
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.mongodb import MongoDBSaver

from flake.config import client, llm            # shared Mongo client + chat model
from flake import memory, observe                # episodes, groups, plan ids, current_run; observation hooks
from flake.agent import context, prompts         # context loader + system-prompt renderer
from flake.agent.tools import TOOLS              # the agent's real tools (propose, poll, book, ...)
from flake.harness import audit, gate as gatemod, versions   # Lane C: audit log, policy gate, versions

# Runaway guard: stop after this many model calls, even if it still wants tools.
MAX_TURNS = 10


# ---------------------------------------------------------------------------
# State: the working memory of one plan run.
# Each node returns only the keys it changed; LangGraph merges them in.
# ---------------------------------------------------------------------------
class PlanState(TypedDict):
    # add_messages = APPEND new messages, except a message whose id matches an
    # existing one REPLACES it. The gate relies on that replace behaviour.
    messages: Annotated[list, add_messages]
    group_id: str      # which friend group
    plan_id: str       # also the checkpointer thread_id
    plan_brief: str    # Alex's sentence, e.g. "Taco Tuesday, ~$25 each"
    version: dict      # the policy version in force for this run (canary or active)
    context: dict      # what load_context built: risk table, similar plans, notes
    turns: int         # how many times the model has been called


# ---------------------------------------------------------------------------
# A tool the MODEL never sees (it isn't in bind_tools below).
# The gate substitutes it for any denied call, so the model gets a clear
# "DENIED" result instead of the action happening.
# ---------------------------------------------------------------------------
@tool
def policy_notice(reason: str) -> str:
    """Internal. Returns the reason a call was denied by policy."""
    return f"DENIED by policy: {reason}"


# The model is told about the real tools only.
model = llm.bind_tools(TOOLS)


# ---------------------------------------------------------------------------
# Node 1: load_context (runs once at the start)
# ---------------------------------------------------------------------------
def load_context(state: PlanState):
    observe.emit("node.start", node="load_context", plan_id=state["plan_id"])

    # Policy in force: the canary if one is running, else the active version.
    version = versions.get_effective(state["group_id"])
    # The demo lights up policy -> gate here: every decision below cites this version.
    observe.emit("policy.loaded", plan_id=state["plan_id"], version_id=version["_id"],
                 status=version["status"], policy=version["policy"])
    group = memory.get_group(state["group_id"])

    # Risk table, similar past plans (vector search), notes about the friends.
    # How much gets loaded is itself part of the policy (context_policy).
    ctx = context.build(state["group_id"], state["plan_brief"], version["policy"]["context_policy"])
    observe.emit("context.built", plan_id=state["plan_id"], version_id=version["_id"], risk=ctx["risk"],
                 similar=[{k: e.get(k) for k in ("_id", "title", "summary", "score")} for e in ctx["similar"]],
                 notes=ctx["notes"], context_policy=version["policy"]["context_policy"])

    # Turn group + brief + policy + context into the system prompt.
    system = prompts.render(group, state["plan_brief"], version, ctx)

    observe.emit("node.end", node="load_context", plan_id=state["plan_id"])
    # Save version/context in state so the gate can use them on every pass,
    # reset the turn counter, and seed the conversation.
    return {"version": version, "context": ctx, "turns": 0,
            "messages": [SystemMessage(system), HumanMessage(f"Plan this: {state['plan_brief']}")]}


# ---------------------------------------------------------------------------
# Node 2: agent (one LLM call per visit)
# ---------------------------------------------------------------------------
def agent(state: PlanState):
    turn = state["turns"] + 1
    observe.emit("node.start", node="agent", plan_id=state["plan_id"], turn=turn)

    # The model only DECIDES; its reply usually contains tool_calls.
    # Nothing is executed here.
    reply = model.invoke(state["messages"])

    # llmcache leaves "hit"/"miss" on this thread; no cache installed reads as "off".
    observe.emit("llm.turn", plan_id=state["plan_id"], version_id=state["version"]["_id"], turn=turn,
                 cache=observe.take("llm_cache", "off"),
                 tool_calls=[{"name": c["name"], "args": c["args"]} for c in (getattr(reply, "tool_calls", None) or [])],
                 content=reply.content if isinstance(reply.content, str) else str(reply.content))
    observe.emit("node.end", node="agent", plan_id=state["plan_id"])
    return {"messages": [reply], "turns": turn}


# ---------------------------------------------------------------------------
# Node 3: gate (the policy enforcement point, Lane C's logic)
# ---------------------------------------------------------------------------
def gate(state: PlanState):
    observe.emit("node.start", node="gate", plan_id=state["plan_id"])
    last = state["messages"][-1]   # the model's reply with its requested tool calls

    # Approvals Alex has already given on this plan (written by ask_organizer).
    # Re-read every pass so a retried call can be allowed after Alex says yes.
    # `or {}`: on the first pass the model is calling propose_plan, so the episode doesn't exist yet
    approvals = (memory.get_episode(state["plan_id"]) or {}).get("approvals", [])

    rewritten = []
    for call in last.tool_calls:
        # Check the call against rules, guardrails and tool permissions,
        # using the current risk numbers and existing approvals.
        decision = gatemod.check(call["name"], call["args"], state["version"]["policy"],
                                 state["context"]["risk"], approvals)

        # Every decision is audited, including allows.
        audit_id = audit.log(state["plan_id"], state["version"]["_id"], call, decision)
        observe.emit("gate.decision", plan_id=state["plan_id"], version_id=state["version"]["_id"],
                     audit_id=audit_id, call_id=call["id"], tool=call["name"], requested_args=call["args"],
                     decision=decision.action, final_args=decision.final_args, reason=decision.reason,
                     rule_id=decision.rule_id)

        if decision.action in ("allow", "modify"):
            # Same tool, but with the gate's final args
            # (e.g. non-refundable -> refundable for sam, maya).
            rewritten.append({**call, "args": decision.final_args})
        elif decision.action == "ask":
            # Don't run it; ask Alex instead. approve_tool tells ask_organizer
            # which tool the approval is for. Same call id so results line up.
            rewritten.append({"id": call["id"], "name": "ask_organizer",
                              "args": {"question": decision.reason, "approve_tool": call["name"]}})
        else:
            # deny: swap in policy_notice so the model learns why.
            # Keeping call["id"] is required: every ToolMessage must match a tool_call_id.
            rewritten.append({"id": call["id"], "name": "policy_notice", "args": {"reason": decision.reason}})

    observe.emit("node.end", node="gate", plan_id=state["plan_id"])
    # Same id as the model's message -> add_messages REPLACES it in history.
    # The tools node therefore only ever sees the gated calls.
    return {"messages": [AIMessage(content=last.content, tool_calls=rewritten, id=last.id)]}


# ---------------------------------------------------------------------------
# Node 4: tools. ToolNode runs whatever calls are on the last message.
# It must know policy_notice (for denies) and ask_organizer (must be in TOOLS).
# The wrapper only reports each call and its result; the ToolNode is unchanged.
# ---------------------------------------------------------------------------
tool_node = ToolNode(TOOLS + [policy_notice])


def tools(state: PlanState, config):
    calls = state["messages"][-1].tool_calls
    observe.emit("node.start", node="tools", plan_id=state["plan_id"],
                 calls=[{"name": c["name"], "args": c["args"]} for c in calls])
    out = tool_node.invoke(state, config)
    by_id = {m.tool_call_id: m for m in out["messages"]}
    for call in calls:
        msg = by_id.get(call["id"])
        observe.emit("tool.result", plan_id=state["plan_id"], version_id=state["version"]["_id"],
                     call_id=call["id"], name=call["name"], args=call["args"],
                     result=msg.content if msg is not None else None,
                     status=getattr(msg, "status", "success") if msg is not None else "missing")
    observe.emit("node.end", node="tools", plan_id=state["plan_id"])
    return out


# ---------------------------------------------------------------------------
# Node 5: record_episode (runs once at the end)
# ---------------------------------------------------------------------------
def record_episode(state: PlanState):
    observe.emit("node.start", node="record_episode", plan_id=state["plan_id"])
    # Stamp which policy version ran this plan: the Retro and the canary
    # promotion check both need it.
    ep = memory.get_episode(state["plan_id"]) or {}
    fields = {"version_id": state["version"]["_id"], "turns": state["turns"]}
    if ep.get("booking"):
        fields["status"], fields["incomplete_reason"] = "booked", None
    else:
        # Honest bookkeeping: a run that hit MAX_TURNS or stopped without a receipt must
        # not look booked (tick would resolve a plan nobody booked), even if finish_plan
        # was called. It stays "proposed" with the reason attached.
        fields["status"] = "proposed"
        fields["incomplete_reason"] = ("hit the turn limit before booking" if state["turns"] >= MAX_TURNS
                                       else "the agent stopped without booking")
    memory.update_episode(state["plan_id"], fields)   # no-op if propose_plan never ran
    observe.emit("plan.recorded", plan_id=state["plan_id"], version_id=state["version"]["_id"],
                 status=fields["status"], incomplete_reason=fields["incomplete_reason"],
                 turns=state["turns"], booking=ep.get("booking"))
    observe.emit("node.end", node="record_episode", plan_id=state["plan_id"])
    return {}


# ---------------------------------------------------------------------------
# Router after the agent node
# ---------------------------------------------------------------------------
def route_after_agent(state: PlanState):
    last = state["messages"][-1]
    # Done if the model asked for no tools, or the turn cap is hit.
    if not getattr(last, "tool_calls", None) or state["turns"] >= MAX_TURNS:
        return "record_episode"
    # Otherwise every tool request goes through the gate first.
    return "gate"


# ---------------------------------------------------------------------------
# Wire the graph
# ---------------------------------------------------------------------------
builder = StateGraph(PlanState)
builder.add_node("load_context", load_context)
builder.add_node("agent", agent)
builder.add_node("gate", gate)
builder.add_node("tools", tools)
builder.add_node("record_episode", record_episode)

builder.add_edge(START, "load_context")
builder.add_edge("load_context", "agent")
builder.add_conditional_edges("agent", route_after_agent, {"gate": "gate", "record_episode": "record_episode"})
builder.add_edge("gate", "tools")    # gate -> tools is the ONLY way into tools
builder.add_edge("tools", "agent")   # results go back to the model: the loop
builder.add_edge("record_episode", END)

# Working memory in Atlas: full state saved after every node, keyed by thread_id.
# Lets a run be paused, resumed or replayed.
checkpointer = MongoDBSaver(client, db_name=os.environ.get("MONGODB_DB", "flake"))
graph = builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Entry point used by the CLI: `flake plan "..."`
# ---------------------------------------------------------------------------
def run_plan(group_id: str, plan_brief: str) -> dict:
    plan_id = memory.next_plan_id()

    # Global the tools read to know which group/plan they act on.
    # Fine for a single-process CLI; not safe for concurrent plans.
    memory.current_run.update(group_id=group_id, plan_id=plan_id)
    observe.emit("plan.start", plan_id=plan_id, group_id=group_id, brief=plan_brief)

    # One checkpoint thread per plan.
    config = {"configurable": {"thread_id": plan_id}}
    final = graph.invoke({"group_id": group_id, "plan_id": plan_id, "plan_brief": plan_brief, "messages": []}, config)

    # Return the finished episode document (RSVPs, booking, approvals, version_id, ...).
    ep = memory.get_episode(plan_id)
    if ep is None:
        # The model never called propose_plan, so there is no episode: report that instead
        # of crashing, and still say which policy version was in force.
        version = (final or {}).get("version") or {}
        ep = {"_id": plan_id, "group_id": group_id, "status": "proposed", "version_id": version.get("_id"),
              "turns": (final or {}).get("turns", 0), "incomplete_reason": "the agent never proposed a plan"}
    observe.emit("plan.end", plan_id=plan_id, version_id=ep.get("version_id"), status=ep.get("status"),
                 incomplete_reason=ep.get("incomplete_reason"), booking=ep.get("booking"), turns=ep.get("turns"))
    return ep
