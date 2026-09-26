"""HTTP surface for the browser: state snapshot, event stream (SSE), presenter controls,
and the built UI as static files."""

import asyncio
from collections.abc import AsyncIterable
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from flake.demo.beats import BEATS
from flake.demo.coordinator import Blocked, Busy, Coordinator, ResetTimeout

REPO = Path(__file__).resolve().parents[3]
POLL_S = 0.15


class Answer(BaseModel):
    decision: Literal["approve", "decline"]


class Pace(BaseModel):
    factor: float


def _cursor_from(last_event_id: str | None, session: str | None, since: int, current_session: str) -> int:
    """Resume only within the same session; anything else replays from the start."""
    if last_event_id and ":" in last_event_id:
        sess, seq = last_event_id.rsplit(":", 1)
        if sess == current_session and seq.isdigit():
            return int(seq)
        return 0
    if session == current_session:
        return max(0, since)
    return 0


def create_app(coord: Coordinator, ui_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="Flake demo", version="0.1.0")

    @app.get("/api/state")
    def state():
        return coord.state()

    @app.get("/api/beats")
    def beats():
        return {"beats": BEATS}

    @app.get("/api/events", response_class=EventSourceResponse)
    async def events(since: int = 0, session: str | None = None, once: bool = False,
                     last_event_id: Annotated[str | None, Header()] = None) -> AsyncIterable[ServerSentEvent]:
        """The live stream. `since`+`session` (or the Last-Event-ID header, "session:seq") resume a
        reload within the same session; anything else replays from the start. once=true replays
        what is there and closes (for curl and tests)."""
        journal = coord.journal
        seen = journal.session
        cursor = _cursor_from(last_event_id, session, since, seen)
        yield ServerSentEvent(event="hello", data={"session": seen, "cursor": cursor}, id=f"{seen}:{cursor}")
        while True:
            if journal.session != seen:            # a reset happened: start the new session from 0
                seen, cursor = journal.session, 0
                yield ServerSentEvent(event="hello", data={"session": seen, "cursor": 0}, id=f"{seen}:0")
            for ev in journal.since(cursor):
                cursor = ev.seq
                yield ServerSentEvent(event="flake", data=ev.to_dict(), id=f"{ev.session}:{ev.seq}")
            if once:
                return
            await asyncio.sleep(POLL_S)

    @app.post("/api/next")
    def next_beat():
        try:
            return coord.next_beat()
        except (Busy, Blocked) as e:
            raise HTTPException(status_code=409, detail=str(e))
        except ResetTimeout as e:
            raise HTTPException(status_code=503, detail=str(e))

    @app.post("/api/approvals/{approval_id}")
    def answer(approval_id: str, body: Answer):
        try:
            return coord.answer_approval(approval_id, body.decision)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"no approval {approval_id}")

    @app.post("/api/pace")
    def pace(body: Pace):
        try:
            return {"pace": coord.set_pace(body.factor)}
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    @app.post("/api/reset")
    def reset():
        try:
            return coord.reset()
        except ResetTimeout as e:
            raise HTTPException(status_code=503, detail=str(e))

    ui = ui_dir or REPO / "frontend" / "dist"
    if ui.is_dir() and (ui / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(ui), html=True), name="ui")
    else:
        @app.get("/", response_class=HTMLResponse)
        def no_ui():
            return ("<h1>Flake demo API is up</h1><p>The UI is not built. Run "
                    "<code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code>, then restart.</p>")
    return app
