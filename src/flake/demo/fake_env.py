"""Stand-ins so the code base runs without Atlas or model keys: mongomock for the
database, a hash for the embedder, a fake notes store, an in-memory checkpointer and a
model of the caller's choosing. Used by tests/conftest.py and by `flake-demo --fake`.

install() must run before anything imports flake.config."""

import hashlib
import os
import sys
import types


class _NoLLM:
    """'network off': underwriter_llm.propose must fall back to pricing; the graph must still import."""

    def with_structured_output(self, *_a, **_k):
        raise RuntimeError("network off")

    def bind_tools(self, *_a, **_k):
        return self

    def invoke(self, *_a, **_k):
        raise RuntimeError("network off")


class FakeStore:
    """Stands in for the LangGraph MongoDBStore behind memory.add_note/search_notes."""

    def __init__(self):
        self.items = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def put(self, ns, key, value, **_):
        self.items = [(n, k, v) for n, k, v in self.items if (n, k) != (ns, key)]   # replace, like the real store
        self.items.append((ns, key, value))

    def search(self, ns, query=None, limit=10, **_):
        return [types.SimpleNamespace(key=k, value=v) for n, k, v in self.items if n == ns][:limit]

    def clear(self):
        self.items.clear()


def install(llm=None, seed: int = 42):
    import mongomock

    cfg = types.ModuleType("flake.config")
    cfg.client = mongomock.MongoClient()
    cfg.db = cfg.client["flake"]
    cfg.embed = lambda text: [b / 255 for b in hashlib.sha256(text.encode()).digest()] * 48  # 1536 dims
    cfg.llm = llm if llm is not None else _NoLLM()
    cfg.embedder = None
    cfg.DEMO_SEED = seed
    cfg.LLM_CACHE_PATH = None
    sys.modules["flake.config"] = cfg

    store_mod = types.ModuleType("langgraph.store.mongodb")
    store_mod.MongoDBStore = types.SimpleNamespace(from_conn_string=lambda *a, **k: FakeStore())
    store_mod.create_vector_index_config = lambda **k: None
    sys.modules["langgraph.store.mongodb"] = store_mod

    # the Mongo checkpointer needs a real server (mongomock lacks its bulk options): keep working memory in RAM
    from langgraph.checkpoint.memory import InMemorySaver
    global _saver, _store
    _saver = InMemorySaver()
    _store = store_mod.MongoDBStore.from_conn_string()
    store_mod.MongoDBStore = types.SimpleNamespace(from_conn_string=lambda *a, **k: _store)
    ckpt_mod = types.ModuleType("langgraph.checkpoint.mongodb")
    ckpt_mod.MongoDBSaver = lambda *a, **k: _saver
    sys.modules["langgraph.checkpoint.mongodb"] = ckpt_mod

    os.environ.setdefault("MONGODB_URI", "mongodb://fake")
    return cfg


_saver = None
_store = None


def clear_state() -> None:
    """What a real reset does to the checkpoints and notes collections, for the in-memory stand-ins.
    A no-op unless install() ran."""
    if _saver is not None:
        for attr in ("storage", "writes", "blobs"):
            getattr(_saver, attr, {}).clear()
    if _store is not None:
        _store.clear()
