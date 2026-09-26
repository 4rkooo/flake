"""A thread-safe, ordered event journal for one server session.

Every observation becomes one Event with a monotonic `seq`. The browser follows the
stream from a cursor and, after a reload, asks for everything since 0 -- so a refresh
rebuilds the view without rerunning anything. reset() starts a new session id and a
fresh sequence, so events from before the reset can never repopulate the new view.
"""

import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def new_session() -> str:
    return uuid.uuid4().hex[:12]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Event:
    seq: int
    session: str
    ts: str
    kind: str
    status: str                 # start | ok | info | warn | error
    beat: int | None
    beat_id: str | None
    operation: str | None
    node: str | None            # diagram node this event lights up
    summary: str
    details: dict = field(default_factory=dict)
    plan_id: str | None = None
    version_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class Journal:
    MAX_EVENTS = 5000   # a full run is a few hundred; this only guards against a runaway

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[Event] = []
        self._session = new_session()
        self._seq = 0

    @property
    def session(self) -> str:
        return self._session

    def append(self, kind: str, status: str = "info", *, beat=None, beat_id=None, operation=None, node=None,
               summary: str = "", details: dict | None = None, plan_id=None, version_id=None) -> Event:
        with self._lock:
            self._seq += 1
            ev = Event(self._seq, self._session, now(), kind, status, beat, beat_id, operation, node,
                       summary, details or {}, plan_id, version_id)
            self._events.append(ev)
            if len(self._events) > self.MAX_EVENTS:
                del self._events[: len(self._events) - self.MAX_EVENTS]
            return ev

    def since(self, cursor: int) -> list[Event]:
        # cursor = the last seq the reader has; 0 (or a cursor from another session) replays all
        with self._lock:
            if cursor <= 0 or cursor > self._seq:
                return list(self._events)
            return [e for e in self._events if e.seq > cursor]

    def cursor(self) -> int:
        with self._lock:
            return self._seq

    def all(self) -> list[Event]:
        with self._lock:
            return list(self._events)

    def reset(self) -> str:
        with self._lock:
            self._events.clear()
            self._seq = 0
            self._session = new_session()
            return self._session
