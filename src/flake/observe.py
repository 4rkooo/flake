"""
flake/observe.py

Optional observation hooks, shared by every lane.

Core modules call observe.emit(kind, **fields) at the points a viewer cares about: graph
nodes, tool results, gate decisions, retrieval, the risk maths, Retro steps, version
transitions. With no subscriber (the CLI) emit() returns immediately, so `flake plan`
and `flake retro` behave exactly as before.

The demo server subscribes and turns the calls into ordered events for the browser. It
also uses this module to stop a run cooperatively: after request_cancel(), the next
observation point raises Cancelled, which unwinds the graph without touching the world
any further. Only the demo ever sets that flag.
"""

import threading
from contextlib import contextmanager

_subscribers: list = []
_local = threading.local()          # per-thread: quiet flag + scratch notes
_cancel = threading.Event()


class Cancelled(Exception):
    """Raised at an observation point after request_cancel(): the demo is resetting."""


def subscribe(fn) -> None:
    # fn(kind: str, fields: dict) -> None. Subscribers must not raise; an error in a
    # viewer must never break the agent.
    if fn not in _subscribers:
        _subscribers.append(fn)


def unsubscribe(fn) -> None:
    if fn in _subscribers:
        _subscribers.remove(fn)


def is_quiet() -> bool:
    return getattr(_local, "quiet", 0) > 0


@contextmanager
def quiet():
    # Suppress emission from this thread: the demo reads the database to build its state
    # snapshot and those reads are not agent activity.
    _local.quiet = getattr(_local, "quiet", 0) + 1
    try:
        yield
    finally:
        _local.quiet -= 1


def emit(kind: str, **fields) -> None:
    # Every observation point is also a cancellation point, so a reset stops a run at the
    # next node/tool/write boundary instead of waiting for it to finish.
    if _cancel.is_set() and not is_quiet():
        raise Cancelled(kind)
    if not _subscribers or is_quiet():
        return
    for fn in list(_subscribers):
        try:
            fn(kind, fields)
        except Exception:
            pass    # a viewer bug is not the agent's problem


def request_cancel() -> None:
    _cancel.set()


def clear_cancel() -> None:
    _cancel.clear()


def cancel_requested() -> bool:
    return _cancel.is_set()


def check_cancelled() -> None:
    if _cancel.is_set():
        raise Cancelled("check")


# Scratch notes let one layer leave a fact for the caller on the same thread, e.g. the
# LLM cache marks hit/miss so the agent node can label its turn without knowing about caching.
def note(key: str, value) -> None:
    notes = getattr(_local, "notes", None)
    if notes is None:
        notes = _local.notes = {}
    notes[key] = value


def take(key: str, default=None):
    notes = getattr(_local, "notes", None)
    if not notes:
        return default
    return notes.pop(key, default)
