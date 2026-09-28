"""`uv run flake-demo`: serve the visual demo.

Order matters here. The demo database name is chosen and put in MONGODB_DB, and the
pymongo listener is registered, BEFORE any flake module imports flake.config -- that is
where the shared MongoClient, the checkpointer's database and the notes store are bound."""

import argparse
import os
import sys
import time
from pathlib import Path


def ensure_notes_index(uri: str, db_name: str, timeout: float = 150) -> None:
    """Create the notes store's vector index ahead of the store itself. On a fresh demo
    database the store would otherwise create it at import and give up after 15s while
    Atlas is still building (30s or more), which kills the server on first start."""
    from pymongo import MongoClient
    from pymongo.operations import SearchIndexModel

    client = MongoClient(uri)
    try:
        db = client[db_name]
        col = db["notes"]
        try:
            existing = {ix["name"] for ix in col.list_search_indexes()}
        except Exception as e:  # noqa: BLE001 -- no Atlas Search on this deployment
            print(f"notes.vector_index: search indexes unavailable ({type(e).__name__}); notes fall back to none", flush=True)
            return
        if "vector_index" not in existing:
            if "notes" not in db.list_collection_names():
                db.create_collection("notes")
            dims = int(os.environ.get("EMBEDDING_DIMS", "1536"))
            fields = [{"type": "vector", "path": "embedding", "numDimensions": dims, "similarity": "cosine"},
                      {"type": "filter", "path": "namespace_prefix"}]   # what langgraph's MongoDBStore builds
            try:
                col.create_search_index(SearchIndexModel(definition={"fields": fields}, name="vector_index", type="vectorSearch"))
            except Exception as e:  # noqa: BLE001
                # small Atlas tiers allow 3 search indexes per cluster; the CLI database may already hold two.
                # The demo still runs: similar plans keep their vector index, notes fall back and say so.
                print(f"notes.vector_index: not created ({str(e).splitlines()[0][:120]}); note search will use the fallback. "
                      "Free a slot by dropping an index on another database, or run with --db flake.")
                return
            print("notes.vector_index: created, waiting for Atlas to build it", flush=True)
        started = time.time()
        while time.time() - started < timeout:
            status = next((ix for ix in col.list_search_indexes() if ix["name"] == "vector_index"), None)
            if status and status.get("queryable"):
                print("notes.vector_index: queryable", flush=True)
                return
            print(f"notes.vector_index: {status.get('status') if status else 'missing'}, waiting", flush=True)
            time.sleep(5)
        print("notes.vector_index: not ready yet; note searches fall back to none until it is", flush=True)
    finally:
        client.close()


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="flake-demo", description="Serve the Flake visual demo locally.")
    parser.add_argument("--host", default=os.environ.get("FLAKE_DEMO_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("PORT") or os.environ.get("FLAKE_DEMO_PORT") or 8000),
                        help="reads $PORT first, for platforms that inject it (e.g. Fly.io, Render)")
    parser.add_argument("--db", help="demo database name (default: $FLAKE_DEMO_DB, else ${MONGODB_DB}_demo)")
    parser.add_argument("--fake", action="store_true",
                        help="offline rehearsal: in-memory database and a scripted model, no keys needed")
    parser.add_argument("--ui", help="path to the built frontend (default: frontend/dist)")
    parser.add_argument("--pace", type=float, default=float(os.environ.get("FLAKE_DEMO_PACE", "1.0")),
                        help="presentation pace: 1.0 holds each step on screen for about a second, 0 runs flat out")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv
    load_dotenv()

    fake = args.fake or os.environ.get("FLAKE_DEMO_FAKE", "").lower() in ("1", "true", "yes")
    base = os.environ.get("MONGODB_DB", "flake")
    demo_db = args.db or os.environ.get("FLAKE_DEMO_DB") or f"{base}_demo"
    os.environ["MONGODB_DB"] = demo_db          # read by config, memory (store) and graph (checkpointer)

    watcher = None
    if fake:
        from flake.demo import fake_env, fake_llm
        fake_env.install(llm=fake_llm.ScriptedChatModel())
        print("fake mode: in-memory database, scripted model, no network", flush=True)
    else:
        missing = [v for v in ("MONGODB_URI", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "LLM_MODEL") if not os.environ.get(v)]
        if missing:
            sys.exit(f"{', '.join(missing)} not set: copy .env.example to .env, or run with --fake")
        from flake.demo import dbwatch
        watcher = dbwatch.install()             # before the first MongoClient exists
        ensure_notes_index(os.environ["MONGODB_URI"], demo_db)

    from flake.demo.api import create_app
    from flake.demo.coordinator import Coordinator

    coord = Coordinator(watcher=watcher, pace=args.pace)
    app = create_app(coord, ui_dir=Path(args.ui) if args.ui else None)
    print(f"Flake demo on http://{args.host}:{args.port}  database: {demo_db}{'  (fake)' if fake else ''}", flush=True)
    print("Open the page and press Next Beat; the first beat resets the demo database.", flush=True)

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
