import subprocess

from flake.config import db

for name in ["episodes", "harness_versions", "risk_profiles", "audit_log", "chat_log", "notes", "checkpoints", "checkpoint_writes"]:
    db[name].drop()  # dropping a collection drops its search indexes too

subprocess.run(["python", "scripts/seed.py"], check=True)
subprocess.run(["python", "scripts/create_indexes.py"], check=True)
