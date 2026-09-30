import mongomock
import pytest

# Installed before any test imports flake: flake.config would otherwise connect to
# Atlas and build LLM/embedding clients, and flake.memory opens a LangGraph Mongo
# store (with a vector index) at import. With these fakes the real memory module
# runs on mongomock, so tests can use it or monkeypatch its functions. The same
# fakes power `flake-demo --fake`; the default model always fails, so the Retro
# takes the deterministic pricing fallback.
from flake.demo import fake_env  # noqa: E402

fake_env.install()


@pytest.fixture
def db(monkeypatch):
    """In-memory Mongo standing in for Atlas, patched into every harness module."""
    from flake.harness import canary, retro, versions

    fake = mongomock.MongoClient().flake
    for mod in (versions, canary, retro):
        if hasattr(mod, "db"):
            monkeypatch.setattr(mod, "db", fake)
    return fake
