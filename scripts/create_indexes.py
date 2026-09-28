import os, time

from pymongo import ASCENDING, DESCENDING
from pymongo.operations import SearchIndexModel

from flake.config import db

DIMS = int(os.environ.get("EMBEDDING_DIMS", "1536"))


def ensure_vector_index(collection, name: str, path: str, filters: list[str],
                        timeout: float | None = None, progress=print) -> bool:
    """Create the index if missing and wait until Atlas reports it queryable.
    timeout=None waits forever (the CLI); the demo passes a bound and shows the
    progress lines, then runs with the recency fallback until the index is ready."""
    existing = {ix["name"] for ix in collection.list_search_indexes()}
    if name in existing:
        progress(f"{collection.name}.{name}: exists")
        return True
    fields = [{"type": "vector", "path": path, "numDimensions": DIMS, "similarity": "cosine"}]
    fields += [{"type": "filter", "path": f} for f in filters]
    collection.create_search_index(SearchIndexModel(definition={"fields": fields}, name=name, type="vectorSearch"))
    started = time.time()
    while True:  # wait until Atlas reports it queryable
        status = next(ix for ix in collection.list_search_indexes() if ix["name"] == name)
        if status.get("queryable"):
            break
        if timeout is not None and time.time() - started > timeout:
            progress(f"{collection.name}.{name}: still {status.get('status', 'PENDING')} after {timeout:.0f}s; "
                     "searches fall back to recency until it is queryable")
            return False
        progress(f"{collection.name}.{name}: {status.get('status', 'PENDING')}, waiting")
        time.sleep(5)
    progress(f"{collection.name}.{name}: queryable")
    return True


def main(timeout: float | None = None, progress=print) -> bool:
    db.episodes.create_index([("group_id", ASCENDING), ("resolved_at", DESCENDING)])
    db.harness_versions.create_index([("group_id", ASCENDING), ("version", DESCENDING)], unique=True)
    db.audit_log.create_index([("episode_id", ASCENDING), ("ts", ASCENDING)])
    db.chat_log.create_index([("group_id", ASCENDING), ("at", ASCENDING)])
    return ensure_vector_index(db.episodes, "episodes_vec", "embedding", ["group_id"], timeout=timeout, progress=progress)


if __name__ == "__main__":
    main()
