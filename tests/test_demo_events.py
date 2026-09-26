from flake.demo.events import bounded, translate


def test_gate_decisions_map_to_status_colours_and_keep_the_version():
    row = translate("gate.decision", {"plan_id": "ep_006", "version_id": "taco-council:v2", "tool": "book", "decision": "modify",
                                      "reason": "book_refundable_for applies to maya, sam", "rule_id": "r1",
                                      "requested_args": {"non_refundable_for": ["sam"]}, "final_args": {"non_refundable_for": []}})
    assert row["node"] == "gate" and row["status"] == "ok" and "MODIFY" in row["summary"] and "[r1]" in row["summary"]
    assert row["version_id"] == "taco-council:v2" and row["details"]["args_changed"] is True
    assert translate("gate.decision", {"decision": "ask", "tool": "book", "reason": "over cap"})["status"] == "warn"
    assert translate("gate.decision", {"decision": "deny", "tool": "book", "reason": "deposit first"})["status"] == "error"
    approved = translate("gate.decision", {"decision": "allow", "tool": "book", "reason": "spend $40 is over the $0 auto-spend cap"})
    assert approved["summary"].startswith("Gate ALLOW (approved by Alex): book")
    assert translate("gate.decision", {"decision": "allow", "tool": "book", "reason": "within policy"})["summary"] == "Gate ALLOW: book — within policy"


def test_model_turns_say_whether_they_were_replayed_or_paid_for():
    hit = translate("llm.turn", {"turn": 2, "cache": "hit", "tool_calls": [{"name": "book", "args": {}}]})
    miss = translate("llm.turn", {"turn": 2, "cache": "miss", "tool_calls": []})
    off = translate("llm.turn", {"turn": 1, "cache": "off", "tool_calls": []})
    assert "cached replay" in hit["summary"] and "requests book" in hit["summary"]
    assert "fresh API call" in miss["summary"] and "cache off" in off["summary"]


def test_retrieval_labels_vector_search_and_the_fallback():
    vec = translate("memory.similar", {"method": "vector_search", "k": 3, "hits": [{"title": "Ski trip", "score": 0.87}]})
    fb = translate("memory.similar", {"method": "recency_fallback", "k": 3, "error": "OperationFailure: no index", "hits": [{}, {}]})
    assert vec["status"] == "ok" and "$vectorSearch" in vec["summary"] and "Ski trip (0.87)" in vec["summary"]
    assert fb["status"] == "warn" and "fallback" in fb["summary"] and "no index" in fb["summary"]
    assert translate("proposal.fallback", {"error": "RuntimeError: network off"})["summary"].endswith("deterministic proposal fallback")


def test_details_are_bounded_and_never_carry_embeddings():
    big = {"embedding": [0.1] * 1536, "text": "x" * 5000, "items": list(range(100)), "nested": {"queryVector": [1], "ok": 1}}
    out = bounded(big)
    assert "embedding" not in out and "queryVector" not in out["nested"]
    assert len(out["text"]) < 900 and len(out["items"]) == 41 and out["items"][-1] == "... 60 more"


def test_db_rows_read_like_a_log_line():
    row = translate("db.op", {"op": "update", "collection": "episodes", "ids": ["ep_006"], "fields": ["booking"], "n": 1})
    assert row["summary"] == "update episodes ep_006: set booking" and row["node"] is None
    row = translate("db.op", {"op": "vectorSearch", "collection": "episodes", "vector_search": {"index": "episodes_vec", "k": 3, "numCandidates": 50}, "count": 3})
    assert row["summary"].startswith("$vectorSearch episodes.episodes_vec (k=3") and "3 hit(s)" in row["summary"]
