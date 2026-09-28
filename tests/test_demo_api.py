import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from flake import memory
from flake.config import db
from flake.demo import fake_llm, reset as reset_mod
from flake.demo.api import create_app
from flake.demo.coordinator import Coordinator


@pytest.fixture
def coord(monkeypatch):
    from flake.agent import graph, tools, underwriter_llm

    model = fake_llm.ScriptedChatModel()
    monkeypatch.setattr(graph, "model", model.bind_tools(tools.TOOLS))
    monkeypatch.setattr(underwriter_llm, "llm", model)
    for name in db.list_collection_names():
        db[name].drop()
    memory.store.clear()
    c = Coordinator(reset_index_timeout=0)
    yield c
    c.close()


@pytest.fixture
def client(coord):
    return TestClient(create_app(coord, ui_dir=Path("/nonexistent")))


def wait_idle(coord, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline and coord.busy():
        time.sleep(0.02)
    assert not coord.busy()


def sse(client, **params):
    """Read the once-mode stream: [(event, data), ...]"""
    out, event = [], None
    headers = params.pop("headers", None)
    with client.stream("GET", "/api/events", params={"once": "true", **params}, headers=headers) as resp:
        assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/event-stream")
        for line in resp.iter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                out.append((event, json.loads(line.split(":", 1)[1])))
    return out


def test_state_before_any_beat_asks_for_a_reset(client):
    s = client.get("/api/state").json()
    assert s["needs_reset"] is True and s["beat"]["index"] == -1 and s["pending_approvals"] == []
    assert [b["id"] for b in s["beats"]][:2] == ["reset", "taco"] and s["events"] == [] and s["next_title"] == "Reset / baseline"


def test_next_runs_the_baseline_and_refuses_while_busy(client, coord, monkeypatch):
    real = reset_mod.run
    monkeypatch.setattr(reset_mod, "run", lambda **kw: (time.sleep(0.4), real(**kw))[1])
    r = client.post("/api/next")
    assert r.status_code == 200 and r.json()["index"] == 0 and r.json()["status"] == "running"
    assert client.post("/api/next").status_code == 409
    wait_idle(coord)
    s = client.get("/api/state").json()
    assert s["needs_reset"] is False and s["beat"]["status"] == "done" and s["next_title"] == "Taco Tuesday"
    assert s["policy"]["active"]["_id"] == "taco-council:v1" and len(s["episodes"]) == 5 and len(s["risk_profiles"]) == 4


def test_unknown_or_malformed_approvals(client):
    assert client.post("/api/approvals/ap_999", json={"decision": "approve"}).status_code == 404
    assert client.post("/api/approvals/ap_999", json={"decision": "maybe"}).status_code == 422


def test_approvals_over_http_unblock_the_plan(client, coord):
    client.post("/api/next")
    wait_idle(coord)
    client.post("/api/next")
    deadline = time.time() + 30
    while time.time() < deadline and not coord.pending_approvals():
        time.sleep(0.02)
    s = client.get("/api/state").json()
    assert len(s["pending_approvals"]) == 1 and s["pending_approvals"][0]["tool"] == "book" and s["next_available"] is False
    ap = s["pending_approvals"][0]["id"]
    assert client.post(f"/api/approvals/{ap}", json={"decision": "approve"}).json()["status"] == "accepted"
    assert client.post(f"/api/approvals/{ap}", json={"decision": "approve"}).json()["status"] == "already_answered"
    while coord.busy():
        for a in coord.pending_approvals():
            client.post(f"/api/approvals/{a['id']}", json={"decision": "approve"})
        time.sleep(0.02)
    assert memory.get_episode("ep_006")["booking"]


def test_event_stream_replays_and_resumes_within_a_session(client, coord):
    client.post("/api/next")
    wait_idle(coord)
    rows = sse(client)
    assert rows[0][0] == "hello" and rows[0][1]["session"] == coord.journal.session
    flake = [d for e, d in rows if e == "flake"]
    assert [d["seq"] for d in flake] == list(range(1, len(flake) + 1)) and flake[0]["kind"] == "beat.start"
    assert len(flake) == coord.journal.cursor()
    # a reload resumes from its cursor within the same session ...
    resumed = [d for e, d in sse(client, since=3, session=coord.journal.session) if e == "flake"]
    assert resumed[0]["seq"] == 4
    # ... via the browser's Last-Event-ID as well ...
    resumed = [d for e, d in sse(client, headers={"Last-Event-ID": f"{coord.journal.session}:5"}) if e == "flake"]
    assert resumed[0]["seq"] == 6
    # ... but a cursor from another session replays everything
    assert [d for e, d in sse(client, since=3, session="stale") if e == "flake"][0]["seq"] == 1


def test_reset_over_http_returns_a_new_session(client, coord):
    client.post("/api/next")
    wait_idle(coord)
    before = client.get("/api/state").json()["session"]
    r = client.post("/api/reset")
    assert r.status_code == 200 and r.json()["session"] != before
    wait_idle(coord)
    s = client.get("/api/state").json()
    assert s["session"] == r.json()["session"] and s["beat"]["index"] == 0 and all(e["session"] == s["session"] for e in s["events"])


def test_pace_is_adjustable_and_bounded(client, coord):
    assert client.get("/api/state").json()["pace"] == 0
    assert client.post("/api/pace", json={"factor": 1.5}).json() == {"pace": 1.5}
    assert client.get("/api/state").json()["pace"] == 1.5
    assert client.post("/api/pace", json={"factor": 9}).status_code == 422
    assert client.post("/api/pace", json={"factor": -1}).status_code == 422
    assert coord.pace == 1.5
