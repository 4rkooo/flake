import subprocess
import sys

from flake.config import db

for name in ["episodes", "harness_versions", "risk_profiles", "audit_log", "chat_log", "notes", "checkpoints", "checkpoint_writes"]:
    # empty, don't drop: a drop deletes the vector indexes, and rebuilding them is slow and
    # can hit the cluster's search-index limit right before the demo
    db[name].delete_many({})

subprocess.run([sys.executable, "scripts/seed.py"], check=True)
subprocess.run([sys.executable, "scripts/create_indexes.py"], check=True)
