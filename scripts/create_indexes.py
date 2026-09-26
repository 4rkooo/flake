import os, time

from pymongo import ASCENDING, DESCENDING
from pymongo.operations import SearchIndexModel

from flake.config import db

DIMS = int(os.environ.get("EMBEDDING_DIMS", "1536"))


def ensure_vector_index(collection, name: str, path: str, filters: list[str]) -> None:
    existing = {ix["name"] for ix in collection.list_search_indexes()}
    if name in existing:
        print(f"{collection.name}.{name}: exists")
        return
    fields = [{"type": "vector", "path": path, "numDimensions": DIMS, "similarity": "cosine"}]
    fields += [{"type": "filter", "path": f} for f in filters]
    collection.create_search_index(SearchIndexModel(definition={"fields": fields}, name=name, type="vectorSearch"))
    while True:  # wait until Atlas reports it queryable
        status = next(ix for ix in collection.list_search_indexes() if ix["name"] == name)
        if status.get("queryable"):
            break
        time.sleep(5)
    print(f"{collection.name}.{name}: queryable")


def main() -> None:
    db.episodes.create_index([("group_id", ASCENDING), ("resolved_at", DESCENDING)])
    db.harness_versions.create_index([("group_id", ASCENDING), ("version", DESCENDING)], unique=True)
    db.audit_log.create_index([("episode_id", ASCENDING), ("ts", ASCENDING)])
    db.chat_log.create_index([("group_id", ASCENDING), ("at", ASCENDING)])
    ensure_vector_index(db.episodes, "episodes_vec", "embedding", ["group_id"])


if __name__ == "__main__":
    main()
