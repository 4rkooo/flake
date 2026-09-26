"""The Reset / baseline beat: empty the demo database (keeping collections and their
indexes), reseed the five past plans and v1, and make sure the indexes are usable --
with a bounded wait and visible progress instead of create_indexes.py's forever loop.
The LLM cache on disk is never touched."""

import importlib.util
import time
from pathlib import Path

from flake import observe

REPO = Path(__file__).resolve().parents[3]
COLLECTIONS = ["episodes", "harness_versions", "risk_profiles", "audit_log", "chat_log", "notes",
               "checkpoints", "checkpoint_writes"]
INDEX_TIMEOUT_S = 120


def load_script(name: str):
    # scripts/*.py are plain scripts, not a package: load them by path so the demo reuses
    # the exact seed and index code the CLI runs
    path = REPO / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"flake_scripts_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wait_for_search_index(collection, name: str, timeout: float, progress) -> bool | None:
    """True when queryable, False when the wait ran out, None when the collection has no
    such index (or search indexes are unavailable, e.g. in fake mode)."""
    started = time.time()
    while True:
        try:
            status = next((ix for ix in collection.list_search_indexes() if ix["name"] == name), None)
        except Exception as e:                       # mongomock / no Atlas Search
            progress(f"{collection.name}.{name}: search indexes unavailable ({type(e).__name__})")
            return None
        if status is None:
            progress(f"{collection.name}.{name}: no such index (cluster search-index limit?); this memory falls back")
            return None
        if status.get("queryable"):
            progress(f"{collection.name}.{name}: queryable")
            return True
        if time.time() - started > timeout:
            progress(f"{collection.name}.{name}: still {status.get('status', 'PENDING')} after {timeout:.0f}s")
            return False
        progress(f"{collection.name}.{name}: {status.get('status', 'PENDING')}, waiting")
        time.sleep(5)


def run(index_timeout: float = INDEX_TIMEOUT_S) -> dict:
    from flake.config import db

    # 1. clear: delete documents, never drop, so the vector indexes survive
    for name in COLLECTIONS:
        deleted = db[name].delete_many({}).deleted_count
        observe.emit("reset.step", step="clear", collection=name, deleted=deleted)
    from flake.demo import fake_env
    fake_env.clear_state()                       # fake mode keeps checkpoints and notes in RAM, not in collections

    # 2. reseed: group, five resolved plans with embeddings, v1 active, first risk table
    observe.emit("reset.step", step="seed", state="start")
    load_script("seed").main()
    observe.emit("reset.step", step="seed", state="done",
                 episodes=db.episodes.count_documents({}), versions=db.harness_versions.count_documents({}),
                 profiles=db.risk_profiles.count_documents({}))

    # 3. indexes: plain ones are instant; the vector index gets a bounded wait with progress
    def progress(line: str) -> None:
        observe.emit("reset.step", step="index", message=line)

    episodes_ready = None
    try:
        episodes_ready = load_script("create_indexes").main(timeout=index_timeout, progress=progress)
    except Exception as e:
        progress(f"index setup skipped: {type(e).__name__}: {e}"[:200])
    notes_ready = wait_for_search_index(db.notes, "vector_index", index_timeout, progress)

    result = {"episodes_index_ready": episodes_ready, "notes_index_ready": notes_ready,
              "episodes": db.episodes.count_documents({}), "versions": db.harness_versions.count_documents({})}
    observe.emit("reset.done", **result)
    return result
