"""ensure_notes_index: create the notes vector index ahead of the store and wait a bounded time
for Atlas to build it, degrading (never crashing) when Atlas refuses or has no search."""
import types

import pymongo
import pytest
from pymongo.errors import OperationFailure

from flake.demo import server

PENDING = {"status": "PENDING", "queryable": False}
READY = {"status": "READY", "queryable": True}


class FakeNotes:
    """list_search_indexes() answers from `statuses` in turn (the last one repeats); None = no index yet."""

    def __init__(self, statuses, refuse=None, unavailable=False):
        self.statuses, self.refuse, self.unavailable = list(statuses), refuse, unavailable
        self.created = []

    def list_search_indexes(self):
        if self.unavailable:
            raise OperationFailure("no such command: listSearchIndexes")
        s = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return [] if s is None else [{"name": "vector_index", **s}]

    def create_search_index(self, model):
        if self.refuse:
            raise self.refuse
        self.created.append(model)


@pytest.fixture
def atlas(monkeypatch):
    """Point MongoClient at one fake notes collection and give server a clock that sleep() advances."""
    env = types.SimpleNamespace(notes=None, closed=False, t=0.0)

    class Db:
        def __getitem__(self, name):
            return env.notes

        def list_collection_names(self):
            return ["notes"]

    class Client:
        def __init__(self, uri):
            pass

        def __getitem__(self, name):
            return Db()

        def close(self):
            env.closed = True

    monkeypatch.setattr(pymongo, "MongoClient", Client)

    def sleep(s):
        env.t += s
    monkeypatch.setattr(server, "time", types.SimpleNamespace(time=lambda: env.t, sleep=sleep))
    return env


def test_creates_the_missing_index_and_waits_until_queryable(atlas, capsys):
    atlas.notes = FakeNotes([None, PENDING, PENDING, READY])
    server.ensure_notes_index("mongodb://x", "flake_demo", timeout=60)
    assert len(atlas.notes.created) == 1 and "queryable" in capsys.readouterr().out
    assert atlas.t == 10 and atlas.closed          # two 5 s polls, then done


def test_gives_up_after_the_timeout_when_the_index_never_builds(atlas, capsys):
    atlas.notes = FakeNotes([PENDING])             # exists, stuck building
    server.ensure_notes_index("mongodb://x", "flake_demo", timeout=20)
    out = capsys.readouterr().out
    assert "not ready yet" in out and 20 <= atlas.t < 30
    assert atlas.notes.created == [] and atlas.closed


def test_a_refused_index_degrades_without_waiting(atlas, capsys):
    atlas.notes = FakeNotes([None], refuse=OperationFailure("The maximum number of FTS indexes has been reached"))
    server.ensure_notes_index("mongodb://x", "flake_demo", timeout=60)
    assert "not created" in capsys.readouterr().out and atlas.t == 0 and atlas.closed


def test_no_atlas_search_degrades_without_waiting(atlas, capsys):
    atlas.notes = FakeNotes([None], unavailable=True)
    server.ensure_notes_index("mongodb://x", "flake_demo", timeout=60)
    assert "unavailable" in capsys.readouterr().out and atlas.t == 0 and atlas.closed
