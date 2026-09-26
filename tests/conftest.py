import sys
import types

# flake.memory opens an Atlas connection (and a vector index) at import time.
# Lane C's gate tests only need its tiny read API, so swap in a stand-in
# before anything imports the real one.
if "flake.memory" not in sys.modules:
    fake = types.ModuleType("flake.memory")
    fake.current_run = {}
    fake.get_episode = lambda plan_id: {}
    fake.now = lambda: "2026-01-01T00:00:00+00:00"
    sys.modules["flake.memory"] = fake


import mongomock
import pytest


@pytest.fixture
def db(monkeypatch):
    """In-memory Mongo standing in for Atlas, patched into every harness module."""
    from flake.harness import canary, retro, versions

    fake = mongomock.MongoClient().flake
    for mod in (versions, canary, retro):
        if hasattr(mod, "db"):
            monkeypatch.setattr(mod, "db", fake)
    return fake
