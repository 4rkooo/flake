"""
flake/memory.py  (Lane A)

The memory layer: every read/write of plan data goes through here, so the
rest of the code never touches Mongo collections directly.

Collections used:
  groups    - a friend group (members, organizer). Written by the seed script.
  episodes  - EPISODIC memory: one document per plan, proposal -> outcome,
              plus an embedding of its summary for vector search.
  chat_log  - every message Flake or a friend "sends" in the group chat.

(Working memory = LangGraph checkpoints; procedural memory = harness_versions;
 semantic memory = notes. Those live elsewhere.)
"""

from datetime import datetime, timezone
from flake.config import db, embed   # db = Mongo database handle; embed(text) -> list[float]
import os
from langgraph.store.mongodb import MongoDBStore, create_vector_index_config
from flake.config import embedder

# The plan in progress. run_plan() fills this in before invoking the graph, so
# tools (which only receive the model's args) know which group/plan they act on.
# A module-level global: fine for a one-plan-at-a-time CLI, not for concurrent runs.
current_run: dict = {}          # group_id, plan_id for the run in progress; set by run_plan


index_config = create_vector_index_config(embed=embedder, dims=int(os.environ.get("EMBEDDING_DIMS", "1536")), fields=["text"])
store = MongoDBStore.from_conn_string(os.environ["MONGODB_URI"], db_name=os.environ.get("MONGODB_DB", "flake"),
                                      collection_name="notes", index_config=index_config).__enter__()


def now() -> str:
    # UTC ISO-8601 string. Strings in this format sort correctly as text,
    # which is what the .sort("created_at") calls below rely on.
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------
def get_group(group_id: str) -> dict:
    # The group doc: members + organizer. Used to render the system prompt.
    return db.groups.find_one({"_id": group_id})


# ---------------------------------------------------------------------------
# Episodes: one document per plan
# ---------------------------------------------------------------------------
def next_plan_id() -> str:
    # Sequential, human-readable ids: ep_001, ep_002, ...
    # Counts ALL episodes (every group), so ids are global.
    # NOTE: only safe with one writer; and if an id is taken but its episode never
    # gets created (agent never calls propose_plan), the next run reuses that id.
    n = db.episodes.count_documents({}) + 1
    return f"ep_{n:03d}"


def create_episode(**fields) -> str:
    # Called by the propose_plan tool. Uses current_run for the id and group,
    # starts status at "proposed", and pre-creates the arrays that later
    # $push calls append to. **fields (title, date, cost, invitees...) come
    # from the tool and can override the defaults.
    doc = {"_id": current_run["plan_id"], "group_id": current_run["group_id"], "status": "proposed",
           "rsvps": [], "money_requests": [], "approvals": [], "created_at": now(), **fields}
    db.episodes.insert_one(doc)   # raises DuplicateKeyError if propose_plan is called twice
    return doc["_id"]


def get_episode(plan_id: str) -> dict:
    # Returns None if the episode doesn't exist yet. Callers must handle that:
    # the gate runs BEFORE the first propose_plan call executes, so on the very
    # first gate pass there is no episode. Use (get_episode(id) or {}).get(...).
    return db.episodes.find_one({"_id": plan_id})


def update_episode(plan_id: str, fields: dict) -> None:
    # Partial update: $set only touches the given fields, leaving the rest.
    # Silently does nothing if the episode doesn't exist.
    db.episodes.update_one({"_id": plan_id}, {"$set": fields})


def add_money_request(plan_id: str, person: str, amount_usd: int, upfront: bool) -> str:
    # Called by the request_money tool. Appends to the episode's money_requests.
    # upfront=True means a deposit collected BEFORE booking (e.g. Jordan under v2).
    # NOTE: id is per person per plan, so a second request to the same person
    # gets the same id.
    req = {"id": f"mr_{person}_{plan_id}", "person": person, "amount_usd": amount_usd, "upfront": upfront, "at": now()}
    db.episodes.update_one({"_id": plan_id}, {"$push": {"money_requests": req}})
    return req["id"]


def add_approval(plan_id: str, tool: str) -> None:
    # Called by ask_organizer when Alex says yes. The gate reads this list and
    # allows the next call to `tool`.
    # NOTE: approval is by tool NAME only, not args: approving one book() call
    # approves any later book() call on this plan, whatever the amount.
    db.episodes.update_one({"_id": plan_id}, {"$push": {"approvals": {"tool": tool, "at": now()}}})


def finish_episode(plan_id: str, summary: str) -> None:
    # Called by the finish_plan tool. Stores a one-paragraph summary AND its
    # embedding; that embedding is what similar_episodes() searches on for
    # future plans. Marks the plan booked (world.tick later sets "resolved").
    update_episode(plan_id, {"summary": summary, "embedding": embed(summary), "status": "booked"})


# ---------------------------------------------------------------------------
# Group chat
# ---------------------------------------------------------------------------
def chat(sender: str, text: str) -> None:
    # Append one chat line, tagged with the current group/plan.
    # .get() so it also works outside a run (e.g. seed script), storing None.
    db.chat_log.insert_one({"group_id": current_run.get("group_id"), "plan_id": current_run.get("plan_id"),
                            "sender": sender, "text": text, "at": now()})


# ---------------------------------------------------------------------------
# Reads for the Retro and the context loader
# ---------------------------------------------------------------------------
def resolved_episodes(group_id: str) -> list[dict]:
    # Every plan whose outcomes have landed (status set to "resolved" by
    # world.tick), oldest first. This is the Retro's dataset: the risk table
    # and the backtest both replay these in order.
    return list(db.episodes.find({"group_id": group_id, "status": "resolved"}).sort("resolved_at", 1))


def similar_episodes(group_id: str, brief: str, k: int) -> list[dict]:
    # The k past plans most similar in MEANING to the new brief, for the
    # system prompt ("last beach trip Sam bailed..."). k comes from the
    # policy's context_policy, so the Retro can tune it.
    pipeline = [
        # Atlas Vector Search: embed the brief, compare against stored summary
        # embeddings. numCandidates = how many to consider approximately,
        # limit = how many to return. The filter keeps it to this group;
        # group_id must be declared as a "filter" field in the episodes_vec index.
        {"$vectorSearch": {"index": "episodes_vec", "path": "embedding", "queryVector": embed(brief),
                           "numCandidates": 50, "limit": k, "filter": {"group_id": group_id}}},
        # Return only what the prompt needs, plus the similarity score.
        {"$project": {"title": 1, "summary": 1, "outcomes": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]
    try:
        hits = list(db.episodes.aggregate(pipeline))
    except Exception:
        hits = []                      # index not built yet: fall back to recency
    if not hits:
        # Fallback: the k most recent finished plans in this group.
        # NOTE: no projection here, so these docs include the full embedding
        # array; add a projection matching the one above before rendering.
        hits = list(db.episodes.find({"group_id": group_id, "summary": {"$exists": True}})
                    .sort("created_at", -1).limit(k))
    return hits

def add_note(group_id: str, key: str, text: str) -> None:
    store.put(("flake", group_id), key, {"text": text})

def search_notes(group_id: str, query: str, limit: int) -> list[str]:
    try:
        return [item.value["text"] for item in store.search(("flake", group_id), query=query, limit=limit)]
    except Exception:
        return []