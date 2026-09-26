import hashlib
import os
import sys
import types

import mongomock

# Installed before any test imports flake: flake.config would otherwise connect to
# Atlas and build LLM/embedding clients, and flake.memory opens a LangGraph Mongo
# store (with a vector index) at import. With these fakes the real memory module
# runs on mongomock, so tests can use it or monkeypatch its functions.
cfg = types.ModuleType("flake.config")
cfg.client = mongomock.MongoClient()
cfg.db = cfg.client["flake"]
cfg.embed = lambda text: [b / 255 for b in hashlib.sha256(text.encode()).digest()] * 48  # 1536 dims


class _NoLLM:  # "network off": underwriter_llm.propose must fall back to pricing
    def with_structured_output(self, *_a, **_k):
        raise RuntimeError("network off")

    def bind_tools(self, *_a, **_k):
        return self


cfg.llm, cfg.embedder, cfg.DEMO_SEED, cfg.LLM_CACHE_PATH = _NoLLM(), None, 42, None
sys.modules["flake.config"] = cfg


class FakeStore:  # stands in for the LangGraph MongoDBStore behind memory.add_note/search_notes
    def __init__(self):
        self.items = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def put(self, ns, key, value, **_):
        self.items.append((ns, key, value))

    def search(self, ns, query=None, limit=10, **_):
        return [types.SimpleNamespace(key=k, value=v) for n, k, v in self.items if n == ns][:limit]


store_mod = types.ModuleType("langgraph.store.mongodb")
store_mod.MongoDBStore = types.SimpleNamespace(from_conn_string=lambda *a, **k: FakeStore())
store_mod.create_vector_index_config = lambda **k: None
sys.modules["langgraph.store.mongodb"] = store_mod
os.environ.setdefault("MONGODB_URI", "mongodb://fake")


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
