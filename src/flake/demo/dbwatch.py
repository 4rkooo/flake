"""Database activity for the viewer, taken from pymongo's command monitoring.

One global listener sees every command from every client in the process (the shared
client, the checkpointer, the notes store), so nothing in the lanes has to report its
own writes. Each successful CRUD command becomes one `db.op` observation carrying the
collection, the operation, the document ids touched and the result counts; a
$vectorSearch aggregate also carries the returned memories and their scores, and an
update carries the fields it changed. Writes are reported only from succeeded(), i.e.
after the server acknowledged them.

Reads made by the demo itself to build the state snapshot run under observe.quiet()
and are ignored. Checkpoint writes (two collections, several per node) are counted and
flushed as one `checkpoint.saved` observation per graph node.
"""

import threading
from collections import Counter

from pymongo import monitoring

from flake import observe

CRUD = {"find", "aggregate", "insert", "update", "delete", "findAndModify", "count", "distinct"}
CHECKPOINT_COLLECTIONS = {"checkpoints", "checkpoint_writes"}
MAX_IDS = 20


def _sid(value) -> str:
    return str(value)


def _changed_fields(update_doc) -> list[str]:
    # $set/$push/$inc/... -> the keys inside; a replacement document -> its top-level keys
    fields = set()
    if isinstance(update_doc, dict):
        for op, body in update_doc.items():
            if op.startswith("$") and isinstance(body, dict):
                fields.update(body.keys())
            elif not op.startswith("$"):
                fields.add(op)
    elif isinstance(update_doc, list):          # pipeline update
        for stage in update_doc:
            if isinstance(stage, dict):
                for body in stage.values():
                    if isinstance(body, dict):
                        fields.update(body.keys())
    return sorted(f for f in fields if f != "embedding") + (["embedding"] if "embedding" in fields else [])


def summarize_started(name: str, cmd: dict) -> dict | None:
    """What we keep from a started command. Never the documents themselves (they may hold
    embeddings and full prompts), only identifiers and shapes."""
    coll = cmd.get(name)
    if not isinstance(coll, str):
        return None                    # db-level aggregate etc.
    info = {"op": name, "collection": coll}
    if name == "insert":
        docs = cmd.get("documents") or []
        info["ids"] = [_sid(d.get("_id")) for d in docs if isinstance(d, dict)][:MAX_IDS]
        info["count"] = len(docs)
    elif name == "update":
        ups = cmd.get("updates") or []
        info["ids"] = [_sid(u["q"]["_id"]) for u in ups
                       if isinstance(u.get("q"), dict) and "_id" in u["q"]][:MAX_IDS]
        if ups and not info["ids"]:
            info["filter"] = ups[0].get("q")
        fields = set()
        for u in ups:
            fields.update(_changed_fields(u.get("u")))
        info["fields"] = sorted(fields)
        info["upsert"] = any(bool(u.get("upsert")) for u in ups)
        info["count"] = len(ups)
    elif name == "delete":
        dels = cmd.get("deletes") or []
        info["filters"] = [d.get("q") for d in dels][:5]
    elif name == "find":
        info["filter"] = cmd.get("filter")
        info["sort"] = cmd.get("sort")
        info["limit"] = cmd.get("limit")
        info["projection"] = cmd.get("projection")
    elif name == "aggregate":
        pipeline = cmd.get("pipeline") or []
        stages = [next(iter(st)) for st in pipeline if isinstance(st, dict) and st]
        info["stages"] = stages
        vs = next((st["$vectorSearch"] for st in pipeline if isinstance(st, dict) and "$vectorSearch" in st), None)
        if vs:
            info["op"] = "vectorSearch"
            info["vector_search"] = {"index": vs.get("index"), "path": vs.get("path"), "k": vs.get("limit"),
                                     "numCandidates": vs.get("numCandidates"), "filter": vs.get("filter")}
        elif stages[:2] == ["$match", "$group"] and len(pipeline) >= 2 and "n" in (pipeline[1].get("$group") or {}):
            info["op"] = "count"       # pymongo's count_documents is an aggregate underneath
            info["filter"] = pipeline[0].get("$match")
    elif name == "findAndModify":
        info["filter"] = cmd.get("query")
        info["fields"] = _changed_fields(cmd.get("update"))
    elif name in ("count", "distinct"):
        info["filter"] = cmd.get("query")
    return info


def summarize_reply(info: dict, reply: dict) -> dict:
    reply = reply or {}
    op = info["op"]
    if op in ("find", "aggregate", "vectorSearch") or (op == "count" and "cursor" in reply):
        batch = ((reply.get("cursor") or {}).get("firstBatch")) or []
        if op == "count":
            info["n"] = (batch[0].get("n") if batch and isinstance(batch[0], dict) else 0)
        else:
            info["count"] = len(batch)
            info["result_ids"] = [_sid(d.get("_id")) for d in batch if isinstance(d, dict)][:MAX_IDS]
            if op == "vectorSearch":
                info["results"] = [{"_id": _sid(d.get("_id")), "title": d.get("title"), "score": d.get("score")}
                                   for d in batch if isinstance(d, dict)][:10]
    elif op in ("insert", "update", "delete"):
        info["n"] = reply.get("n")
        if "nModified" in reply:
            info["n_modified"] = reply["nModified"]
        if reply.get("upserted"):
            info["upserted"] = [_sid(u.get("_id")) for u in reply["upserted"]]
    elif op == "count":
        info["n"] = reply.get("n")
    elif op == "findAndModify":
        info["n"] = 1 if reply.get("value") is not None else 0
    return info


class Watcher(monitoring.CommandListener):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started: dict[int, dict] = {}
        self._checkpoints: Counter = Counter()

    # -- pymongo callbacks (run on the thread that issued the command) --------------------
    def started(self, event) -> None:
        if event.command_name not in CRUD or observe.is_quiet():
            return
        try:
            info = summarize_started(event.command_name, event.command)
        except Exception:
            info = None
        if info is None:
            return
        info["database"] = event.database_name
        with self._lock:
            self._started[event.request_id] = info

    def succeeded(self, event) -> None:
        with self._lock:
            info = self._started.pop(event.request_id, None)
        if info is None:
            return
        try:
            summarize_reply(info, event.reply)
        except Exception:
            pass
        info["duration_ms"] = round(event.duration_micros / 1000, 1)
        if info["collection"] in CHECKPOINT_COLLECTIONS:
            with self._lock:
                self._checkpoints[(info["collection"], info["op"])] += 1
            return
        self._emit("db.op", **info)

    def failed(self, event) -> None:
        with self._lock:
            info = self._started.pop(event.request_id, None)
        if info is None:
            return
        info["error"] = str(event.failure)[:300]
        self._emit("db.failed", **info)

    # -- checkpoint aggregation -----------------------------------------------------------
    def flush_checkpoints(self, after: str | None) -> None:
        with self._lock:
            counts, self._checkpoints = self._checkpoints, Counter()
        if counts:
            self._emit("checkpoint.saved", after_node=after,
                       writes={f"{coll}.{op}": n for (coll, op), n in sorted(counts.items())},
                       total=sum(counts.values()))

    def _emit(self, kind: str, **fields) -> None:
        try:
            observe.emit(kind, **fields)
        except observe.Cancelled:
            pass        # a reset is in flight; the worker unwinds at its own next checkpoint


_installed: Watcher | None = None


def install() -> Watcher:
    """Register the global listener. Must run before the first MongoClient is created."""
    global _installed
    if _installed is None:
        _installed = Watcher()
        monitoring.register(_installed)
    return _installed


def watcher() -> Watcher | None:
    return _installed
