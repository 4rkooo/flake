"""The notes store gives up its vector index only when the index itself fails (Atlas refuses
it, or it is still building); any other startup error must surface, as in the guide."""
import importlib
import sys
import types

import pytest
from pymongo.errors import OperationFailure, ServerSelectionTimeoutError

from flake import memory

INDEX_LIMIT = OperationFailure("The maximum number of FTS indexes has been reached for this instance size.")


def _store_failing_with(exc):
    real = sys.modules["langgraph.store.mongodb"].MongoDBStore

    def from_conn_string(*a, **k):
        if "index_config" in k:          # only the first attempt asks for a vector index
            raise exc
        return real.from_conn_string()
    return types.SimpleNamespace(from_conn_string=from_conn_string)


@pytest.fixture
def reload_memory(monkeypatch):
    store_mod = sys.modules["langgraph.store.mongodb"]

    def load(exc):
        monkeypatch.setattr(store_mod, "MongoDBStore", _store_failing_with(exc))
        importlib.reload(memory)
    yield load
    monkeypatch.undo()
    importlib.reload(memory)             # back to the fake store every other test uses


@pytest.mark.parametrize("exc", [INDEX_LIMIT, TimeoutError("index not ready after 15s")])
def test_an_index_failure_falls_back_to_plain_notes(reload_memory, exc, capsys):
    reload_memory(exc)
    assert str(exc) in memory.STORE_INDEX_ERROR
    assert "vector index" in capsys.readouterr().err          # said once at startup, not silent
    memory.add_note("g", "k", "sam bailed")                    # the store still works as key-value memory


def test_any_other_startup_error_is_not_mistaken_for_the_index_limit(reload_memory):
    with pytest.raises(ServerSelectionTimeoutError):
        reload_memory(ServerSelectionTimeoutError("no servers found"))
