"""The pymongo listener, fed hand-made command events (mongomock has no monitoring)."""
import json
from types import SimpleNamespace as NS

import pytest

from flake import observe
from flake.demo import dbwatch


@pytest.fixture
def seen():
    got = []
    fn = lambda kind, fields: got.append((kind, fields))
    observe.subscribe(fn)
    yield got
    observe.unsubscribe(fn)


def started(w, rid, name, cmd):
    w.started(NS(command_name=name, request_id=rid, database_name="flake_demo", command=cmd))


def succeeded(w, rid, name, reply, micros=1000):
    w.succeeded(NS(command_name=name, request_id=rid, reply=reply, duration_micros=micros))


def test_crud_summaries_carry_ids_fields_counts_and_scores_but_no_vectors(seen):
    w = dbwatch.Watcher()
    started(w, 1, "insert", {"insert": "episodes", "documents": [{"_id": "ep_006", "embedding": [0.1] * 1536}]})
    succeeded(w, 1, "insert", {"n": 1, "ok": 1.0})
    started(w, 2, "update", {"update": "episodes", "updates": [
        {"q": {"_id": "ep_006"}, "u": {"$set": {"rsvps": []}, "$push": {"approvals": {"tool": "book"}}}, "upsert": False}]})
    succeeded(w, 2, "update", {"n": 1, "nModified": 1, "ok": 1.0})
    started(w, 3, "aggregate", {"aggregate": "episodes", "pipeline": [
        {"$vectorSearch": {"index": "episodes_vec", "path": "embedding", "queryVector": [0.0] * 1536, "limit": 3,
                           "numCandidates": 50, "filter": {"group_id": "taco-council"}}}, {"$project": {"title": 1}}]})
    succeeded(w, 3, "aggregate", {"cursor": {"firstBatch": [{"_id": "ep_003", "title": "Ski trip", "score": 0.91}]}, "ok": 1.0})
    started(w, 4, "find", {"find": "harness_versions", "filter": {"status": "active"}})
    succeeded(w, 4, "find", {"cursor": {"firstBatch": [{"_id": "taco-council:v1"}]}, "ok": 1.0})
    started(w, 5, "aggregate", {"aggregate": "episodes", "pipeline": [{"$match": {}}, {"$group": {"_id": 1, "n": {"$sum": 1}}}]})
    succeeded(w, 5, "aggregate", {"cursor": {"firstBatch": [{"_id": 1, "n": 6}]}, "ok": 1.0})

    assert [k for k, _ in seen] == ["db.op"] * 5
    ins, upd, vs, fnd, cnt = [f for _, f in seen]
    assert (ins["collection"], ins["ids"], ins["n"]) == ("episodes", ["ep_006"], 1) and "documents" not in ins
    assert upd["fields"] == ["approvals", "rsvps"] and upd["n_modified"] == 1 and upd["ids"] == ["ep_006"]
    assert vs["op"] == "vectorSearch" and vs["results"] == [{"_id": "ep_003", "title": "Ski trip", "score": 0.91}]
    assert vs["vector_search"]["k"] == 3 and "queryVector" not in json.dumps(vs)
    assert fnd["count"] == 1 and fnd["result_ids"] == ["taco-council:v1"]
    assert cnt["op"] == "count" and cnt["n"] == 6


def test_checkpoint_writes_are_counted_and_flushed_as_one_event(seen):
    w = dbwatch.Watcher()
    started(w, 1, "update", {"update": "checkpoints", "updates": [{"q": {"thread_id": "ep_006"}, "u": {"$set": {"x": 1}}, "upsert": True}]})
    succeeded(w, 1, "update", {"n": 1, "nModified": 0, "upserted": [{"index": 0, "_id": "abc"}]})
    started(w, 2, "update", {"update": "checkpoint_writes", "updates": [{"q": {}, "u": {"$set": {"y": 1}}}]})
    succeeded(w, 2, "update", {"n": 1, "nModified": 1})
    assert seen == []                                   # nothing yet: aggregated
    w.flush_checkpoints("agent")
    assert len(seen) == 1 and seen[0][0] == "checkpoint.saved"
    assert seen[0][1]["after_node"] == "agent" and seen[0][1]["total"] == 2
    w.flush_checkpoints("gate")                         # nothing pending: no event
    assert len(seen) == 1


def test_quiet_reads_and_failed_writes(seen):
    w = dbwatch.Watcher()
    with observe.quiet():
        started(w, 1, "find", {"find": "episodes", "filter": {}})
    succeeded(w, 1, "find", {"cursor": {"firstBatch": []}})
    assert seen == []                                   # the demo's own state reads are not activity
    started(w, 2, "insert", {"insert": "audit_log", "documents": [{"_id": "ad_001"}]})
    assert seen == []                                   # a write is reported only once the server acknowledged it
    w.failed(NS(command_name="insert", request_id=2, failure={"errmsg": "duplicate key"}, duration_micros=10))
    assert [k for k, _ in seen] == ["db.failed"] and "duplicate key" in seen[0][1]["error"]
