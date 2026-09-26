import subprocess
import sys

from flake import memory
from flake.config import db
from flake.risk.model import build_profiles

for name in ["episodes", "harness_versions", "risk_profiles", "audit_log", "chat_log", "notes", "checkpoints", "checkpoint_writes"]:
    db[name].drop()  # dropping a collection drops its search indexes too

subprocess.run([sys.executable, "scripts/seed.py"], check=True)
subprocess.run([sys.executable, "scripts/create_indexes.py"], check=True)

profiles = build_profiles("friends", memory.resolved_episodes("friends"))
print(f"sam flake_score: {profiles['sam']['flake_score']}")
